"""用户数据的级联删除，供「清记录」「注销」「管理员删用户」「管理员全清」共用。

之前漏过 `drill_attempts`，这次把 `study_items`（学习卡，含用户原句）和 `notes`
一起带上：用户说「全部不保留」，笔记和学习卡同样是用户数据。
"""

from __future__ import annotations

from sqlalchemy.orm import Session as OrmSession

from ..models import (
    DrillAttempt,
    Note,
    PracticeSession,
    Report,
    ReviewEvent,
    StudyItem,
    Turn,
)


def delete_user_data(db: OrmSession, user_id: int) -> dict:
    """跟读 → 复习日志 → 学习卡 → 笔记 → 报告 → 轮次 → 会话，同一事务里删干净。"""
    session_ids = [
        row[0] for row in db.query(PracticeSession.id).filter(PracticeSession.user_id == user_id)
    ]
    deleted = {
        "sessions": 0,
        "turns": 0,
        "reports": 0,
        "drill_attempts": 0,
        "study_items": 0,
        "review_events": 0,
        "notes": 0,
    }
    if session_ids:
        report_ids = [
            row[0] for row in db.query(Report.id).filter(Report.session_id.in_(session_ids))
        ]
        if report_ids:
            deleted["drill_attempts"] = (
                db.query(DrillAttempt)
                .filter(DrillAttempt.report_id.in_(report_ids))
                .delete(synchronize_session=False)
            )
        deleted["reports"] = (
            db.query(Report)
            .filter(Report.session_id.in_(session_ids))
            .delete(synchronize_session=False)
        )
        deleted["turns"] = (
            db.query(Turn)
            .filter(Turn.session_id.in_(session_ids))
            .delete(synchronize_session=False)
        )
    # 学习卡可能来自这次练习，也可能是用户手动加的：统一按 user_id 清干净
    # 复习日志先删：它挂着 item_id，留着会指向已经不存在的卡
    deleted["review_events"] = (
        db.query(ReviewEvent)
        .filter(ReviewEvent.user_id == user_id)
        .delete(synchronize_session=False)
    )
    deleted["study_items"] = (
        db.query(StudyItem)
        .filter(StudyItem.user_id == user_id)
        .delete(synchronize_session=False)
    )
    deleted["notes"] = (
        db.query(Note).filter(Note.user_id == user_id).delete(synchronize_session=False)
    )
    deleted["sessions"] = (
        db.query(PracticeSession)
        .filter(PracticeSession.user_id == user_id)
        .delete(synchronize_session=False)
    )
    return {key: int(value or 0) for key, value in deleted.items()}
