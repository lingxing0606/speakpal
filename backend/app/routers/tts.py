"""语音合成（可选）。用户/服务端没配 key 时返回 409，前端回落到浏览器内置朗读。"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from ..models import User
from ..security import get_current_user
from ..services.llm_config import TTSConfig, get_tts_config, is_valid_base_url

router = APIRouter(prefix="/api", tags=["tts"])

MAX_TTS_CHARS = 500


class TTSIn(BaseModel):
    text: str
    voice: str | None = None


def _error(status: int, kind: str, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"kind": kind, "detail": detail})


@router.post("/tts")
def synthesize(
    body: TTSIn,
    user: User = Depends(get_current_user),
    tts: TTSConfig = Depends(get_tts_config),
):
    """把文本转成音频流（OpenAI 兼容 /audio/speech）。

    密钥只从请求头或 `.env` 读，不落库、不打日志。
    """
    text = (body.text or "").strip()
    if not text:
        return _error(400, "empty_text", "没有要朗读的内容")
    if len(text) > MAX_TTS_CHARS:
        return _error(400, "text_too_long", f"一次最多朗读 {MAX_TTS_CHARS} 个字符")

    if not tts.configured:
        return _error(
            409,
            "tts_not_configured",
            "没有配置语音合成密钥，将使用浏览器内置朗读",
        )
    if not is_valid_base_url(tts.base_url):
        return _error(502, "tts_unavailable", "语音合成地址不是 http(s) 地址")

    voice = (body.voice or "").strip() or tts.voice
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{tts.base_url.rstrip('/')}/audio/speech",
                headers={"Authorization": f"Bearer {tts.api_key}"},
                json={"model": tts.model, "input": text, "voice": voice},
            )
    except httpx.TimeoutException:
        return _error(502, "tts_unavailable", "语音合成超时，先用浏览器朗读")
    except httpx.HTTPError:
        return _error(502, "tts_unavailable", "语音合成服务不可达，先用浏览器朗读")

    if resp.status_code in (401, 403):
        return _error(502, "tts_key_invalid", "语音合成密钥无效或被拒绝，请到「设置」更换")
    if resp.status_code >= 400:
        return _error(502, "tts_unavailable", f"语音合成失败（HTTP {resp.status_code}）")

    media_type = resp.headers.get("content-type") or "audio/mpeg"
    return Response(content=resp.content, media_type=media_type)
