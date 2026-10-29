import json
import re

import httpx

from evaluation.bands import DIMENSIONS, report_bands, round_band

from .llm_config import LLMConfig, UserKeyInvalid, build_llm_config

# 报告卡上的注脚：必须是真实口径。之前写「分数由 AI 估算」，
# 与同一张卡上的「模型分与可测规则分融合」「评分依据」自相矛盾，评委一看就穿。
DEFAULT_NOTE = "分数由模型分与可测规则分融合得出，仅供参考。"
MOCK_NOTE = "示例报告（模型不可用） · 本次不计分"
MAX_FIXES = 3

# 降级原因，两种会落库：
# - not_configured：finish 时没有任何可用 key（练习已结束，不拦，给示例报告）
# - unavailable：服务不可用 / 超时
# - invalid_key：仅指 **服务端 .env 兜底密钥** 被拒（运维问题），不用于用户自己的 key。
#   用户请求头里的 key 被拒走 502 key_invalid，不生成报告。
MOCK_NOT_CONFIGURED = "not_configured"
MOCK_UNAVAILABLE = "unavailable"
MOCK_INVALID_KEY = "invalid_key"

_LETTERS_RE = re.compile(r"[A-Za-z']+")
_JSON_RE = re.compile(r"\{.*\}", re.S)


def _norm(text: str) -> str:
    """比较用户原句用：忽略大小写、标点和多余空格。"""
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower()).split())


def _user_corpus(history) -> str:
    parts = [_norm(t.get("content", "")) for t in history if t.get("role") == "user"]
    return " " + " ".join(parts) + " "


def _sanitize_fixes(raw, history):
    """只保留用户真的说过的话。

    `original` 必须能在用户发言里找到（忽略大小写/标点），否则丢弃——
    报告不能虚构用户没说过的话。
    """
    if not isinstance(raw, list):
        return []
    corpus = _user_corpus(history)
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        original = str(item.get("original") or "").strip()
        better = str(item.get("better") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if not original or not better or not reason:
            continue
        key = _norm(original)
        if not key or f" {key} " not in corpus:
            continue
        out.append({"original": original, "better": better, "reason": reason})
        if len(out) >= MAX_FIXES:
            break
    return out


def _parse_bands(raw):
    """模型给的维度分 → {维度: 雅思 band}。兼容旧的 0–100 写法。"""
    if not isinstance(raw, dict):
        return None
    nums = {}
    for name in DIMENSIONS:
        v = raw.get(name)
        if isinstance(v, str):
            try:
                v = float(v)
            except ValueError:
                continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        nums[name] = float(v)
    if not nums:
        return None
    # 旧的 0–100 格式：最大值超过 9 就按 0–100 换算
    scale = 100.0 if max(nums.values()) > 9 else 10.0
    out = {}
    for name, v in nums.items():
        band = round_band(v) if scale == 10.0 else round_band((v - 10.0) / 10.0)
        if band is not None:
            out[name] = band
    return out or None


def parse_llm_report(text: str, history):
    """解析模型输出为报告 dict；不可用返回 None（交给降级路径）。"""
    match = _JSON_RE.search(text or "")
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    raw = data.get("bands") or data.get("dimensions") or data.get("scores") or {}
    parsed = _parse_bands(raw)
    if not parsed:
        return None

    scored = report_bands(parsed)
    return {
        "total_score": scored["total_score"],
        "dimensions": scored["dimensions"],
        "bands": scored["bands"],
        "band": scored["band"],
        "cefr": scored["cefr"],
        "sentence_fixes": _sanitize_fixes(data.get("sentence_fixes"), history),
        "comment": str(data.get("comment") or "").strip(),
        "note": str(data.get("note") or "").strip() or DEFAULT_NOTE,
        "source": "llm",
        "mock_reason": None,
    }


def _fallback_report(history, mock_reason: str, detail: str = ""):
    """模型不可用时的示例报告：不计分，但句子必须是用户真实说过的。"""
    sentences = []
    for turn in history:
        if turn.get("role") != "user":
            continue
        for part in re.split(r"[.!?\n]+", turn.get("content") or ""):
            sentence = part.strip()
            if len(_LETTERS_RE.findall(sentence)) >= 3:
                sentences.append(sentence)
    fixes = [
        {
            "original": s,
            "better": "",
            "reason": "模型不可用，本句未做改写；这是你真实说过的句子。",
        }
        for s in sentences[:MAX_FIXES]
    ]
    if detail:
        print(f"[scoring] 降级为示例报告（{mock_reason}）：{detail}", flush=True)
    return {
        "total_score": None,
        "dimensions": {},
        "bands": {},
        "band": None,
        "cefr": None,
        "sentence_fixes": fixes,
        "comment": (
            "示例报告（模型不可用）：这次没有拿到评分模型的返回，也没有规则分兜底，"
            "所以本次不计分。下面列出的句子都是你真实说过的内容，不是示例句。"
        ),
        "note": MOCK_NOTE,
        "source": "mock",
        "mock_reason": mock_reason,
    }


def _prompt(scene: dict, difficulty: str, history) -> str:
    lines = []
    for t in history:
        if t.get("role") == "ai":
            lines.append(f"AI: {t.get('content', '')}")
        else:
            mode = "voice" if (t.get("input_mode") or "voice") == "voice" else "typed"
            lines.append(f"User ({mode}): {t.get('content', '')}")
    convo = "\n".join(lines)
    modes = {
        "voice": sum(1 for t in history if t.get("role") == "user" and (t.get("input_mode") or "voice") == "voice"),
        "typed": sum(1 for t in history if t.get("role") == "user" and (t.get("input_mode") or "voice") == "typed"),
    }
    return (
        "You are an English assessor. Rate the learner using IELTS band descriptors, "
        "then explain the reasons.\n"
        "Return ONLY valid JSON with this schema:\n"
        '{"bands":{"pronunciation":3.0-9.0,"fluency":3.0-9.0,'
        '"grammar_vocab":3.0-9.0,"task_completion":3.0-9.0,"written_expression":3.0-9.0},'
        '"sentence_fixes":[{"original":"","better":"","reason":""}],'
        '"comment":"","note":"分数由 AI 估算，仅供参考。"}\n'
        "Which dimensions to return (IMPORTANT):\n"
        f"- This conversation has {modes['voice']} spoken (voice) turns and {modes['typed']} typed turns.\n"
        "- pronunciation and fluency: ONLY if there is at least one voice turn. Score them from the voice turns only.\n"
        "  If there are zero voice turns, OMIT pronunciation and fluency from `bands` completely.\n"
        "- written_expression: ONLY if there is at least one typed turn. Score how well the learner expresses\n"
        "  ideas in writing (sentence construction, vocabulary choice, coherence). Score it from typed turns only.\n"
        "  If there are zero typed turns, OMIT written_expression completely.\n"
        "- grammar_vocab and task_completion: always return, based on all turns.\n"
        "- Never give a typed turn credit for pronunciation or fluency; never give a voice turn\n"
        "  a written_expression score.\n"
        "Scoring rules:\n"
        "- Bands are IELTS-style, 0.5 steps only, between 3.0 and 9.0.\n"
        "- pronunciation: estimate from the transcript only; you cannot hear the audio.\n"
        "  Use band descriptors for intelligibility; do not claim acoustic or phoneme analysis.\n"
        "- fluency: use coherence, length of turns, repetition, hesitation visible in wording.\n"
        "- grammar_vocab: grammar accuracy and range plus lexical resource.\n"
        "- task_completion: did the learner actually do what the scene requires, and is the register polite/appropriate.\n"
        "- Be strict but fair: an answer that is short, off-topic or mostly filler belongs to band 4-5;\n"
        "  a coherent answer with some errors belongs to band 6; accurate, flexible language is band 7+.\n"
        "- sentence_fixes: 1-3 items. `original` MUST be copied verbatim from the learner's turn;\n"
        "  never invent a sentence the learner did not say.\n"
        "- Write `comment` and every `reason` in Simplified Chinese (简体中文).\n"
        "- Keep `original` and `better` in English: the learner's sentence and the improved version.\n\n"
        f"Scene: {scene['name']}\nDifficulty: {difficulty}\nConversation:\n{convo}"
    )


def _request_report(llm: LLMConfig, scene: dict, difficulty: str, history) -> str:
    with httpx.Client(timeout=60) as client:
        resp = client.post(
            f"{llm.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {llm.api_key}"},
            json={
                "model": llm.model,
                "messages": [{"role": "user", "content": _prompt(scene, difficulty, history)}],
                "temperature": 0.2,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def generate_report(scene: dict, difficulty: str, history, llm: LLMConfig | None = None) -> dict:
    """生成报告。

    用户自己的 key 被 401/403 拒绝时抛 UserKeyInvalid（路由层转 502 key_invalid），
    不降级——否则用户会以为模型暂时不可用，反复重试一个永远不可能成功的密钥。
    """
    llm = llm or build_llm_config()
    if not llm.configured:
        return _fallback_report(history, MOCK_NOT_CONFIGURED, "未配置 LLM_API_KEY，也没有用户密钥")

    try:
        text = _request_report(llm, scene, difficulty, history)
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code in (401, 403):
            if llm.from_user:
                # 用户自己的 key 被拒：路由层转 502 key_invalid，不生成报告
                raise UserKeyInvalid() from exc
            # .env 兜底密钥被拒：属运维问题，降级示例报告并标明 invalid_key
            return _fallback_report(history, MOCK_INVALID_KEY, f"服务端兜底密钥被拒：HTTP {code}")
        return _fallback_report(history, MOCK_UNAVAILABLE, f"HTTP {code}")
    except httpx.TimeoutException:
        return _fallback_report(history, MOCK_UNAVAILABLE, "请求超时")
    except Exception as exc:  # noqa: BLE001 - 任何网络/协议错误都降级，不冒泡成 500
        return _fallback_report(history, MOCK_UNAVAILABLE, f"{type(exc).__name__}: {exc}")

    data = parse_llm_report(text, history)
    if not data:
        return _fallback_report(history, MOCK_UNAVAILABLE, "模型返回无法解析")
    return data
