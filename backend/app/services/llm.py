import httpx

from .llm_config import LLMConfig, UserKeyInvalid, build_llm_config
from .outbound import check_base_url

MOCK_FOLLOW_UPS = {
    "job_interview": [
        "Thanks for sharing. What project are you most proud of, and what was your role in it?",
        "Interesting. What was the biggest challenge you faced in that project?",
        "Good. How would you handle a tight deadline with limited resources?",
    ],
    "cafe_order": [
        "Sure. Would you like that hot or iced?",
        "Do you want to add any pastry or snack with that?",
        "Great. Is that for here or to go?",
    ],
    "ielts_part1": [
        "What do you like most about your home?",
        "How long have you lived there?",
        "Would you like to move to a different place in the future? Why?",
    ],
}


def _mock_reply(scene_id: str, turn_index: int) -> str:
    lst = MOCK_FOLLOW_UPS.get(scene_id, ["Could you tell me more about that?"])
    return lst[min(max(turn_index, 0), len(lst) - 1)]


def chat_reply(
    scene: dict,
    difficulty: str,
    history: list,
    turn_index: int,
    llm: LLMConfig | None = None,
) -> tuple[str, bool]:
    """多轮对话。

    没带 key 时走 `.env` 兜底（不是“未配置”）；用户 key 被 401/403 拒绝时抛
    UserKeyInvalid，让路由层立刻告诉用户去换 key，而不是继续聊一轮假对话。

    返回 (回复, degraded)。degraded=True 表示模型没回上来、用的是预设追问，
    前端要提示用户，不能让人以为 AI 在正常工作。base_url 不安全时抛 UnsafeBaseURL。
    """
    llm = llm or build_llm_config()
    if not llm.configured:
        return _mock_reply(scene["id"], turn_index), True
    check_base_url(llm.base_url)

    system = (
        f"You are {scene['role']}. The user is an English learner practicing speaking.\n"
        "Ask short, natural, conversational questions. Ask only one question at a time.\n"
        "After the user answers, briefly acknowledge, then ask one relevant follow-up.\n"
        "Do not correct grammar during the conversation; correction is handled later.\n"
        f"Difficulty: {difficulty}. Keep it friendly."
    )
    messages = [{"role": "system", "content": system}]
    for t in history[-8:]:
        messages.append(
            {
                "role": "assistant" if t["role"] == "ai" else "user",
                "content": t["content"],
            }
        )
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{llm.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {llm.api_key}"},
                json={
                    "model": llm.model,
                    "messages": messages,
                    "temperature": 0.7,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            if not content:
                return _mock_reply(scene["id"], turn_index), True
            return content, False
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403) and llm.from_user:
            raise UserKeyInvalid() from exc
        print(f"[llm] 对话降级为预设追问：HTTP {exc.response.status_code}", flush=True)
        return _mock_reply(scene["id"], turn_index), True
    except Exception as exc:  # noqa: BLE001 - 对话中断比整个请求失败更糟，降级成预设追问
        print(f"[llm] 对话降级为预设追问：{type(exc).__name__}", flush=True)
        return _mock_reply(scene["id"], turn_index), True
