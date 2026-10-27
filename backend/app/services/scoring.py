import json
import re

import httpx

from ..config import settings


def _mock_report(history: list) -> dict:
    user_turns = [t for t in history if t["role"] == "user"]
    n = len(user_turns)
    base = 68 + min(n * 4, 16)
    return {
        "total": base,
        "dimensions": {
            "pronunciation": max(base - 6, 0),
            "fluency": min(base + 2, 100),
            "grammar_vocab": max(base - 2, 0),
            "task_completion": min(base + 6, 100),
        },
        "sentence_fixes": [
            {
                "original": "I am very interest in this job.",
                "better": "I'm very interested in this role.",
                "reason": "interest 是名词/动词；这里需要形容词 interested，搭配 in。",
            }
        ],
        "comment": "整体表达清楚，能完成场景任务；建议多用具体细节，减少填充词。",
        "note": "分数由 AI 估算，仅供参考。",
    }


def generate_report(scene: dict, difficulty: str, history: list) -> dict:
    if not settings.llm_api_key:
        return _mock_report(history)

    convo = "\n".join(
        f"{'AI' if t['role'] == 'ai' else 'User'}: {t['content']}" for t in history
    )
    prompt = (
        "You are an English speaking assessor. Score the learner's conversation.\n"
        "Return ONLY valid JSON matching this schema:\n"
        '{"total":0-100,"dimensions":{"pronunciation":0-100,"fluency":0-100,'
        '"grammar_vocab":0-100,"task_completion":0-100},'
        '"sentence_fixes":[{"original":"","better":"","reason":""}],'
        '"comment":"","note":"分数由 AI 估算，仅供参考。"}\n'
        "Guidelines:\n"
        "- pronunciation is an estimate based on the transcript; do not claim precise acoustic analysis.\n"
        "- Write `comment` and every `reason` in Simplified Chinese (简体中文).\n"
        "- Keep `original` and `better` in English: the learner's sentence and the improved version.\n"
        "- sentence_fixes: return 1-3 items, prioritize real errors or unnatural phrasing.\n\n"
        f"Scene: {scene['name']}\nDifficulty: {difficulty}\nConversation:\n{convo}"
    )
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json={
                    "model": settings.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                },
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            match = re.search(r"\{.*\}", text, re.S)
            if not match:
                return _mock_report(history)
            return json.loads(match.group(0))
    except Exception:
        return _mock_report(history)
