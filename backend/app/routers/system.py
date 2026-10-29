"""系统与配置接口：模型密钥状态、连通性测试、数据位置。"""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, Depends

from ..config import settings
from ..models import User
from ..security import get_current_user
from ..services.llm_config import LLMConfig, get_llm_config, is_valid_base_url
from ..services.storage import storage_info

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/config/llm")
def get_llm_settings(user: User = Depends(get_current_user)):
    """只告诉前端“服务端有没有兜底密钥”和默认地址，绝不回显密钥。"""
    return {
        "env_configured": bool((settings.llm_api_key or "").strip()),
        "default_base_url": settings.llm_base_url,
        "default_model": settings.llm_model,
        # 服务端有没有兜底 TTS key：前端据此决定要不要试 /api/tts
        "tts_env_configured": bool((settings.tts_api_key or "").strip()),
        "default_tts_base_url": settings.tts_base_url,
        "default_tts_model": settings.tts_model,
        "default_tts_voice": settings.tts_voice,
    }


@router.post("/config/llm/test")
def test_llm(
    llm: LLMConfig = Depends(get_llm_config),
    user: User = Depends(get_current_user),
):
    """用请求头里的密钥发一次最小请求。

    失败一律返回 200 + ok=false：前端 axios 拦截器把任何 401 当成“登录失效”并登出，
    密钥错误不能走 401。
    """
    if not llm.configured:
        return {"ok": False, "error_kind": "invalid_key", "error": "未提供密钥"}
    if not is_valid_base_url(llm.base_url):
        return {"ok": False, "error_kind": "unreachable", "error": "Base URL 不是 http(s) 地址"}

    started = time.perf_counter()
    try:
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                f"{llm.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {llm.api_key}"},
                json={
                    "model": llm.model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                    "temperature": 0,
                },
            )
    except httpx.TimeoutException:
        return {"ok": False, "error_kind": "timeout", "error": "请求超时"}
    except httpx.HTTPError as exc:
        return {"ok": False, "error_kind": "unreachable", "error": type(exc).__name__}

    latency_ms = int(round((time.perf_counter() - started) * 1000))
    if resp.status_code in (401, 403):
        return {"ok": False, "error_kind": "invalid_key", "error": f"HTTP {resp.status_code}"}
    if resp.status_code >= 400:
        return {"ok": False, "error_kind": "unreachable", "error": f"HTTP {resp.status_code}"}

    try:
        model = resp.json().get("model") or llm.model
    except ValueError:
        model = llm.model
    return {"ok": True, "model": model, "latency_ms": latency_ms}


@router.get("/system/storage")
def get_storage(user: User = Depends(get_current_user)):
    """当前数据文件位置与状态。登录即可读，方便排错。"""
    return storage_info()
