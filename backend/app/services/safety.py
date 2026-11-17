"""AI 安全（方案 §4.3）：输入注入标记、输出质量检查、图片类型/大小校验。

原则：
- 输入只标记不拦截——学习者可能正是在练「ignore the previous instructions」这类句子。
- 输出不合格时由调用方替换成预设追问；流式无法撤回，替换文本放 done 事件。
- 图片只在这里做类型与大小校验，解码与压缩在前端完成。
"""

from __future__ import annotations

import re

# 提示注入：中英常见说法。命中只打标记，不改变这一轮的处理。
INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.I),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions?", re.I),
    re.compile(r"忽略(之前|以上|前面|先前)的?(所有)?(指令|提示|要求)"),
    re.compile(r"system\s*prompt", re.I),
    re.compile(r"你现在是"),
    re.compile(r"从现在(开始|起)你"),
    re.compile(r"\bact\s+as\b", re.I),
    re.compile(r"\bjailbreak\b", re.I),
)

# 出戏：自称 AI / 语言模型
ROLE_BREAK_PATTERNS = (
    re.compile(r"\bas an ai\b", re.I),
    re.compile(r"\bas a (large )?language model\b", re.I),
    re.compile(r"作为\s*(一个)?\s*AI", re.I),
    re.compile(r"作为\s*人工智能", re.I),
)

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
WORD_RE = re.compile(r"[a-z]+(?:'[a-z]+)?")

MAX_REPLY_CHARS = 600
MAX_CHINESE_RATIO = 0.3
LEAK_NGRAM = 8

MAX_IMAGE_BYTES = 4 * 1024 * 1024


def check_input(text: str) -> dict:
    """学习者的输入是否像提示注入。返回 {"flag": "injection" | None}。"""
    value = text or ""
    for pattern in INJECTION_PATTERNS:
        if pattern.search(value):
            return {"flag": "injection"}
    return {"flag": None}


def chinese_ratio(text: str) -> float:
    """中文字符占「中文 + 英文字母/数字」的比例；标点空白不计。"""
    value = text or ""
    cjk = len(CJK_RE.findall(value))
    latin = len(re.findall(r"[A-Za-z0-9]", value))
    total = cjk + latin
    return cjk / total if total else 0.0


def _leaks_system_prompt(reply: str, system_prompt: str) -> bool:
    """回复里出现 system prompt 的连续 8 词，视为泄露（不要求整段照抄）。"""
    if not system_prompt:
        return False
    prompt_words = WORD_RE.findall(system_prompt.lower())
    if len(prompt_words) < LEAK_NGRAM:
        return False
    known = {
        " ".join(prompt_words[i : i + LEAK_NGRAM])
        for i in range(len(prompt_words) - LEAK_NGRAM + 1)
    }
    reply_words = WORD_RE.findall((reply or "").lower())
    for i in range(len(reply_words) - LEAK_NGRAM + 1):
        if " ".join(reply_words[i : i + LEAK_NGRAM]) in known:
            return True
    return False


def check_reply(text: str, system_prompt: str = "") -> tuple[bool, str]:
    """AI 回复是否可直接给用户。返回 (ok, reason)；reason 为空表示通过。"""
    value = (text or "").strip()
    if not value:
        return False, "empty"
    for pattern in ROLE_BREAK_PATTERNS:
        if pattern.search(value):
            return False, "role_break"
    if len(value) > MAX_REPLY_CHARS:
        return False, "too_long"
    if chinese_ratio(value) > MAX_CHINESE_RATIO:
        return False, "chinese_ratio"
    if _leaks_system_prompt(value, system_prompt):
        return False, "prompt_leak"
    return True, ""


def image_mime(data: bytes) -> str | None:
    """按文件头判断图片类型：JPEG / PNG / WebP；不是这三种返回 None。"""
    if not data:
        return None
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_image(data: bytes) -> str:
    """校验图片大小与类型，返回 mime；不合格抛 ValueError（路由转 400）。"""
    if not data:
        raise ValueError("没有收到图片")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(f"图片不能超过 {MAX_IMAGE_BYTES // (1024 * 1024)} MiB")
    mime = image_mime(data)
    if not mime:
        raise ValueError("只支持 JPG / PNG / WebP 图片")
    return mime
