"""当前用户自己的资料与数据。

- `PATCH /api/me/profile`：改昵称 / 改密码（改密码要旧密码）。
- `DELETE /api/me/data`：只清练习记录，账号保留。
- `DELETE /api/me/account`：注销账号（连数据带用户行），前端手打「注销」确认。
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as OrmSession

from ..db import get_db
from ..models import PracticeSession, Report, User
from ..schemas import (
    PreferencesIn,
    PreferencesOut,
    ProfileOut,
    ProfileUpdateIn,
    RecommendationOut,
    UserOut,
)
from ..security import (
    check_password_rule,
    create_token,
    get_current_user,
    hash_password,
    verify_password,
)
from ..services import wordbank
from ..services.user_data import delete_user_data

router = APIRouter(prefix="/api/me", tags=["me"])

DIFFICULTIES = ("easy", "medium", "hard")


class DeleteDataIn(BaseModel):
    scope: str = "records"
    confirm: str | None = None


class DeleteAccountIn(BaseModel):
    confirm: str | None = None


@router.patch("/profile", response_model=ProfileOut)
def update_my_profile(
    body: ProfileUpdateIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """改昵称或密码。改密码必须带当前密码，防止拿着别人电脑直接改。

    改密码会让 `token_version` +1：其他设备上签发的 token 立即 401，
    当前设备拿到响应里新签发的 `token` 继续用，不用重新登录。
    """
    nickname = (body.nickname or "").strip()
    password = body.password or ""
    if not nickname and not password:
        raise HTTPException(status_code=400, detail="昵称和密码至少改一项")

    password_changed = False
    if password:
        if not body.current_password:
            raise HTTPException(status_code=400, detail="改密码需要提供当前密码")
        if not verify_password(body.current_password, user.password_hash):
            raise HTTPException(status_code=400, detail="当前密码不正确")
        check_password_rule(password)
        user.password_hash = hash_password(password)
        user.token_version = int(user.token_version or 0) + 1
        password_changed = True
    if nickname:
        user.nickname = nickname

    db.commit()
    db.refresh(user)
    out = ProfileOut.model_validate(user)
    if password_changed:
        out.token = create_token(user.id, user.token_version)
    return out


@router.get("/settings", response_model=PreferencesOut)
def get_my_settings(user: User = Depends(get_current_user)):
    """设置页偏好：练习难度、新词词库范围。跟着账号走，换设备也在。"""
    return PreferencesOut(
        practice_difficulty=(user.practice_difficulty or "medium"),
        word_scope=(user.word_scope or wordbank.default_scope()),
    )


@router.patch("/settings", response_model=PreferencesOut)
def update_my_settings(
    body: PreferencesIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """局部更新；取值不在枚举内返 400。切换词库只影响之后取的新词，已学的卡不动。"""
    if body.practice_difficulty is not None:
        difficulty = body.practice_difficulty.strip().lower()
        if difficulty not in DIFFICULTIES:
            raise HTTPException(status_code=400, detail="难度只能是 easy / medium / hard")
        user.practice_difficulty = difficulty
    if body.word_scope is not None:
        scope = body.word_scope.strip().lower()
        if scope not in wordbank.scope_ids():
            raise HTTPException(status_code=400, detail="单词范围不存在")
        user.word_scope = scope
    db.commit()
    db.refresh(user)
    return PreferencesOut(
        practice_difficulty=(user.practice_difficulty or "medium"),
        word_scope=(user.word_scope or wordbank.default_scope()),
    )


@router.get("/recommendation", response_model=RecommendationOut)
def get_recommendation(
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """按上一份报告的 band 推难度：连续练上去就自动加难。"""
    last = (
        db.query(PracticeSession)
        .join(Report, Report.session_id == PracticeSession.id)
        .filter(PracticeSession.user_id == user.id)
        .order_by(PracticeSession.id.desc())
        .first()
    )
    if not last or not last.report:
        return RecommendationOut(
            recommended_difficulty="medium",
            reason="还没有带分数的记录，先从中等开始",
        )
    band = last.report.band
    if band is None:
        return RecommendationOut(
            recommended_difficulty="medium",
            last_scene_id=last.scene_id,
            reason="上一份是示例报告（没有分数），先保持中等",
        )
    if band >= 7.0:
        difficulty, reason = "hard", f"上次 band {band}，可以试困难档"
    elif band >= 5.5:
        difficulty, reason = "medium", f"上次 band {band}，保持中等"
    else:
        difficulty, reason = "easy", f"上次 band {band}，先用简单档把句子说完整"
    return RecommendationOut(
        recommended_difficulty=difficulty,
        last_band=band,
        cefr=last.report.cefr,
        last_scene_id=last.scene_id,
        reason=reason,
    )


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
    if confirm != "注销":
        raise HTTPException(status_code=400, detail="注销不可恢复，请输入「注销」确认")

    deleted = delete_user_data(db, user.id)
    deleted_account = db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
    db.commit()
    return {
        "deleted_account": int(deleted_account or 0),
        "deleted_sessions": deleted["sessions"],
        "deleted_turns": deleted["turns"],
        "deleted_reports": deleted["reports"],
        "deleted_drill_attempts": deleted["drill_attempts"],
        "deleted_study_items": deleted["study_items"],
        "deleted_notes": deleted["notes"],
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

    deleted = delete_user_data(db, user.id)
    db.commit()
    return {
        "deleted_sessions": deleted["sessions"],
        "deleted_turns": deleted["turns"],
        "deleted_reports": deleted["reports"],
        "deleted_drill_attempts": deleted["drill_attempts"],
        "deleted_study_items": deleted["study_items"],
        "deleted_notes": deleted["notes"],
        "scope": "records",
    }
