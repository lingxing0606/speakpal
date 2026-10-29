import os

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session as OrmSession

from ..config import database_url_locked_by_env, settings
from ..db import get_db
from ..models import PracticeSession, Report, Turn, User
from ..schemas import AdminUserUpdateIn
from ..security import hash_password
from ..services.scenes import get_scene
from ..services.storage import (
    copy_current_to,
    normalize_target,
    storage_info,
    write_location,
)
from ..services.user_data import delete_user_data
from ..timeutil import utc_iso

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(x_admin_key: str | None = Header(default=None)):
    if not settings.admin_key or x_admin_key != settings.admin_key:
        raise HTTPException(status_code=401, detail="管理密钥错误")
    return True


def require_admin_ui(x_admin_key: str | None = Header(default=None)):
    """和 require_admin 一样，但失败返回 403。

    前端 axios 拦截器把任何 401 当作“登录失效”并登出；在设置页把管理密钥填错
    不该把用户踢出登录态，所以这两个“从界面调用”的接口用 403。
    """
    if not settings.admin_key or x_admin_key != settings.admin_key:
        raise HTTPException(status_code=403, detail="管理密钥错误")
    return True


@router.get("/stats")
def stats(_=Depends(require_admin), db: OrmSession = Depends(get_db)):
    users = db.query(func.count(User.id)).scalar() or 0
    sessions = db.query(func.count(PracticeSession.id)).scalar() or 0
    reports = db.query(func.count(Report.id)).scalar() or 0
    return {
        "users": users,
        "sessions": sessions,
        "reports": reports,
        "incomplete": max(sessions - reports, 0),
    }


@router.get("/users")
def user_stats(_=Depends(require_admin), db: OrmSession = Depends(get_db)):
    rows = db.query(User).order_by(User.id).all()
    out = []
    for u in rows:
        session_count = (
            db.query(func.count(PracticeSession.id))
            .filter(PracticeSession.user_id == u.id)
            .scalar()
            or 0
        )
        report_count = (
            db.query(func.count(Report.id))
            .join(PracticeSession, Report.session_id == PracticeSession.id)
            .filter(PracticeSession.user_id == u.id)
            .scalar()
            or 0
        )
        avg = (
            db.query(func.avg(Report.total_score))
            .join(PracticeSession, Report.session_id == PracticeSession.id)
            .filter(PracticeSession.user_id == u.id)
            .scalar()
        )
        out.append(
            {
                "id": u.id,
                "username": u.username,
                "nickname": u.nickname or u.username,
                "sessions": session_count,
                "reports": report_count,
                "avg_score": round(float(avg), 1) if avg is not None else None,
            }
        )
    return out


@router.get("/sessions")
def recent_sessions(
    limit: int = 20,
    _=Depends(require_admin),
    db: OrmSession = Depends(get_db),
):
    limit = max(1, min(limit, 100))
    rows = (
        db.query(PracticeSession)
        .order_by(PracticeSession.id.desc())
        .limit(limit)
        .all()
    )
    out = []
    for s in rows:
        scene = get_scene(s.scene_id)
        out.append(
            {
                "id": s.id,
                "user": (s.user.nickname or s.user.username) if s.user else "",
                "scene": scene["name"] if scene else s.scene_id,
                "status": "finished" if s.report else "incomplete",
                "score": s.report.total_score if s.report else None,
                "created_at": utc_iso(s.created_at),
            }
        )
    return out


class StorageIn(BaseModel):
    path: str
    copy_existing: bool = True


class AdminDeleteIn(BaseModel):
    scope: str = "records"  # records | account
    confirm: str | None = None


@router.put("/storage")
def update_storage(body: StorageIn, _=Depends(require_admin_ui)):
    """只写 data_location.json，重启后生效；不热切换。

    真实环境变量锁定了库地址时直接 409，不写配置、不假装成功——
    否则界面提示“重启后生效”，重启后却毫无变化，很难排查。
    """
    if database_url_locked_by_env():
        return JSONResponse(
            status_code=409,
            content={
                "kind": "env_override",
                "hint": "DATABASE_URL 由环境变量指定，配置文件不会生效",
                "current": storage_info(),
            },
        )
    try:
        target = normalize_target(body.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    parent = target.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"目标目录无法创建：{exc}")
    if not parent.exists() or not os.access(parent, os.W_OK):
        raise HTTPException(status_code=400, detail="目标目录不可写")

    copied = 0
    if body.copy_existing:
        try:
            copied = copy_current_to(target)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"复制现有数据失败：{exc}")
    try:
        write_location(target)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"写入配置失败：{exc}")

    return {
        "ok": True,
        "path": str(target),
        "copied_bytes": copied,
        "restart_required": True,
    }


@router.delete("/data")
def delete_all_data(
    body: AdminDeleteIn | None = Body(default=None),
    _=Depends(require_admin_ui),
    db: OrmSession = Depends(get_db),
):
    """演示前重置：删数据行，不删 .db 文件（engine 还握着旧文件）。"""
    scope = (body.scope if body else None) or "records"
    confirm = body.confirm if body else None
    if confirm != "删除":
        raise HTTPException(status_code=400, detail="请输入「删除」两个字确认")
    if scope not in ("records", "account"):
        raise HTTPException(status_code=400, detail="scope 只能是 records 或 account")

    deleted_reports = db.query(Report).delete(synchronize_session=False)
    deleted_turns = db.query(Turn).delete(synchronize_session=False)
    deleted_sessions = db.query(PracticeSession).delete(synchronize_session=False)
    deleted_users = 0
    if scope == "account":
        deleted_users = db.query(User).delete(synchronize_session=False)
    db.commit()
    return {
        "deleted_users": int(deleted_users or 0),
        "deleted_sessions": int(deleted_sessions or 0),
        "deleted_turns": int(deleted_turns or 0),
        "deleted_reports": int(deleted_reports or 0),
        "scope": scope,
    }


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    body: AdminUserUpdateIn,
    _=Depends(require_admin_ui),
    db: OrmSession = Depends(get_db),
):
    """管理员改某个用户：昵称 / 密码（不需要旧密码）。"""
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    nickname = (body.nickname or "").strip()
    password = body.password or ""
    if not nickname and not password:
        raise HTTPException(status_code=400, detail="昵称和密码至少改一项")
    if nickname:
        target.nickname = nickname
    if password:
        target.password_hash = hash_password(password)
    db.commit()
    db.refresh(target)
    return {
        "id": target.id,
        "username": target.username,
        "nickname": target.nickname or target.username,
        "password_changed": bool(password),
    }


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    _=Depends(require_admin_ui),
    db: OrmSession = Depends(get_db),
):
    """管理员删某个用户及其全部练习数据（不可恢复）。"""
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    deleted_sessions, deleted_turns, deleted_reports = delete_user_data(db, user_id)
    db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
    db.commit()
    return {
        "deleted_account": 1,
        "deleted_sessions": deleted_sessions,
        "deleted_turns": deleted_turns,
        "deleted_reports": deleted_reports,
        "user_id": user_id,
    }
