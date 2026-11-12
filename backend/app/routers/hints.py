"""手动输入提示接口（任务二后端）。

按「AI 刚问的那句」生成 1–3 条能照着说的句子；模型不可用时回退场景通用句型，
任何失败都不影响输入框（前端只在气泡里标「通用句型」）。
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession

from ..db import get_db
from ..models import PracticeSession, User
from ..schemas import HintsIn, HintsOut
from ..security import get_current_user
from ..services.hints import generate_hints
from ..services.llm_config import LLMConfig, get_llm_config
from ..services.scenes import get_scene

router = APIRouter(prefix="/api", tags=["hints"])


def _load_plan(sess: PracticeSession) -> dict:
    """会话的本场计划；老会话没有 plan 时给空计划。"""
    try:
        data = json.loads(sess.plan_json or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


@router.post("/sessions/{session_id}/hint", response_model=HintsOut)
def get_hint(
    session_id: int,
    body: HintsIn | None = None,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
    llm: LLMConfig = Depends(get_llm_config),
):
    """练习中「这么说更顺」的提示：缓存 → 模型 → 通用句型，从不报错打断练习。

    `nonce` 由「换一批」带：参与缓存 key 并绕过缓存命中，强制重新生成。
    """
    sess = db.get(PracticeSession, session_id)
    if not sess or sess.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    if sess.status != "active":
        raise HTTPException(status_code=400, detail="会话已结束")
    scene = get_scene(sess.scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")
    history = [{"role": t.role, "content": t.content} for t in sess.turns]
    return HintsOut(
        **generate_hints(
            scene,
            sess.difficulty,
            _load_plan(sess),
            history,
            db,
            llm,
            (body.nonce or "").strip() if body else "",
        )
    )
