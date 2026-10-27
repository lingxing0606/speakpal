import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession

from ..db import get_db
from ..models import PracticeSession, User
from ..schemas import ReportOut
from ..security import get_current_user

router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/sessions/{session_id}/report", response_model=ReportOut)
def get_report(
    session_id: int,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    sess = db.get(PracticeSession, session_id)
    if not sess or sess.user_id != user.id or not sess.report:
        raise HTTPException(status_code=404, detail="报告不存在")
    rep = sess.report
    return ReportOut(
        report_id=rep.id,
        total_score=rep.total_score,
        dimensions=json.loads(rep.dimensions_json or "{}"),
        sentence_fixes=json.loads(rep.fixes_json or "[]"),
        comment=rep.comment,
        features=json.loads(rep.features_json or "{}"),
        note="分数由 AI 估算，仅供参考。",
    )
