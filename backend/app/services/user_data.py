"""用户数据的级联删除，供「注销自己」和「管理员删用户」共用。"""

from __future__ import annotations

from sqlalchemy.orm import Session as OrmSession

from ..models import PracticeSession, Report, Turn


def delete_user_data(db: OrmSession, user_id: int) -> tuple[int, int, int]:
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
