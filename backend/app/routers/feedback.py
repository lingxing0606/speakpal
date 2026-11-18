"""用户反馈：登录用户提交，管理台（/api/admin/feedback）查看。每人每天最多 20 条。"""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession

from ..db import get_db
from ..models import Feedback, User
from ..schemas import FeedbackIn
from ..security import get_current_user
from ..timeutil import utc_iso, utcnow

router = APIRouter(prefix="/api", tags=["feedback"])

KINDS = ("bug", "idea", "other")
DAILY_LIMIT = 20


@router.post("/feedback")
def submit_feedback(
    body: FeedbackIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="反馈内容不能为空")
    since = utcnow() - timedelta(days=1)
    recent = (
        db.query(Feedback)
        .filter(Feedback.user_id == user.id, Feedback.created_at >= since)
        .count()
    )
    if recent >= DAILY_LIMIT:
        raise HTTPException(status_code=429, detail="今天提交的反馈已经很多了，明天再来吧")
    row = Feedback(
        user_id=user.id,
        kind=body.kind if body.kind in KINDS else "other",
        content=content,
        page=body.page.strip(),
    )
    db.add(row)
    db.commit()
    return {"id": row.id, "created_at": utc_iso(row.created_at)}
