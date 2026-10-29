"""练习类接口：跟读重说队列、最小对立对。"""

from __future__ import annotations

import difflib
import json
import re
from collections import defaultdict

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as OrmSession

from ..db import get_db
from ..models import DrillAttempt, PracticeSession, Report, User
from ..schemas import DrillAttemptIn, DrillAttemptOut, DrillItem, DrillsOut
from ..security import get_current_user
from ..services.pronunciation import MINIMAL_PAIR_SETS, check_pronunciation

router = APIRouter(prefix="/api", tags=["exercises"])

# 跟读相似度阈值：0.85 相当于只错一两个词，够用来判断「读成形了」
PASS_THRESHOLD = 0.85
MAX_ATTEMPT_CHARS = 500

_WORD_RE = re.compile(r"[a-z']+")


class PronCheckIn(BaseModel):
    target: str
    heard: str


def _words(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").lower())


def similarity(heard: str, target: str) -> float:
    a, b = _words(heard), _words(target)
    if not a or not b:
        return 0.0
    return round(difflib.SequenceMatcher(None, a, b).ratio(), 3)


def _load_session(session_id: int, user: User, db: OrmSession):
    sess = db.get(PracticeSession, session_id)
    if not sess or sess.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    if not sess.report:
        raise HTTPException(status_code=404, detail="这次练习还没有报告，先结束练习")
    return sess


def _fixes(rep: Report) -> list[dict]:
    try:
        data = json.loads(rep.fixes_json or "[]")
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def _feedback(sim: float) -> str:
    if sim >= PASS_THRESHOLD:
        return "这次跟读成形了，保持这个节奏。"
    if sim >= 0.6:
        return "很接近了，注意词序，把每个词都读出来。"
    return "差得比较多：先听一遍原句，再一个词一个词跟读。"


@router.get("/sessions/{session_id}/drills", response_model=DrillsOut)
def list_drills(
    session_id: int,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """把报告里的逐句改写做成跟读队列（目标句 = 改写后的句子）。"""
    sess = _load_session(session_id, user, db)
    rep = sess.report
    attempts = (
        db.query(DrillAttempt).filter(DrillAttempt.report_id == rep.id).all()
    )
    best: dict[int, float] = defaultdict(float)
    count: dict[int, int] = defaultdict(int)
    for a in attempts:
        best[a.item_index] = max(best[a.item_index], a.similarity)
        count[a.item_index] += 1

    items = []
    for i, fix in enumerate(_fixes(rep)):
        target = str(fix.get("better") or "").strip()
        if not target:
            continue
        b = best.get(i)
        items.append(
            DrillItem(
                index=i,
                source=str(fix.get("original") or ""),
                target=target,
                focus=str(fix.get("reason") or "")[:80],
                attempts=count.get(i, 0),
                best_similarity=b,
                passed=bool(b is not None and b >= PASS_THRESHOLD),
            )
        )
    return DrillsOut(report_id=rep.id, pass_threshold=PASS_THRESHOLD, items=items)


@router.post("/sessions/{session_id}/drills/{item_index}/attempt", response_model=DrillAttemptOut)
def submit_drill_attempt(
    session_id: int,
    item_index: int,
    body: DrillAttemptIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """提交一次跟读：比较转写与目标句的相似度，落库并返回反馈。"""
    sess = _load_session(session_id, user, db)
    rep = sess.report
    fixes = _fixes(rep)
    if item_index < 0 or item_index >= len(fixes):
        raise HTTPException(status_code=404, detail="没有这一条跟读")
    target = str(fixes[item_index].get("better") or "").strip()
    if not target:
        raise HTTPException(status_code=400, detail="这一条没有目标句")

    transcript = (body.transcript or "").strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="没有听到内容，再说一遍")
    if len(transcript) > MAX_ATTEMPT_CHARS:
        raise HTTPException(status_code=400, detail=f"太长了（上限 {MAX_ATTEMPT_CHARS} 字符）")

    sim = similarity(transcript, target)
    db.add(
        DrillAttempt(
            report_id=rep.id,
            item_index=item_index,
            transcript=transcript,
            similarity=sim,
        )
    )
    db.commit()

    rows = (
        db.query(DrillAttempt.similarity)
        .filter(DrillAttempt.report_id == rep.id, DrillAttempt.item_index == item_index)
        .all()
    )
    vals = [r[0] for r in rows]
    return DrillAttemptOut(
        index=item_index,
        similarity=sim,
        passed=sim >= PASS_THRESHOLD,
        attempts=len(vals),
        best_similarity=max(vals),
        feedback=_feedback(sim),
    )


@router.get("/pronunciation/minimal-pairs")
def minimal_pairs(user: User = Depends(get_current_user)):
    """两组最小对立对，各 10 组，供发音小游戏用。"""
    return {"sets": MINIMAL_PAIR_SETS}


@router.post("/pronunciation/check")
def pronunciation_check(
    body: PronCheckIn = Body(...),
    user: User = Depends(get_current_user),
):
    """按转写判断读的是目标词还是对手词（不用声学模型）。"""
    if not (body.target or "").strip():
        raise HTTPException(status_code=400, detail="缺少目标词")
    return check_pronunciation(body.target, body.heard)
