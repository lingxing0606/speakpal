import httpx

from ..config import settings

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


def chat_reply(scene: dict, difficulty: str, history: list, turn_index: int) -> str:
    if not settings.llm_api_key:
        return _mock_reply(scene["id"], turn_index)

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
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json={
                    "model": settings.llm_model,
                    "messages": messages,
                    "temperature": 0.7,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return _mock_reply(scene["id"], turn_index)
