"""Agent 编排层的工具注册表：只读 Python 函数 + OpenAI function calling schema。

两种用法：
- 编排代码按名字直接调（Planner / Critic），参数由代码保证；
- 出报告时把 `openai_tools()` 交给模型，让模型自己决定调哪些。模型传来的参数
  在这里按 schema 校验：多余参数丢弃，缺必填 / 类型不对返回 {"error": ...} 给
  模型自己修正，不抛异常。
所有工具都只读：不写库、不发网络请求；工具执行失败也不抛给调用方。
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
    "scene_checklist": {
        "func": _scene_checklist,
        "schema": {"scene_id": str},
        "description": "List the communication goals (checklist labels) for a practice scene.",
        "parameters": {
            "type": "object",
            "properties": {
                "scene_id": {
                    "type": "string",
                    "description": "Scene id, for example cafe_order or job_interview.",
                }
            },
            "required": ["scene_id"],
        },
    },
    "get_frames": {
        "func": _get_frames,
        "schema": {"scene_id": str},
        "description": "Vetted English sentence frames for a scene, with Chinese hints.",
        "parameters": {
            "type": "object",
            "properties": {
                "scene_id": {
                    "type": "string",
                    "description": "Scene id, for example cafe_order or job_interview.",
                }
            },
            "required": ["scene_id"],
        },
    },
    "recent_weakness": {
        "func": _recent_weakness,
        "schema": {"db": object, "user_id": int},
        "description": (
            "The learner's recent error reasons from scored reports. "
            "The server injects the learner identity; call it with no arguments."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "lookup_word": {
        "func": _lookup_word,
        "schema": {"term": str},
        "description": "Look up a word in the built-in vocabulary bank.",
        "parameters": {
            "type": "object",
            "properties": {
                "term": {
                    "type": "string",
                    "description": "One English word, for example serendipity.",
                }
            },
            "required": ["term"],
        },
    },
    "grammar_card": {
        "func": _grammar_card,
        "schema": {"query": str},
        "description": "Find one grammar card by keyword (point, rule or example sentence).",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword or rule name, for example present perfect.",
                }
            },
            "required": ["query"],
        },
    },
}


def openai_tools(names: list[str]) -> list[dict]:
    """把指定工具转成 OpenAI function calling 的 tools 参数；未知名字跳过。"""
    out = []
    for name in names:
        tool = TOOLS.get(name)
        if not tool:
            continue
        out.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
        )
    return out


def call(name: str, **kwargs):
    """按名字调工具：按 schema 校验参数、隔离异常、打印一行审计日志。

    参数不合法时返回 {"error": ...}（给模型自己修正），不抛；
    工具执行异常仍返回 None，调用方的 `or []` 兜底照旧。
    """
    tool = TOOLS.get(name)
    if not tool:
        return {"error": f"未知工具：{name}"}
    args = {}
    invalid = []
    for key, expected in tool["schema"].items():
        if key not in kwargs:
            continue
        value = kwargs[key]
        # bool 是 int 的子类：user_id=True 这类值不能当整数放过去
        if isinstance(value, bool) and expected is not bool:
            invalid.append(key)
            continue
        if not isinstance(value, expected):
            invalid.append(key)
            continue
        args[key] = value
    missing = [key for key in tool["schema"] if key not in args]
    if missing:
        detail = f"工具 {name} 缺少参数：{', '.join(missing)}"
        if invalid:
            detail += f"（类型不对：{', '.join(invalid)}）"
        return {"error": detail}
    # 多余参数在 args 组装时已经丢掉
    started = time.perf_counter()
    try:
        result = tool["func"](**args)
    except Exception as exc:  # noqa: BLE001 - 工具失败只降级，不冒泡
        print(f"[tools] {name} 失败：{type(exc).__name__}", flush=True)
        return None
    cost = (time.perf_counter() - started) * 1000
    print(f"[tools] {name} ok {cost:.0f}ms", flush=True)
    return result
