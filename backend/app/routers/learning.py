"""学习卡与笔记：主页的「要复习的单词 / 要改的说法」和用户自己的笔记。"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession

from ..db import get_db
from ..models import LearningItem, Note, User
from ..schemas import (
    LearningItemOut,
    LearningReviewIn,
    LearningSummaryOut,
    NoteIn,
    NoteOut,
)
from ..security import get_current_user
from ..services.learning import item_out
from ..services.srs import schedule
from ..timeutil import utc_iso

router = APIRouter(prefix="/api", tags=["learning"])

MAX_LIMIT = 100


def _item_out(row: LearningItem, now: datetime | None = None) -> LearningItemOut:
    return item_out(row, now)


def _item_or_404(db: OrmSession, user_id: int, item_id: int) -> LearningItem:
    row = db.get(LearningItem, item_id)
    if not row or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="学习卡不存在")
    return row


@router.get("/learning/items", response_model=list[LearningItemOut])
def list_learning_items(
    due: int = 0,
    type: str | None = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """due=1 只回到期的；type 可筛 spelling / natural / grammar。"""
    limit = max(1, min(limit, MAX_LIMIT))
    now = datetime.utcnow()
    query = db.query(LearningItem).filter(
        LearningItem.user_id == user.id, LearningItem.status == "active"
    )
    if due:
        query = query.filter(LearningItem.due_at <= now)
    if type:
        query = query.filter(LearningItem.type == type)
    rows = query.order_by(LearningItem.due_at.asc(), LearningItem.id.asc()).limit(limit).all()
    return [_item_out(row, now) for row in rows]


@router.get("/learning/summary", response_model=LearningSummaryOut)
def learning_summary(user: User = Depends(get_current_user), db: OrmSession = Depends(get_db)):
    now = datetime.utcnow()
    rows = (
        db.query(LearningItem)
        .filter(LearningItem.user_id == user.id, LearningItem.status == "active")
        .all()
    )
    return LearningSummaryOut(
        total=len(rows),
        due=sum(1 for r in rows if (r.due_at or now) <= now),
        spelling=sum(1 for r in rows if r.type == "spelling"),
        natural=sum(1 for r in rows if r.type == "natural"),
        grammar=sum(1 for r in rows if r.type == "grammar"),
    )


@router.get("/learning/items/{item_id}", response_model=LearningItemOut)
def get_learning_item(
    item_id: int,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    return _item_out(_item_or_404(db, user.id, item_id))


@router.post("/learning/items/{item_id}/review", response_model=LearningItemOut)
def review_learning_item(
    item_id: int,
    body: LearningReviewIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """复习反馈：again / hard / good / easy，按 SM-2 算下次到期时间。"""
    row = _item_or_404(db, user.id, item_id)
    try:
        ease, interval, reps, lapses, due_at = schedule(
            row.ease, row.interval_days or 0, row.reps or 0, row.lapses or 0, body.quality
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    row.ease = ease
    row.interval_days = interval
    row.reps = reps
    row.lapses = lapses
    row.due_at = due_at
    row.last_reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _item_out(row)


# ------------------------------------------------------------------ 笔记
def _note_out(row: Note) -> NoteOut:
    return NoteOut(
        id=row.id,
        title=row.title or "",
        content=row.content or "",
        learning_item_id=row.learning_item_id,
        session_id=row.session_id,
        created_at=utc_iso(row.created_at),
        updated_at=utc_iso(row.updated_at),
    )


def _note_or_404(db: OrmSession, user_id: int, note_id: int) -> Note:
    row = db.get(Note, note_id)
    if not row or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return row


@router.get("/notes", response_model=list[NoteOut])
def list_notes(user: User = Depends(get_current_user), db: OrmSession = Depends(get_db)):
    rows = (
        db.query(Note)
        .filter(Note.user_id == user.id)
        .order_by(Note.updated_at.desc())
        .all()
    )
    return [_note_out(row) for row in rows]


@router.post("/notes", response_model=NoteOut)
def create_note(
    body: NoteIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    content = (body.content or "").strip()
    title = (body.title or "").strip()
    if not title and not content:
        raise HTTPException(status_code=400, detail="笔记不能是空的")
    if body.learning_item_id is not None:
        _item_or_404(db, user.id, body.learning_item_id)
    row = Note(
        user_id=user.id,
        title=title,
        content=content,
        learning_item_id=body.learning_item_id,
        session_id=body.session_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _note_out(row)


@router.patch("/notes/{note_id}", response_model=NoteOut)
def update_note(
    note_id: int,
    body: NoteIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    row = _note_or_404(db, user.id, note_id)
    title = (body.title or "").strip()
    content = (body.content or "").strip()
    if not title and not content:
        raise HTTPException(status_code=400, detail="笔记不能是空的")
    row.title = title
    row.content = content
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _note_out(row)


@router.delete("/notes/{note_id}")
def delete_note(
    note_id: int,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    row = _note_or_404(db, user.id, note_id)
    db.delete(row)
    db.commit()
    return {"deleted": 1, "note_id": note_id}
