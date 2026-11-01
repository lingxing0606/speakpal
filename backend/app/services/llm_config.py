"""每个请求的模型配置：只用浏览器带来的 key。

用户要求服务端不再提供密钥，所以这里**没有 `.env` 兜底**：
没有 `X-LLM-Key` 就是未配置，接口按 409 `llm_not_configured` 拦住，
前端只留「去设置填密钥」这一条路。密钥只在内存里用一次，不落库、不打日志。
base_url / model 仍支持请求头覆盖，用户可以用自己的中转或别的 OpenAI 兼容服务。
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from fastapi import Header

from ..config import settings


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str
    model: str
    key_source: str  # user | none（服务端密钥已下线，不再有 env）

    @property
    def from_user(self) -> bool:
        return self.key_source == "user"

    @property
    def configured(self) -> bool:
        return self.key_source != "none"


def _clean(value: str | None) -> str:
    return (value or "").strip()


def is_valid_base_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def build_llm_config(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> LLMConfig:
    user_key = _clean(api_key)
    # 服务端不再提供密钥：没有浏览器带来的 key 就是未配置，不做 `.env` 兜底
    key, source = (user_key, "user") if user_key else ("", "none")
    return LLMConfig(
        api_key=key,
        base_url=_clean(base_url) or settings.llm_base_url,
        model=_clean(model) or settings.llm_model,
        key_source=source,
    )


def get_llm_config(
    x_llm_key: str | None = Header(default=None, alias="X-LLM-Key"),
    x_llm_base_url: str | None = Header(default=None, alias="X-LLM-Base-URL"),
    x_llm_model: str | None = Header(default=None, alias="X-LLM-Model"),
) -> LLMConfig:
    return build_llm_config(x_llm_key, x_llm_base_url, x_llm_model)


class UserKeyInvalid(Exception):
    """用户自己配的 key 被服务端拒绝（401/403）。

    这种情况必须明确告诉用户去换 key，不能降级成「示例报告」——否则用户会以为
    模型暂时不可用，反复重试一个永远不可能成功的密钥。
    """

    def __init__(self, message: str = "模型密钥无效或被拒绝，请到「设置」更换密钥后再试"):
        self.message = message
        super().__init__(message)


# ---------------------------------------------------------------- TTS（可选）
@dataclass(frozen=True)
class TTSConfig:
    api_key: str
    base_url: str
    model: str
    voice: str
    key_source: str  # user | env | none

    @property
    def configured(self) -> bool:
        return self.key_source != "none"


def build_tts_config(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    voice: str | None = None,
) -> TTSConfig:
    user_key = _clean(api_key)
    env_key = (settings.tts_api_key or "").strip()
    user_base = _clean(base_url)
    # 服务端兜底 key 只能发往服务端配置的地址：否则填个自己的地址就能把 key 收走
    foreign_base = bool(user_base) and user_base.rstrip("/") != settings.tts_base_url.rstrip("/")
    if user_key:
        key, source = user_key, "user"
    elif env_key and not foreign_base:
        key, source = env_key, "env"
    else:
        key, source = "", "none"
    return TTSConfig(
        api_key=key,
        base_url=_clean(base_url) or settings.tts_base_url,
        model=_clean(model) or settings.tts_model,
        voice=_clean(voice) or settings.tts_voice,
        key_source=source,
    )


def get_tts_config(
    x_tts_key: str | None = Header(default=None, alias="X-TTS-Key"),
    x_tts_base_url: str | None = Header(default=None, alias="X-TTS-Base-URL"),
    x_tts_model: str | None = Header(default=None, alias="X-TTS-Model"),
    x_tts_voice: str | None = Header(default=None, alias="X-TTS-Voice"),
) -> TTSConfig:
    return build_tts_config(x_tts_key, x_tts_base_url, x_tts_model, x_tts_voice)
