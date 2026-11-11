"""Agent 编排层的工具注册表：编排代码按名字调用的只读 Python 函数。

本轮不要求模型自己发起调用（不走 OpenAI function calling），所以这里只做三件事：
「名字 → 函数 + 必填参数校验 + 一行审计日志」。所有工具都只读：不写库、不发网络请求。
工具失败不抛给调用方——Agent 的每一段都不该因为「查不到一个词」而中断。
"""

from __future__ import annotations

import json
import time

from ..models import PracticeSession, Report
from . import library, wordbank
from .rules import TASK_CHECKS
from .scenes import get_frames


def _scene_checklist(scene_id: str) -> list[str]:
    """场景交际功能清单的标签（与 rules.TASK_CHECKS 同源，Planner 只能从中挑目标）。"""
    return [label for label, _keywords in TASK_CHECKS.get(scene_id) or []]


def _get_frames(scene_id: str) -> list[dict]:
    return get_frames(scene_id) or []


def _recent_weakness(db, user_id: int, limit: int = 3) -> list[str]:
    """最近几份计分报告的错因（error_type + reason），给 Planner 挑目标用。"""
    size = max(1, min(int(limit or 3), 5))
    rows = (
        db.query(Report)
        .join(PracticeSession, Report.session_id == PracticeSession.id)
        .filter(PracticeSession.user_id == user_id, Report.source == "llm")
        .order_by(Report.id.desc())
        .limit(size)
        .all()
    )
    out = []
    for rep in rows:
        try:
            fixes = json.loads(rep.fixes_json or "[]")
        except ValueError:
            fixes = []
        for fix in fixes if isinstance(fixes, list) else []:
            if not isinstance(fix, dict):
                continue
            reason = str(fix.get("reason") or "").strip()
            if not reason:
                continue
            kind = str(fix.get("error_type") or "grammar").strip().lower()
            out.append(f"{kind}: {reason[:40]}")
    return out[:5]


def _lookup_word(term: str, scope: str | None = None) -> dict | None:
    hit = wordbank.find(term, scope)
    if not hit:
        return None
    entry, found = hit
    return wordbank.word_out(entry, found)


def _grammar_card(query: str) -> dict | None:
    """按关键词找一张语法卡：先比语法点，再比规则与例句。"""
    needle = (query or "").strip().lower()
    if not needle:
        return None
    cards = library.grammar_cards()
    for card in cards:
        if needle in card["point"].lower():
            return card
    for card in cards:
        if needle in f"{card['rule']} {card['wrong']} {card['right']}".lower():
            return card
    return None


TOOLS = {
    "scene_checklist": {"func": _scene_checklist, "schema": {"scene_id": str}},
    "get_frames": {"func": _get_frames, "schema": {"scene_id": str}},
    "recent_weakness": {"func": _recent_weakness, "schema": {"db": object, "user_id": int}},
    "lookup_word": {"func": _lookup_word, "schema": {"term": str}},
    "grammar_card": {"func": _grammar_card, "schema": {"query": str}},
}


def call(name: str, **kwargs):
    """按名字调工具：校验必填参数、隔离异常、打印一行审计日志。"""
    tool = TOOLS.get(name)
    if not tool:
        raise KeyError(f"未知工具：{name}")
    missing = [key for key in tool["schema"] if key not in kwargs]
    if missing:
        raise ValueError(f"工具 {name} 缺少参数：{', '.join(missing)}")
    started = time.perf_counter()
    try:
        result = tool["func"](**kwargs)
    except Exception as exc:  # noqa: BLE001 - 工具失败只降级，不冒泡
        print(f"[tools] {name} 失败：{type(exc).__name__}", flush=True)
        return None
    cost = (time.perf_counter() - started) * 1000
    print(f"[tools] {name} ok {cost:.0f}ms", flush=True)
    return result
