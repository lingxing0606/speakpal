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
    VocabAddIn,
    VocabAddOut,
    VocabOut,
)
from ..security import get_current_user
from ..services import wordbank
from ..services.srs import schedule
from ..services.study import KINDS, is_due, item_out, judge_spelling, normalize_related
from ..timeutil import utc_iso

router = APIRouter(prefix="/api", tags=["study"])

MAX_TERM = 128
# 学习卡来源（docs/design.md §16.1）：报告里加的 / 词库学的新词 / 复习时补的
SOURCES = ("report", "vocab", "review")
SOURCE_REPORT = "report"


def _item_or_404(db: OrmSession, user_id: int, item_id: int) -> StudyItem:
    row = db.get(StudyItem, item_id)
    if not row or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="学习卡不存在")
    return row


@router.get("/study/due", response_model=list[StudyItemOut])
def due_items(
    limit: int | None = None,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """今天要到期的卡：date(due_at) <= today，按到期时间升序。

    默认返回全部到期卡：`/study/summary` 的 `due_count` 统计所有到期卡，
    这里如果默认只给 50 张，首页说 60 个、学习页只能复习 50 个，两边对不上。
    `limit` 仍然可传（给需要分页的调用方），不传就不截断。
    """
    now = datetime.utcnow()
    rows = (
        db.query(StudyItem)
        .filter(StudyItem.user_id == user.id)
        .order_by(StudyItem.due_at.asc(), StudyItem.id.asc())
        .all()
    )
    due = [row for row in rows if is_due(row, now)]
    if limit is not None:
        due = due[: max(1, limit)]
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
    """手动加入学习清单（报告页「加入学习清单」走这条）。

    按 `(user_id, kind, term)` 去重：前端「已加入清单」只是内存状态，刷新后会恢复可点，
    重复点不能变成两张卡（否则首页到期数 +2、学习页同一个词问两遍）。
    已经存在时直接返回那张卡，前端据返回的 id 置灰即可。
    """
    kind = (body.kind or "").strip().lower()
    if kind not in KINDS:
        raise HTTPException(status_code=400, detail="kind 只能是 word / phrase / spelling")
    term = (body.term or "").strip()
    if not term:
        raise HTTPException(status_code=400, detail="term 不能为空")
    source = (body.source or SOURCE_REPORT).strip().lower()
    if source not in SOURCES:
        raise HTTPException(status_code=400, detail="source 只能是 report / vocab / review")
    _check_session_owner(db, user.id, body.source_session_id)

    wanted = term.lower()
    existing = next(
        (
            row
            for row in db.query(StudyItem)
            .filter(StudyItem.user_id == user.id, StudyItem.kind == kind)
            .all()
            if (row.term or "").lower() == wanted
        ),
        None,
    )
    if existing is not None:
        return item_out(existing)

    row = StudyItem(
        user_id=user.id,
        kind=kind,
        term=term[:MAX_TERM],
        context=(body.context or "").strip(),
        meaning_zh=(body.meaning_zh or "").strip(),
        example=(body.example or "").strip(),
        related_json=__import__("json").dumps(normalize_related(body.related), ensure_ascii=False),
        source_session_id=body.source_session_id,
        source=source,
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


# ---------------------------------------------------------------- 新词词库
# 每日新词上限（docs/design.md §18.3）；手动加入 / 报告自动建卡不计入
DAILY_NEW_WORDS = 20


def _learned_word_terms(db: OrmSession, user_id: int) -> set[str]:
    """已经进过学习清单的单词（小写），用来避开重复推荐。"""
    rows = (
        db.query(StudyItem.term)
        .filter(StudyItem.user_id == user_id, StudyItem.kind == "word")
        .all()
    )
    return {str(row[0]).strip().lower() for row in rows if row[0]}


def _vocab_used_today(db: OrmSession, user_id: int) -> int:
    """今天已经用词库加了几张新词卡（按 UTC 日期，和到期判定同一口径）。"""
    today = datetime.utcnow().date()
    rows = (
        db.query(StudyItem.created_at)
        .filter(
            StudyItem.user_id == user_id,
            StudyItem.kind == "word",
            StudyItem.source == "vocab",
        )
        .all()
    )
    return sum(1 for (created,) in rows if created and created.date() == today)


def _scope_or_default(raw: str | None, user: User) -> str:
    scope = (raw or "").strip().lower() or (user.word_scope or "").strip().lower()
    if scope not in wordbank.scope_ids():
        scope = wordbank.default_scope()
    return scope


@router.get("/study/vocab", response_model=VocabOut)
def vocab_next(
    scope: str | None = None,
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """「今天学几个新词」：取该范围里用户还没有卡的词，顺带给出范围和进度。"""
    scope_id = (scope or "").strip().lower() or None
    if scope_id and scope_id not in wordbank.scope_ids():
        raise HTTPException(status_code=400, detail="单词范围不存在")
    scope_id = _scope_or_default(scope_id, user)
    limit = max(1, min(limit, DAILY_NEW_WORDS))
    learned = _learned_word_terms(db, user.id)
    info = wordbank.totals(scope_id, learned)
    used_today = _vocab_used_today(db, user.id)
    return VocabOut(
        scope=scope_id,
        name=info["name"],
        desc=info["desc"],
        total=info["total"],
        learned=info["learned"],
        remaining=info["remaining"],
        daily_limit=DAILY_NEW_WORDS,
        used_today=used_today,
        remaining_today=max(0, DAILY_NEW_WORDS - used_today),
        items=wordbank.next_words(scope_id, learned, limit),
        scopes=wordbank.scopes_out(),
    )


@router.post("/study/vocab/add", response_model=VocabAddOut)
def vocab_add(
    body: VocabAddIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """把新词落成卡（kind=word, source=vocab），复用 §16 的 SRS，不另起调度。

    去重按 `(user_id, term, kind)`（词不分大小写）；每日新词上限 20，
    超出的部分不计入 `added`，用 `limited` 报给前端，而不是静默丢弃。
    """
    scope_id = (body.scope or "").strip().lower() or None
    if scope_id and scope_id not in wordbank.scope_ids():
        raise HTTPException(status_code=400, detail="单词范围不存在")
    scope_id = _scope_or_default(scope_id, user)

    learned = _learned_word_terms(db, user.id)
    requested: list[str] = []
    for raw in body.terms or []:
        term = str(raw or "").strip()
        if term:
            requested.append(term)
    if not requested and body.count:
        count = max(1, min(int(body.count), DAILY_NEW_WORDS))
        requested = [w["term"] for w in wordbank.next_words(scope_id, learned, count)]
    if not requested:
        raise HTTPException(status_code=400, detail="没有要加入的新词")

    used_today = _vocab_used_today(db, user.id)
    remaining_today = max(0, DAILY_NEW_WORDS - used_today)

    added_rows = []
    skipped = 0
    limited = 0
    seen = set()
    for term in requested:
        key = term.lower()
        if key in learned or key in seen:
            skipped += 1
            continue
        seen.add(key)
        found = wordbank.find(term, scope_id)
        if not found:
            skipped += 1
            continue
        if len(added_rows) >= remaining_today:
            limited += 1
            continue
        entry, found_scope = found
        card = wordbank.word_out(entry, found_scope)
        row = StudyItem(
            user_id=user.id,
            kind="word",
            term=card["term"][:MAX_TERM],
            context="",
            meaning_zh=(card["pos"] + " " + card["meaning_zh"]).strip(),
            example=card["example"],
            related_json=__import__("json").dumps(card["related"], ensure_ascii=False),
            source="vocab",
            due_at=datetime.utcnow(),  # 新词当天进复习队列
        )
        db.add(row)
        added_rows.append(row)

    if not added_rows and not skipped and not limited:
        raise HTTPException(status_code=404, detail="词库里没有这些词")
    db.commit()
    for row in added_rows:
        db.refresh(row)
    return VocabAddOut(
        added=len(added_rows),
        skipped=skipped,
        limited=limited,
        daily_limit=DAILY_NEW_WORDS,
        used_today=used_today + len(added_rows),
        remaining_today=max(0, remaining_today - len(added_rows)),
        items=[item_out(row) for row in added_rows],
    )


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
