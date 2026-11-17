"""服务端语音转写接口（方案 §4.1）：音频只在内存里过一遍，不写磁盘。

前端录音（webm/opus）先由 `utils/wav.js` 转成 16 kHz 单声道 16-bit WAV 再上传；
这里校验格式/大小/时长后转发给 DeepSeek 或 OpenAI 兼容接口，失败统一
`{"text": "", "source": "none"}`，由前端回退浏览器识别。
"""

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from ..config import settings
from ..services.asr import MAX_AUDIO_BYTES, AudioInvalid, transcribe, validate_audio
from ..services.llm_config import LLMConfig, UserKeyInvalid, get_llm_config

router = APIRouter(prefix="/api", tags=["asr"])

KEY_INVALID_BODY = {
    "kind": "key_invalid",
    "detail": "模型密钥无效或被拒绝，请到「设置」更换密钥后再试",
}
KEY_REQUIRED_BODY = {
    "kind": "llm_not_configured",
    "detail": "还没有接入模型密钥",
}


@router.post("/asr")
def transcribe_audio(
    file: UploadFile = File(...),
    llm: LLMConfig = Depends(get_llm_config),
    x_asr_model: str | None = Header(default=None, alias="X-ASR-Model"),
):
    """上传一段 WAV（≤8 MiB、≤120 秒）并转写；上游失败不报错，返回 source=none。"""
    if not llm.configured:
        return JSONResponse(status_code=409, content=KEY_REQUIRED_BODY)
    data = file.file.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"音频不能超过 {MAX_AUDIO_BYTES // (1024 * 1024)} MiB",
        )
    try:
        validate_audio(data)
    except AudioInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        return transcribe(
            llm,
            data,
            filename=file.filename,
            model=(x_asr_model or settings.asr_model).strip(),
        )
    except UserKeyInvalid:
        return JSONResponse(status_code=502, content=KEY_INVALID_BODY)
