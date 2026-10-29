"""当前用户自己的数据操作。

两个入口，不重叠：
- `DELETE /api/me/account`：注销账号（连数据带用户行），前端手打「注销」确认。
- `DELETE /api/me/data`：只清练习记录，账号保留。
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as OrmSession

from ..db import get_db
from ..models import PracticeSession, Report, Turn, User
from ..security import get_current_user

router = APIRouter(prefix="/api/me", tags=["me"])


class DeleteDataIn(BaseModel):
    scope: str = "records"
    confirm: str | None = None


class DeleteAccountIn(BaseModel):
    confirm: str | None = None


def _delete_user_data(db: OrmSession, user_id: int) -> tuple[int, int, int]:
    """报告 → 轮次 → 会话，同一事务里删干净，返回 (sessions, turns, reports)。"""
    session_ids = [
        row[0] for row in db.query(PracticeSession.id).filter(PracticeSession.user_id == user_id)
    ]
    deleted_reports = 0
    deleted_turns = 0
    if session_ids:
        deleted_reports = (
            db.query(Report)
            .filter(Report.session_id.in_(session_ids))
            .delete(synchronize_session=False)
        )
        deleted_turns = (
            db.query(Turn)
            .filter(Turn.session_id.in_(session_ids))
            .delete(synchronize_session=False)
        )
    deleted_sessions = (
        db.query(PracticeSession)
        .filter(PracticeSession.user_id == user_id)
        .delete(synchronize_session=False)
    )
    return int(deleted_sessions or 0), int(deleted_turns or 0), int(deleted_reports or 0)


@router.delete("/account")
def delete_my_account(
    body: DeleteAccountIn | None = Body(default=None),
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """注销账号：删会话 / 轮次 / 报告，再删用户行。

    不可恢复，所以要求前端把用户手打的「注销」回传一次（前端已经校验，这里再挡一层，
    防止别的调用方误删）。删完后这个 token 对应不到用户，之后任何请求一律 401。
    """
    confirm = (body.confirm if body else None) or ""
    if confirm not in ("注销", "删除"):
        raise HTTPException(status_code=400, detail="注销不可恢复，请输入「注销」确认")

    deleted_sessions, deleted_turns, deleted_reports = _delete_user_data(db, user.id)
    deleted_account = db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
    db.commit()
    return {
        "deleted_account": int(deleted_account or 0),
        "deleted_sessions": deleted_sessions,
        "deleted_turns": deleted_turns,
        "deleted_reports": deleted_reports,
        "scope": "account",
    }


@router.delete("/data")
def delete_my_data(
    body: DeleteDataIn | None = Body(default=None),
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """只删练习记录，账号保留。注销请走 `/api/me/account`。"""
    scope = (body.scope if body else None) or "records"
    if scope == "account":
        raise HTTPException(
            status_code=400,
            detail="注销账号请调用 DELETE /api/me/account",
        )
    if scope != "records":
        raise HTTPException(status_code=400, detail="scope 只能是 records")

    deleted_sessions, deleted_turns, deleted_reports = _delete_user_data(db, user.id)
    db.commit()
    return {
        "deleted_sessions": deleted_sessions,
        "deleted_turns": deleted_turns,
        "deleted_reports": deleted_reports,
        "scope": "records",
    }
