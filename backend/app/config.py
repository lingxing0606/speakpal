import json
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

# 必须在 load_dotenv() 之前快照：只有“真实进程环境”里的 DATABASE_URL 才算部署级覆盖。
# 否则 .env 里的 DATABASE_URL 会永远压过 data_location.json，改位置会静默失效。
_ENV_SNAPSHOT = frozenset(os.environ)

_BACKEND_DIR = Path(__file__).resolve().parent.parent

# 显式指定 backend/.env：不依赖启动时的工作目录（否则从别的目录启动会找不到，
# 生成的密钥每次都变，所有人的登录都会失效）
load_dotenv(_BACKEND_DIR / ".env")
LOCATION_FILE = _BACKEND_DIR / "data_location.json"
DEFAULT_DATABASE_URL = "sqlite:///./speakpal.db"


def read_data_location() -> dict:
    """读 data_location.json；坏了/不存在都当没配置，不抛。"""
    try:
        data = json.loads(LOCATION_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _resolve_database_url() -> tuple[str, str]:
    """返回 (database_url, 来源)。优先级：

    1. 真实进程环境变量 DATABASE_URL（部署级覆盖）
    2. backend/data_location.json
    3. backend/.env 里的 DATABASE_URL
    4. 默认 backend/speakpal.db
    """
    env_url = os.environ.get("DATABASE_URL")
    if "DATABASE_URL" in _ENV_SNAPSHOT and env_url:
        return env_url, "env"
    config_url = str(read_data_location().get("database_url") or "").strip()
    if config_url:
        return config_url, "config"
    dotenv_url = os.environ.get("DATABASE_URL")
    if dotenv_url:
        return dotenv_url, "dotenv"
    return DEFAULT_DATABASE_URL, "default"


_DATABASE_URL, _DATABASE_SOURCE = _resolve_database_url()

ENV_FILE = _BACKEND_DIR / ".env"
# 公开过的默认值等于没设：README / 旧版 .env.example 里写过，谁都能拿来伪造 token、进管理台
_WEAK_SECRETS = {
    "JWT_SECRET": {"", "dev-secret-change-me", "change-me-to-a-random-long-string"},
    "ADMIN_KEY": {"", "admin123"},
}


def _persist_env(name: str, value: str) -> bool:
    """把生成的值写回 backend/.env（替换同名行或追加），失败返回 False。"""
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
        out, replaced = [], False
        for line in lines:
            if line.split("=", 1)[0].strip() == name:
                out.append(f"{name}={value}")
                replaced = True
            else:
                out.append(line)
        if not replaced:
            out.append(f"{name}={value}")
        ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


def _ensure_secret(name: str, nbytes: int, show: bool) -> str:
    """默认/空值就随机生成一个并写回 .env，重启后保持不变。

    真实进程环境变量里给的值不改写（部署方自己负责）；只告警。
    """
    value = (os.environ.get(name) or "").strip()
    if value not in _WEAK_SECRETS[name]:
        return value
    if name in _ENV_SNAPSHOT and value:
        print(f"[config] 警告：环境变量 {name} 是公开默认值，请更换", flush=True)
        return value
    value = secrets.token_urlsafe(nbytes)
    os.environ[name] = value
    saved = _persist_env(name, value)
    where = "已写入 backend/.env" if saved else "未能写入 .env，仅本次进程有效"
    if show:
        print(f"[config] {name} 原为默认值，已生成新值（{where}）：{value}", flush=True)
    else:
        print(f"[config] {name} 原为默认值，已生成随机值（{where}）", flush=True)
    return value


def _csv_env(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings:
    jwt_secret: str = _ensure_secret("JWT_SECRET", 48, show=False)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))
    database_url: str = _DATABASE_URL
    database_source: str = _DATABASE_SOURCE
    location_file: str = str(LOCATION_FILE)
    # 对话密钥不再由服务端保存（用户要求）：只认浏览器带来的 X-LLM-Key，
    # 所以这里没有 llm_api_key；.env 里就算写了 LLM_API_KEY 也不会被读取。
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    llm_model: str = os.getenv("LLM_MODEL", "deepseek-chat")
    # 语音合成（可选）：用的是 OpenAI 兼容的 /audio/speech，不填就走浏览器内置朗读
    tts_api_key: str = os.getenv("TTS_API_KEY", "")
    tts_base_url: str = os.getenv("TTS_BASE_URL", "https://api.openai.com/v1")
    tts_model: str = os.getenv("TTS_MODEL", "tts-1")
    tts_voice: str = os.getenv("TTS_VOICE", "alloy")
    # 管理密钥要人去填，所以生成时打印到后端控制台
    admin_key: str = _ensure_secret("ADMIN_KEY", 12, show=True)
    # 跨域白名单：前端走 vite 代理时其实是同源，这里只为直连 8000 的场景
    cors_origins: list[str] = _csv_env(
        "CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
    )
    # 默认拒绝让服务端去请求内网 / 本机地址（防 SSRF）；用本机 Ollama 之类时设成 1
    allow_private_llm_hosts: bool = os.getenv("ALLOW_PRIVATE_LLM_HOSTS", "0") == "1"
    # 管理台「改数据位置」的目录白名单；留空不限目录（但始终不覆盖已存在的文件）
    storage_root: str = os.getenv("STORAGE_ROOT", "").strip()


settings = Settings()


def database_url_locked_by_env() -> bool:
    """真实环境变量是否锁定库地址（锁定时改配置无效，接口要返回 409）。"""
    return settings.database_source == "env"
