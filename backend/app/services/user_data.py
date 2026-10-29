"""用户数据的级联删除，供「注销自己」「管理员删用户」「管理员全清」共用。

注意：`drill_attempts` 存的是用户跟读时的原句，属于用户数据，必须一起删。
之前漏了这张表，清完数据后原句还能从库里捞回来——违背「全部不保留」。
"""

from __future__ import annotations

from sqlalchemy.orm import Session as OrmSession

from ..models import DrillAttempt, PracticeSession, Report, Turn


def delete_user_data(db: OrmSession, user_id: int) -> tuple[int, int, int, int]:
    """跟读记录 → 报告 → 轮次 → 会话，同一事务里删干净。

    返回 (sessions, turns, reports, drill_attempts)。
    """
    session_ids = [
        row[0] for row in db.query(PracticeSession.id).filter(PracticeSession.user_id == user_id)
    ]
    deleted_reports = 0
    deleted_turns = 0
    deleted_drills = 0
    if session_ids:
        report_ids = [
            row[0]
            for row in db.query(Report.id).filter(Report.session_id.in_(session_ids))
        ]
        if report_ids:
            deleted_drills = (
                db.query(DrillAttempt)
                .filter(DrillAttempt.report_id.in_(report_ids))
                .delete(synchronize_session=False)
            )
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
    return (
        int(deleted_sessions or 0),
        int(deleted_turns or 0),
        int(deleted_reports or 0),
        int(deleted_drills or 0),
    )
