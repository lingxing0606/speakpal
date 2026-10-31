import json
import os
from pathlib import Path

from dotenv import load_dotenv

# 必须在 load_dotenv() 之前快照：只有“真实进程环境”里的 DATABASE_URL 才算部署级覆盖。
# 否则 .env 里的 DATABASE_URL 会永远压过 data_location.json，改位置会静默失效。
_ENV_SNAPSHOT = frozenset(os.environ)

load_dotenv()

_BACKEND_DIR = Path(__file__).resolve().parent.parent
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


class Settings:
    jwt_secret: str = os.getenv("JWT_SECRET", "dev-secret-change-me")
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
    admin_key: str = os.getenv("ADMIN_KEY", "admin123")


settings = Settings()


def database_url_locked_by_env() -> bool:
    """真实环境变量是否锁定库地址（锁定时改配置无效，接口要返回 409）。"""
    return settings.database_source == "env"
