from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session as OrmSession

from ..config import settings
from ..db import get_db
from ..models import PracticeSession, Report, User
from ..services.scenes import get_scene

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(x_admin_key: str | None = Header(default=None)):
    if not settings.admin_key or x_admin_key != settings.admin_key:
        raise HTTPException(status_code=401, detail="管理密钥错误")
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
                "created_at": s.created_at.isoformat(),
            }
        )
    return out
