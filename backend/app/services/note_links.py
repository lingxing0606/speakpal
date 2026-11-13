"""笔记知识关联：纯文本自动识别（AI 架构方案 §4.3 方案 A）。

保存笔记时按用户已学卡匹配正文，派生 `note_links`；阅读时一次返回命中词条
与位置，悬停不再发请求。匹配规则：
- 英文按词边界、大小写不敏感（cat 不命中 category）；
- 最长匹配优先（ice cream 优先于 ice）；
- 单字停用词（a/the/of…）不建链接；
- 每条笔记最多 50 个命中位置。
"""

from __future__ import annotations

import re

from sqlalchemy import func

from ..models import NoteLink, NoteLinkMute, ReviewEvent, StudyItem
from ..timeutil import utc_iso
from . import wordbank

MAX_NOTE_LINKS = 50
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

STOP_WORDS = {
    "a",
    "an",
    "the",
    "of",
    "to",
    "in",
    "on",
    "at",
    "for",
    "and",
    "or",
    "but",
    "is",
    "are",
    "am",
    "be",
    "been",
    "was",
    "were",
    "it",
    "this",
    "that",
    "these",
    "those",
    "i",
    "you",
    "he",
    "she",
    "we",
    "they",
    "my",
    "your",
    "his",
    "her",
    "our",
    "their",
    "as",
    "by",
    "with",
    "from",
    "not",
    "do",
    "does",
    "did",
    "so",
    "if",
    "then",
    "than",
    "too",
    "very",
    "can",
    "could",
    "will",
    "would",
    "should",
    "may",
    "might",
    "must",
    "have",
    "has",
    "had",
}


def phonetic_for(term: str) -> str:
    found = wordbank.find(term)
    return str(found[0].get("phonetic") or "") if found else ""


def _is_stopword(term: str) -> bool:
    return " " not in term and term.strip().lower() in STOP_WORDS


def _pattern(term: str):
    if _CJK_RE.search(term):
        return re.compile(re.escape(term))
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", re.IGNORECASE)


def match_note_links(body: str, items, muted_ids=()) -> list[dict]:
    """返回 [{item_id, term, start, end}]；items 需有 id / term。"""
    text = body or ""
    if not text.strip():
        return []
    muted = set(muted_ids or ())
    candidates = []
    for item in items:
        if item.id in muted:
            continue
        term = str(item.term or "").strip()
        if not term or _is_stopword(term):
            continue
        for match in _pattern(term).finditer(text):
            candidates.append(
                {
                    "item_id": int(item.id),
                    "term": term,
                    "start": match.start(),
                    "end": match.end(),
                }
            )

    candidates.sort(
        key=lambda c: (-(c["end"] - c["start"]), c["start"], c["item_id"])
    )
    accepted = []
    occupied = []
    for candidate in candidates:
        overlaps = any(
            candidate["start"] < end and start < candidate["end"]
            for start, end in occupied
        )
        if overlaps:
            continue
        occupied.append((candidate["start"], candidate["end"]))
        accepted.append(candidate)
        if len(accepted) >= MAX_NOTE_LINKS:
            break
    accepted.sort(key=lambda c: (c["start"], c["end"], c["item_id"]))
    return accepted


def refresh_note_links(db, note) -> None:
    """删掉旧链接后按当前正文重算；幂等，调用方负责 commit。"""
    db.query(NoteLink).filter(NoteLink.note_id == note.id).delete(
        synchronize_session=False
    )
    body = (note.body or "").strip()
    if not body:
        return
    items = db.query(StudyItem).filter(StudyItem.user_id == note.user_id).all()
    muted = [
        row[0]
        for row in db.query(NoteLinkMute.item_id)
        .filter(NoteLinkMute.note_id == note.id)
        .all()
    ]
    for match in match_note_links(note.body, items, muted):
        db.add(
            NoteLink(
                note_id=note.id,
                item_id=match["item_id"],
                term=match["term"],
                start=match["start"],
                end=match["end"],
            )
        )


def note_links_out(db, note) -> list[dict]:
    rows = (
        db.query(NoteLink)
        .filter(NoteLink.note_id == note.id)
        .order_by(NoteLink.start.asc(), NoteLink.end.asc())
        .all()
    )
    # 旧笔记没有派生过链接：第一次读取时补算，旧数据也能直接高亮
    if not rows and (note.body or "").strip():
        refresh_note_links(db, note)
        db.commit()
        rows = (
            db.query(NoteLink)
            .filter(NoteLink.note_id == note.id)
            .order_by(NoteLink.start.asc(), NoteLink.end.asc())
            .all()
        )
    if not rows:
        return []

    muted = {
        row[0]
        for row in db.query(NoteLinkMute.item_id)
        .filter(NoteLinkMute.note_id == note.id)
        .all()
    }
    item_ids = [row.item_id for row in rows]
    items = {
        row.id: row
        for row in db.query(StudyItem)
        .filter(StudyItem.user_id == note.user_id, StudyItem.id.in_(item_ids))
        .all()
    }
    review_rows = (
        db.query(ReviewEvent.item_id, func.max(ReviewEvent.created_at))
        .filter(
            ReviewEvent.user_id == note.user_id,
            ReviewEvent.item_id.in_(item_ids),
        )
        .group_by(ReviewEvent.item_id)
        .all()
    )
    reviewed = {row[0]: row[1] for row in review_rows}

    out = []
    for link in rows:
        item = items.get(link.item_id)
        if item is None or item.id in muted:
            continue
        last = reviewed.get(item.id)
        out.append(
            {
                "item_id": item.id,
                "term": item.term,
                "kind": item.kind,
                "meaning_zh": item.meaning_zh or "",
                "phonetic": phonetic_for(item.term),
                "example": item.example or "",
                "reps": int(item.reps or 0),
                "due_at": utc_iso(item.due_at),
                "last_reviewed_at": utc_iso(last) if last else None,
                "start": int(link.start),
                "end": int(link.end),
            }
        )
    return out
