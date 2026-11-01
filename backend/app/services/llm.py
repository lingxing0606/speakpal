import json

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


# 流式接口在模型不可用时也要给一句预设追问
fallback_reply = _mock_reply


def build_messages(scene: dict, difficulty: str, history: list) -> list:
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
    return messages


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

    messages = build_messages(scene, difficulty, history)
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


# ---------------------------------------------------------------- 流式
class StreamUnavailable(Exception):
    """流还没开始就失败（网络、5xx、限流）：路由层降级为预设追问。"""


class ChatStream:
    """已经确认状态码正常的上游流；迭代得到文本片段，用完必须 close()。"""

    def __init__(self, client, resp):
        self._client = client
        self._resp = resp

    def __iter__(self):
        ctype = (self._resp.headers.get("content-type") or "").lower()
        if "text/event-stream" not in ctype:
            # 有的兼容服务忽略 stream=true，直接回整段 JSON：当成一个片段
            data = json.loads(self._resp.read())
            content = data["choices"][0]["message"]["content"]
            if content:
                yield content
            return
        for line in self._resp.iter_lines():
            line = (line or "").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except ValueError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            piece = (choices[0].get("delta") or {}).get("content")
            if piece:
                yield piece

    def close(self):
        try:
            self._resp.close()
        finally:
            self._client.close()


def open_chat_stream(
    scene: dict,
    difficulty: str,
    history: list,
    llm: LLMConfig | None = None,
) -> ChatStream:
    """先把上游连接和状态码确认好，再交给路由去流式转发。

    这样密钥被拒（UserKeyInvalid）、地址不安全（UnsafeBaseURL）仍能返回正常的 HTTP 错误码，
    不会变成「200 开流之后才报错」。其他失败抛 StreamUnavailable。
    """
    llm = llm or build_llm_config()
    if not llm.configured:
        raise StreamUnavailable("未配置密钥")
    check_base_url(llm.base_url)
    client = httpx.Client(timeout=httpx.Timeout(30.0))
    try:
        request = client.build_request(
            "POST",
            f"{llm.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {llm.api_key}"},
            json={
                "model": llm.model,
                "messages": build_messages(scene, difficulty, history),
                "temperature": 0.7,
                "stream": True,
            },
        )
        resp = client.send(request, stream=True)
    except Exception as exc:  # noqa: BLE001
        client.close()
        raise StreamUnavailable(type(exc).__name__) from exc
    if resp.status_code in (401, 403) and llm.from_user:
        resp.close()
        client.close()
        raise UserKeyInvalid()
    if resp.status_code >= 400:
        resp.close()
        client.close()
        raise StreamUnavailable(f"HTTP {resp.status_code}")
    return ChatStream(client, resp)
