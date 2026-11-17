"""服务端语音转写（方案 §4.1，按官方文档口径修正）。

- DeepSeek 主机：`POST {base}/tools/asr`，multipart 字段名 `file`，返回
  `{request_id, text, duration_ms}`；只接受 16-bit PCM WAV 或 Ogg Opus。
- 其他 base_url：尝试 OpenAI 兼容的 `{base}/audio/transcriptions`（模型可配，默认 whisper-1）。
- 音频只在内存里处理，不写文件、不落盘；任何失败都降级成 `{text: "", source: "none"}`。
- 错误码 400/408/413/429/503/504 记进日志与 `reason`，前端据此回退浏览器识别。
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from .llm_config import LLMConfig, UserKeyInvalid
from .outbound import check_base_url

DEEPSEEK_HOST = "api.deepseek.com"
MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_AUDIO_MS = 120_000
# 官方支持的 WAV 采样率（16k 合法）
ALLOWED_RATES = (8000, 16000, 22050, 24000, 32000, 44100, 48000)
# 官方错误码 → 记录用的原因
ERROR_REASONS = {
    400: "bad_audio",
    408: "timeout",
    413: "too_large",
    429: "rate_limited",
    503: "unavailable",
    504: "gateway_timeout",
}
TIMEOUT = httpx.Timeout(120.0, connect=10.0)


class AudioInvalid(ValueError):
    """上传的音频不合规（格式/大小/时长），路由转 400。"""


def validate_audio(data: bytes) -> int | None:
    """校验音频并返回 WAV 时长毫秒；Ogg Opus 返回 None（不解析时长）。"""
    if not data:
        raise AudioInvalid("没有收到音频")
    if len(data) > MAX_AUDIO_BYTES:
        raise AudioInvalid(f"音频不能超过 {MAX_AUDIO_BYTES // (1024 * 1024)} MiB")
    if data.startswith(b"OggS"):
        return None
    return wav_duration_ms(data)


def wav_duration_ms(data: bytes) -> int:
    """解析 16-bit PCM 单声道 WAV：格式、采样率、时长都要合规，否则抛 AudioInvalid。"""
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise AudioInvalid("音频需要是 16-bit PCM WAV 或 Ogg Opus")
    fmt = None
    data_size = None
    pos = 12
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        size = int.from_bytes(data[pos + 4 : pos + 8], "little")
        body = pos + 8
        if chunk_id == b"fmt ":
            if size < 16 or body + 16 > len(data):
                raise AudioInvalid("WAV 的 fmt 段不完整")
            audio_format = int.from_bytes(data[body : body + 2], "little")
            channels = int.from_bytes(data[body + 2 : body + 4], "little")
            rate = int.from_bytes(data[body + 4 : body + 8], "little")
            bits = int.from_bytes(data[body + 14 : body + 16], "little")
            fmt = (audio_format, channels, rate, bits)
        elif chunk_id == b"data":
            data_size = min(size, max(0, len(data) - body))
            break
        pos = body + size + (size & 1)
    if fmt is None:
        raise AudioInvalid("WAV 缺少 fmt 段")
    audio_format, channels, rate, bits = fmt
    if audio_format != 1 or bits != 16 or channels != 1:
        raise AudioInvalid("只支持 16-bit PCM 单声道 WAV")
    if rate not in ALLOWED_RATES:
        raise AudioInvalid(
            "WAV 采样率只支持 " + " / ".join(str(r) for r in ALLOWED_RATES)
        )
    if not data_size:
        raise AudioInvalid("WAV 缺少音频数据")
    duration_ms = round(data_size * 1000 / (rate * channels * 2))
    if duration_ms <= 0:
        raise AudioInvalid("WAV 没有有效时长")
    if duration_ms > MAX_AUDIO_MS:
        raise AudioInvalid("音频不能超过 120 秒")
    return duration_ms


def _failure(reason: str) -> dict:
    return {"text": "", "source": "none", "reason": reason}


def _log(method: str, status: int) -> None:
    reason = ERROR_REASONS.get(status, f"http_{status}")
    print(f"[asr] {method} 失败：HTTP {status} ({reason})", flush=True)


def transcribe(
    llm: LLMConfig, data: bytes, filename: str | None = None, model: str | None = None
) -> dict:
    """转发到 DeepSeek 或 OpenAI 兼容转写；网络/HTTP 失败一律降级，不抛。"""
    check_base_url(llm.base_url)
    if urlparse(llm.base_url).hostname == DEEPSEEK_HOST:
        return _deepseek(llm, data, filename)
    return _openai_compatible(llm, data, filename, model)


def _deepseek(llm: LLMConfig, data: bytes, filename: str | None) -> dict:
    url = f"{llm.base_url.rstrip('/')}/tools/asr"
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(
                url,
                headers={"Authorization": f"Bearer {llm.api_key}"},
                files={"file": (filename or "audio.wav", data, "audio/wav")},
            )
    except httpx.HTTPError as exc:
        print(f"[asr] deepseek 网络失败：{type(exc).__name__}", flush=True)
        return _failure("network")
    if resp.status_code in (401, 403) and llm.from_user:
        raise UserKeyInvalid()
    if resp.status_code >= 400:
        _log("deepseek", resp.status_code)
        return _failure(ERROR_REASONS.get(resp.status_code, f"http_{resp.status_code}"))
    try:
        payload = resp.json()
    except ValueError:
        return _failure("bad_json")
    text = str(payload.get("text") or "").strip()
    if not text:
        return _failure("empty")
    duration = payload.get("duration_ms")
    return {
        "text": text,
        "source": "deepseek",
        "duration_ms": int(duration) if isinstance(duration, (int, float)) else 0,
    }


def _openai_compatible(
    llm: LLMConfig, data: bytes, filename: str | None, model: str | None
) -> dict:
    url = f"{llm.base_url.rstrip('/')}/audio/transcriptions"
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(
                url,
                headers={"Authorization": f"Bearer {llm.api_key}"},
                files={"file": (filename or "audio.wav", data, "audio/wav")},
                data={"model": (model or "whisper-1").strip()},
            )
    except httpx.HTTPError as exc:
        print(f"[asr] 兼容接口网络失败：{type(exc).__name__}", flush=True)
        return _failure("network")
    if resp.status_code in (401, 403) and llm.from_user:
        raise UserKeyInvalid()
    if resp.status_code >= 400:
        _log("compatible", resp.status_code)
        return _failure(ERROR_REASONS.get(resp.status_code, f"http_{resp.status_code}"))
    try:
        payload = resp.json()
    except ValueError:
        return _failure("bad_json")
    text = str(payload.get("text") or "").strip()
    if not text:
        return _failure("empty")
    return {"text": text, "source": "compatible"}
