"""学习卡：校验模型给的诊断、从逐句改写兜底、写库去重。

模型输出不可全信：`trigger` 必须是用户真的说过的句子，`target` 必须非空，
类型只认 spelling / natural / grammar。不合法就丢掉，宁缺毋滥。
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from sqlalchemy.orm import Session as OrmSession

from ..models import LearningItem
from ..schemas import LearningItemOut
from ..timeutil import utc_iso

TYPES = ("spelling", "natural", "grammar")
MAX_ITEMS = 5
_WORD_RE = re.compile(r"[A-Za-z']+")


def _loads(raw, fallback):
    try:
        value = json.loads(raw or "")
    except (ValueError, TypeError):
        return fallback
    return value if isinstance(value, type(fallback)) else fallback


def item_out(row: LearningItem, now: datetime | None = None) -> LearningItemOut:
    """ORM → API 结构（含是否到期）。报告页、学习卡列表、复习接口共用。"""
    now = now or datetime.utcnow()
    return LearningItemOut(
        id=row.id,
        type=row.type,
        trigger=row.trigger,
        target=row.target,
        explanation=row.explanation or "",
        examples=_loads(row.examples_json, []),
        related=_loads(row.related_json, []),
        review_prompt=row.review_prompt or "",
        reps=int(row.reps or 0),
        lapses=int(row.lapses or 0),
        interval_days=int(row.interval_days or 0),
        due_at=utc_iso(row.due_at),
        due=(row.due_at or now) <= now,
        session_id=row.session_id,
        created_at=utc_iso(row.created_at),
    )


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower()).split())


def _user_corpus(history) -> str:
    parts = [_norm(t.get("content", "")) for t in history if t.get("role") == "user"]
    return " " + " ".join(parts) + " "


def _clean_related(raw):
    out = []
    if not isinstance(raw, list):
        return out
    for item in raw[:6]:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word") or "").strip()
        relation = str(item.get("relation") or "").strip().lower()
        meaning = str(item.get("meaning_zh") or "").strip()
        if not word:
            continue
        if relation not in ("synonym", "antonym", "similar", "family"):
            relation = "similar"
        out.append({"word": word, "relation": relation, "meaning_zh": meaning})
    return out


def sanitize_learning(raw, history):
    """模型给的 learning_items → 可入库的列表。"""
    if not isinstance(raw, list):
        return []
    corpus = _user_corpus(history)
    out = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "").strip().lower()
        if kind not in TYPES:
            continue
        trigger = str(item.get("trigger") or "").strip()
        target = str(item.get("target") or "").strip()
        explanation = str(item.get("explanation") or "").strip()
        if not target or not explanation:
            continue
        key = _norm(trigger)
        if not key or f" {key} " not in corpus:
            # 触发句必须是用户真说过的，否则这条诊断没有出处
            continue
        dedupe = (kind, target.lower())
        if dedupe in seen:
            continue
        seen.add(dedupe)
        examples = [
            str(x).strip()
            for x in (item.get("examples") or [])
            if str(x).strip()
        ][:3]
        out.append(
            {
                "type": kind,
                "trigger": trigger,
                "target": target,
                "explanation": explanation,
                "examples": examples,
                "related": _clean_related(item.get("related")),
                "review_prompt": str(item.get("review_prompt") or "").strip(),
            }
        )
        if len(out) >= MAX_ITEMS:
            break
    return out


def from_fixes(fixes):
    """模型没给 learning_items 时的兜底：把逐句改写当成「表达僵硬」卡。"""
    out = []
    for fix in fixes or []:
        original = str(fix.get("original") or "").strip()
        better = str(fix.get("better") or "").strip()
        reason = str(fix.get("reason") or "").strip()
        if not original or not better:
            continue
        out.append(
            {
                "type": "natural",
                "trigger": original,
                "target": better,
                "explanation": reason or "这句可以更自然一些。",
                "examples": [],
                "related": [],
                "review_prompt": "试着用更自然的说法把这句话说出来。",
            }
        )
        if len(out) >= MAX_ITEMS:
            break
    return out


def upsert_items(db: OrmSession, user_id: int, session_id: int | None, items):
    """写库并去重：同一个用户、同一类型、同一个目标只保留一条。"""
    if not items:
        return []
    existing = {
        (row.type, row.target.lower())
        for row in db.query(LearningItem)
        .filter(LearningItem.user_id == user_id, LearningItem.status == "active")
        .all()
    }
    added = []
    for item in items:
        key = (item["type"], item["target"].lower())
        if key in existing:
            continue
        row = LearningItem(
            user_id=user_id,
            session_id=session_id,
            type=item["type"],
            trigger=item["trigger"],
            target=item["target"],
            explanation=item["explanation"],
            examples_json=json.dumps(item.get("examples") or [], ensure_ascii=False),
            related_json=json.dumps(item.get("related") or [], ensure_ascii=False),
            review_prompt=item.get("review_prompt") or "",
        )
        db.add(row)
        existing.add(key)
        added.append(row)
    return added
