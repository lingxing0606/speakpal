"""学习卡与笔记（docs/design.md §16.5）。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession

from ..db import get_db
from ..models import Note, PracticeSession, StudyItem, User
from ..schemas import (
    NoteIn,
    NoteOut,
    StudyItemIn,
    StudyItemOut,
    StudyReviewIn,
)
from ..security import get_current_user
from ..services.srs import schedule
from ..services.study import KINDS, is_due, item_out, judge_spelling, normalize_related
from ..timeutil import utc_iso

router = APIRouter(prefix="/api", tags=["study"])

MAX_TERM = 128


def _item_or_404(db: OrmSession, user_id: int, item_id: int) -> StudyItem:
    row = db.get(StudyItem, item_id)
    if not row or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="学习卡不存在")
    return row


@router.get("/study/due", response_model=list[StudyItemOut])
def due_items(
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """今天要到期的卡：date(due_at) <= today，按到期时间升序。"""
    limit = max(1, min(limit, 200))
    now = datetime.utcnow()
    rows = (
        db.query(StudyItem)
        .filter(StudyItem.user_id == user.id)
        .order_by(StudyItem.due_at.asc(), StudyItem.id.asc())
        .all()
    )
    due = [row for row in rows if is_due(row, now)][:limit]
    return [item_out(row, now) for row in due]


@router.get("/study/summary")
def study_summary(user: User = Depends(get_current_user), db: OrmSession = Depends(get_db)):
    """首页两张卡的聚合接口：字段名按设计文档（*_count）。"""
    now = datetime.utcnow()
    rows = db.query(StudyItem).filter(StudyItem.user_id == user.id).all()
    notes_count = db.query(Note).filter(Note.user_id == user.id).count()
    return {
        "due_count": sum(1 for row in rows if is_due(row, now)),
        "notes_count": int(notes_count or 0),
        "total": len(rows),
        "word_count": sum(1 for row in rows if row.kind == "word"),
        "phrase_count": sum(1 for row in rows if row.kind == "phrase"),
        "spelling_count": sum(1 for row in rows if row.kind == "spelling"),
    }


@router.post("/study/items", response_model=StudyItemOut)
def create_item(
    body: StudyItemIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """手动加入学习清单（报告页「加入学习清单」走这条）。"""
    kind = (body.kind or "").strip().lower()
    if kind not in KINDS:
        raise HTTPException(status_code=400, detail="kind 只能是 word / phrase / spelling")
    term = (body.term or "").strip()
    if not term:
        raise HTTPException(status_code=400, detail="term 不能为空")
    _check_session_owner(db, user.id, body.source_session_id)
    row = StudyItem(
        user_id=user.id,
        kind=kind,
        term=term[:MAX_TERM],
        context=(body.context or "").strip(),
        meaning_zh=(body.meaning_zh or "").strip(),
        example=(body.example or "").strip(),
        related_json=__import__("json").dumps(normalize_related(body.related), ensure_ascii=False),
        source_session_id=body.source_session_id,
        due_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return item_out(row)


@router.post("/study/items/{item_id}/review", response_model=StudyItemOut)
def review_item(
    item_id: int,
    body: StudyReviewIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """句型/单词卡用 grade 自评三档；拼写卡传 answer，由服务端按编辑距离判档。"""
    row = _item_or_404(db, user.id, item_id)
    answer = (body.answer or "").strip()
    if answer:
        if row.kind != "spelling":
            raise HTTPException(status_code=400, detail="只有拼写卡需要默写判定")
        result, _distance = judge_spelling(answer, row.term)
    else:
        result = (body.grade or body.result or "").strip().lower()
    try:
        ease, interval, reps, lapses, due_at = schedule(
            row.ease, row.interval_days or 0, row.reps or 0, row.lapses or 0, result
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    row.ease = ease
    row.interval_days = interval
    row.reps = reps
    row.lapses = lapses
    row.due_at = due_at
    db.commit()
    db.refresh(row)
    out = item_out(row)
    out.last_result = result
    return out


@router.delete("/study/items/{item_id}")
def delete_item(
    item_id: int,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    row = _item_or_404(db, user.id, item_id)
    db.delete(row)
    db.commit()
    return {"deleted": 1, "item_id": item_id}


# ------------------------------------------------------------------ 笔记
def _note_out(row: Note) -> NoteOut:
    return NoteOut(
        id=row.id,
        title=row.title or "",
        body=row.body or "",
        session_id=row.session_id,
        created_at=utc_iso(row.created_at),
        updated_at=utc_iso(row.updated_at),
    )


def _check_session_owner(db: OrmSession, user_id: int, session_id: int | None) -> None:
    """笔记/学习卡可以挂到某次练习上，但只能挂自己的。"""
    if session_id is None:
        return
    session = db.get(PracticeSession, session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="会话不存在")


def _note_or_404(db: OrmSession, user_id: int, note_id: int) -> Note:
    row = db.get(Note, note_id)
    if not row or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return row


def _title_or_first_line(title: str | None, body: str) -> str:
    """不填标题就取正文首行前 40 字。"""
    text = (title or "").strip()
    if text:
        return text[:128]
    first = (body or "").strip().splitlines()[0] if (body or "").strip() else ""
    return first.strip()[:40]


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
    text = (body.body or "").strip()
    title = _title_or_first_line(body.title, text)
    if not text and not title:
        raise HTTPException(status_code=400, detail="笔记不能是空的")
    _check_session_owner(db, user.id, body.session_id)
    row = Note(user_id=user.id, title=title, body=text, session_id=body.session_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _note_out(row)


@router.get("/notes/{note_id}", response_model=NoteOut)
def get_note(
    note_id: int,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    return _note_out(_note_or_404(db, user.id, note_id))


@router.patch("/notes/{note_id}", response_model=NoteOut)
def update_note(
    note_id: int,
    body: NoteIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    row = _note_or_404(db, user.id, note_id)
    text = (body.body or "").strip()
    title = _title_or_first_line(body.title, text)
    if not text and not title:
        raise HTTPException(status_code=400, detail="笔记不能是空的")
    row.title = title
    row.body = text
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
