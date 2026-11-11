"""Agent 编排：Planner–Executor–Critic（AI 架构方案 §三.1 方案 A）。

- Planner：会话开始时定 3 个目标（只能取自场景任务清单），并给出用词提示。
- Executor：仍是原来的流式对话，只是 system prompt 里多了目标与进度（llm.build_messages）。
- Critic：出报告前对比目标与全文，只可收紧关键词命中，不可放宽。

两条口径与项目现有做法一致：
- 目标取自 rules.TASK_CHECKS，达成由关键词规则算，不靠模型自评（可复算、可在报告里核对）。
- 任何一段模型失败都不阻塞主流程：Planner 退回规则目标，Critic 退回规则达成度。
"""

from __future__ import annotations

import json

import httpx

from .llm_config import LLMConfig, build_llm_config
from .outbound import UnsafeBaseURL, check_base_url
from .rules import evaluate_task
from .tools import call as call_tool

GOAL_COUNT = 3
FINISH_MIN_TURNS = 3  # 太早结束显得敷衍，最少聊三轮
FINISH_MAX_TURNS = 6  # 目标一直没达成就到 6 轮兜底
PLAN_TIMEOUT = 12.0
CRITIC_TIMEOUT = 20.0


def _loads_json(text: str):
    """从模型输出里取第一个 JSON 对象；容忍前后带解释文字。"""
    raw = text or ""
    start = raw.find("{")
    if start < 0:
        return None
    try:
        data, _end = json.JSONDecoder().raw_decode(raw[start:])
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _request_json(llm: LLMConfig, prompt: str, timeout: float):
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            f"{llm.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {llm.api_key}"},
            json={
                "model": llm.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            },
        )
        resp.raise_for_status()
        return _loads_json(resp.json()["choices"][0]["message"]["content"])


# ---------------------------------------------------------------- Planner
def checklist_labels(scene_id: str) -> list[str]:
    return call_tool("scene_checklist", scene_id=scene_id) or []


def _rule_plan(scene_id: str) -> dict:
    """模型不可用时的目标：按清单顺序取前三个，规则可复算。"""
    return {"goals": checklist_labels(scene_id)[:GOAL_COUNT], "focus": [], "source": "rule"}


def _sanitize_plan(raw, labels: list[str]) -> dict:
    """只认清单内的下标；三个不够就按清单顺序补齐，多余与非法值直接丢。"""
    goals: list[str] = []
    for item in (raw or {}).get("goals") or []:
        if isinstance(item, bool) or not isinstance(item, int):
            continue
        if 0 <= item < len(labels) and labels[item] not in goals:
            goals.append(labels[item])
        if len(goals) >= GOAL_COUNT:
            break
    if not goals:
        return {"goals": [], "focus": []}
    for label in labels:
        if len(goals) >= GOAL_COUNT:
            break
        if label not in goals:
            goals.append(label)
    focus = []
    for item in (raw or {}).get("focus") or []:
        text = str(item or "").strip()
        if text:
            focus.append(text[:20])
        if len(focus) >= 2:
            break
    return {"goals": goals, "focus": focus}


def _plan_prompt(scene: dict, difficulty: str, labels: list[str], weakness: list[str]) -> str:
    listed = "\n".join(f"{i} {label}" for i, label in enumerate(labels))
    weak = "；".join(weakness) if weakness else "（暂无历史弱项）"
    return (
        "You are the planner of an English speaking practice agent.\n"
        "Before the conversation starts you decide what this learner should achieve.\n"
        "Return ONLY valid JSON with this schema:\n"
        '{"goals":[0,1,2],"focus":[""],"comment":""}\n'
        "Rules:\n"
        f"- `goals` are exactly {GOAL_COUNT} indexes from the checklist below, no duplicates.\n"
        "- Pick the goals this learner is most likely to miss: the ones their recent weak\n"
        "  points suggest, then the ones easy to skip in small talk.\n"
        "- `focus` is 1-2 hints in Simplified Chinese on wording the learner needs\n"
        "  (for example \"用 I'd like ... 而不是 I want ...\"). Each under 20 characters.\n"
        "- Never output an index that is not in the checklist.\n"
        "- Write `focus` in Simplified Chinese (简体中文).\n\n"
        f"Scene: {scene['name']}\nDifficulty: {difficulty}\nChecklist:\n{listed}\n"
        f"Learner's recent weak points: {weak}"
    )


def plan_session(
    scene: dict, difficulty: str, weakness: list[str], llm: LLMConfig | None = None
) -> dict:
    """Planner：失败一律退回规则目标，绝不阻塞建会话。"""
    labels = checklist_labels(scene["id"])
    if not labels:
        return {"goals": [], "focus": [], "source": "rule"}
    llm = llm or build_llm_config()
    if not llm.configured:
        return _rule_plan(scene["id"])
    try:
        check_base_url(llm.base_url)
    except UnsafeBaseURL as exc:
        print(f"[agent] Planner 退回规则目标（地址不安全）：{exc.message}", flush=True)
        return _rule_plan(scene["id"])
    try:
        data = _request_json(llm, _plan_prompt(scene, difficulty, labels, weakness), PLAN_TIMEOUT)
    except Exception as exc:  # noqa: BLE001 - 规划失败不该让用户开不了练
        print(f"[agent] Planner 退回规则目标：{type(exc).__name__}", flush=True)
        return _rule_plan(scene["id"])
    plan = _sanitize_plan(data, labels)
    if not plan["goals"]:
        print("[agent] Planner 没给出可用目标，退回规则目标", flush=True)
        return _rule_plan(scene["id"])
    plan["source"] = "llm"
    return plan


# ---------------------------------------------------------------- 进度与结束时机
def progress(scene_id: str, plan: dict, user_text: str) -> dict:
    """按关键词规则算目标进度，返回合并后的 plan（goals / rule_hits / achieved / missing）。"""
    goals = [g for g in (plan.get("goals") or []) if isinstance(g, str) and g]
    if not goals:
        return dict(plan or {})
    hits = set(evaluate_task(scene_id, user_text).get("hits") or [])
    achieved = [g for g in goals if g in hits]
    out = dict(plan)
    out["goals"] = goals
    out["rule_hits"] = achieved
    out["achieved"] = achieved
    out["missing"] = [g for g in goals if g not in achieved]
    return out


def should_finish(plan: dict, user_count: int) -> bool:
    """目标都达成（至少三轮）或到 6 轮上限就提示可以出报告。

    没有目标的老会话保持原口径（4 轮），不改变已有行为。
    """
    goals = (plan or {}).get("goals") or []
    if not goals:
        return user_count >= 4
    if user_count >= FINISH_MAX_TURNS:
        return True
    return user_count >= FINISH_MIN_TURNS and not plan.get("missing")


# ---------------------------------------------------------------- Critic
def _critic_prompt(scene: dict, plan: dict, history: list) -> str:
    lines = []
    for t in history:
        if t.get("role") == "ai":
            lines.append(f"AI: {t.get('content', '')}")
        else:
            lines.append(f"User: {t.get('content', '')}")
    convo = "\n".join(lines)
    goals = json.dumps(plan.get("goals") or [], ensure_ascii=False)
    hits = json.dumps(plan.get("rule_hits") or [], ensure_ascii=False)
    frames = call_tool("get_frames", scene_id=scene["id"]) or []
    vetted = "\n".join(f"- {f.get('en', '')}" for f in frames if f.get("en"))
    return (
        "You are the critic of this English practice session. Check whether the learner\n"
        "actually achieved the planned goals, then tell them what is still missing.\n"
        "Return ONLY valid JSON with this schema:\n"
        '{"achieved":["<goal label>"],"comment":"<一句简体中文>"}\n'
        "Rules:\n"
        "- `achieved` may only contain labels copied from the goal list; never invent a goal.\n"
        "- A goal counts only if the learner really did it. Mentioning a keyword in passing,\n"
        "  or the AI saying it, does not count.\n"
        "- You may remove a goal the keyword check matched by mistake, but you must not add\n"
        "  a goal the learner never attempted.\n"
        "- `comment` is one short sentence in Simplified Chinese: what is still missing and\n"
        "  one English sentence they can try next time, using the vetted phrases below.\n"
        "- Write `comment` in Simplified Chinese (简体中文).\n\n"
        f"Scene: {scene['name']}\nGoal list: {goals}\n"
        f"Keyword check already matched: {hits}\n"
        f"Vetted phrases for this scene:\n{vetted}\n"
        f"Conversation:\n{convo}"
    )


def _rule_comment(missing: list[str]) -> str:
    """Critic 不可用时的中文收尾：只说还缺什么，不编英文改写。"""
    if not missing:
        return "三个目标都达到了，下次可以换个更难的场景继续练。"
    return "还差「" + "、".join(missing) + "」，下次练习先把这一项补上。"


def critic(
    scene: dict, plan: dict, history: list, user_text: str, llm: LLMConfig | None = None
) -> dict:
    """Critic：只可收紧关键词命中（只压不抬），模型失败退回规则达成度。"""
    base = progress(scene["id"], plan, user_text)
    if not base.get("goals"):
        return base
    base["review"] = "rule"
    base["comment"] = _rule_comment(base.get("missing") or [])
    llm = llm or build_llm_config()
    if not llm.configured:
        return base
    try:
        check_base_url(llm.base_url)
        data = _request_json(llm, _critic_prompt(scene, base, history), CRITIC_TIMEOUT)
    except Exception as exc:  # noqa: BLE001 - 复盘失败不影响出报告
        print(f"[agent] Critic 退回规则达成度：{type(exc).__name__}", flush=True)
        return base
    if not isinstance(data, dict):
        print("[agent] Critic 返回无法解析，退回规则达成度", flush=True)
        return base
    reviewed = [g for g in (data.get("achieved") or []) if isinstance(g, str)]
    if not reviewed:
        # 空列表多半是模型没按格式给；按无效处理，不去清空规则命中
        print("[agent] Critic 没给出达成项，退回规则达成度", flush=True)
        return base
    kept = [g for g in base["achieved"] if g in set(reviewed)]
    out = dict(base)
    out["achieved"] = kept
    out["missing"] = [g for g in base["goals"] if g not in kept]
    out["comment"] = str(data.get("comment") or "").strip()[:120] or _rule_comment(out["missing"])
    out["review"] = "llm"
    return out
