"""学习卡：按 docs/design.md §16.4 从逐句纠错里自动建卡。

- `spelling` → kind=spelling（term = 拼错的正确词，related = 近义/反义/同类）
- `stiffness` → kind=phrase（term = 更自然的说法，context = 原句）
- `grammar` / `wordiness` 不自动建卡，报告里给「加入学习清单」由用户决定。
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session as OrmSession

from ..models import StudyItem
from ..schemas import StudyItemOut
from ..timeutil import utc_iso

KINDS = ("word", "phrase", "spelling")
AUTO_KINDS = {"spelling": "spelling", "stiffness": "phrase"}
MAX_TERM = 128

EMPTY_RELATED = {"synonyms": [], "antonyms": [], "similar": []}


def _loads(raw, fallback):
    try:
        value = json.loads(raw or "")
    except (ValueError, TypeError):
        return fallback
    return value if isinstance(value, type(fallback)) else fallback


def normalize_related(raw) -> dict:
    """related 只认 synonyms / antonyms / similar 三个键，值是字符串数组。"""
    out = {key: [] for key in EMPTY_RELATED}
    if not isinstance(raw, dict):
        return out
    for key in out:
        values = raw.get(key)
        if not isinstance(values, list):
            continue
        for value in values[:8]:
            text = str(value).strip()
            if text:
                out[key].append(text)
    return out


def item_out(row: StudyItem, now: datetime | None = None) -> StudyItemOut:
    now = now or datetime.utcnow()
    return StudyItemOut(
        id=row.id,
        kind=row.kind,
        term=row.term,
        context=row.context or "",
        meaning_zh=row.meaning_zh or "",
        example=row.example or "",
        related=_loads(row.related_json, dict(EMPTY_RELATED)),
        source_session_id=row.source_session_id,
        reps=int(row.reps or 0),
        lapses=int(row.lapses or 0),
        interval_days=float(row.interval_days or 0),
        due_at=utc_iso(row.due_at),
        due=is_due(row, now),
        created_at=utc_iso(row.created_at),
    )


def is_due(row: StudyItem, now: datetime | None = None) -> bool:
    """到期按日期比较：`date(due_at) <= today` 就算今天要复习。

    按时刻比会让凌晨打开首页是 0 个、也会让「again +10 分钟」当场掉出队列。
    """
    now = now or datetime.utcnow()
    due = row.due_at or now
    return due.date() <= now.date()


def _edit_distance(a: str, b: str) -> int:
    """拼写判分用：Levenshtein 距离。"""
    a, b = (a or "").lower(), (b or "").lower()
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def judge_spelling(answer: str, term: str) -> tuple[str, int]:
    """拼写卡默写判档：全对 good、差 1–2 个字母 hard、更多 again。"""
    distance = _edit_distance((answer or "").strip(), (term or "").strip())
    if distance == 0:
        return "good", distance
    if distance <= 2:
        return "hard", distance
    return "again", distance


def cards_from_fixes(fixes):
    """把一次报告的 sentence_fixes 变成待建卡列表（只建 spelling / stiffness）。"""
    cards = []
    for fix in fixes or []:
        if not isinstance(fix, dict):
            continue
        error_type = str(fix.get("error_type") or "grammar").strip().lower()
        kind = AUTO_KINDS.get(error_type)
        if not kind:
            continue
        original = str(fix.get("original") or "").strip()
        better = str(fix.get("better") or "").strip()
        natural = str(fix.get("natural") or "").strip()
        if not original:
            continue
        if kind == "spelling":
            term = str(fix.get("word") or "").strip()
        else:
            term = natural or better
        if not term:
            continue
        cards.append(
            {
                "kind": kind,
                "term": term[:MAX_TERM],
                "context": original,
                "meaning_zh": str(fix.get("reason") or "").strip(),
                "example": better if kind == "spelling" else (natural or better),
                "related": normalize_related(fix.get("related")),
            }
        )
    return cards


def create_cards(db: OrmSession, user_id: int, session_id: int | None, cards):
    """写库去重：同一用户、同 kind、同 term（小写）只留一条。"""
    if not cards:
        return []
    existing = {
        (row.kind, (row.term or "").lower())
        for row in db.query(StudyItem).filter(StudyItem.user_id == user_id).all()
    }
    added = []
    for card in cards:
        key = (card["kind"], card["term"].lower())
        if key in existing:
            continue
        row = StudyItem(
            user_id=user_id,
            kind=card["kind"],
            term=card["term"],
            context=card.get("context") or "",
            meaning_zh=card.get("meaning_zh") or "",
            example=card.get("example") or "",
            related_json=json.dumps(card.get("related") or EMPTY_RELATED, ensure_ascii=False),
            source_session_id=session_id,
            due_at=datetime.utcnow(),  # 草稿：立即可复习
        )
        db.add(row)
        existing.add(key)
        added.append(row)
    return added
