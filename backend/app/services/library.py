"""语法卡与口语卡：内置静态内容（docs/design.md §18.6）。

- 语法卡：`kind=grammar, source=grammar`，一张卡只教一个点。`term` 语法点、
  `meaning_zh` 规则一句话、`context` 错句、`example` 正确句；
  `related.blank` / `related.answer` 是从「错句→正确句」推出来的挖空和答案，
  前端可以直接拿来做填空，复习也按 `answer` 判档，不走自评。
- 口语卡：`kind=phrase, source=spoken`，`term` 书面说法、`example` 更自然的口语说法、
  `meaning_zh` 为什么这样说。复习时比对用户改写和口语说法（词级相似度）。

内容与词库一样是应用自带数据，不是用户数据；进度仍然只存 `study_items`。
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

_GRAMMAR_DIR = Path(__file__).resolve().parent.parent / "data" / "grammar"
_SPOKEN_FILE = Path(__file__).resolve().parent.parent / "data" / "spoken.json"

GRAMMAR_GROUP_ORDER = ("tenses", "articles", "prepositions", "clauses")

_grammar_cache: dict[str, dict] = {}
_spoken_cache: list[dict] | None = None

_WORD_RE = re.compile(r"[a-z0-9']+")


def _load_group(group_id: str) -> dict:
    if group_id in _grammar_cache:
        return _grammar_cache[group_id]
    data: dict = {"group": group_id, "name": group_id, "desc": "", "items": []}
    try:
        raw = json.loads((_GRAMMAR_DIR / f"{group_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    if isinstance(raw, dict):
        items = [
            item
            for item in (raw.get("items") or [])
            if isinstance(item, dict) and item.get("id") and item.get("point")
        ]
        data = {
            "group": group_id,
            "name": str(raw.get("name") or group_id).strip(),
            "desc": str(raw.get("desc") or "").strip(),
            "items": items,
        }
    _grammar_cache[group_id] = data
    return data


def grammar_groups() -> list[dict]:
    """四组语法卡（时态/冠词/介词/从句），每组 15 张。"""
    return [_load_group(g) for g in GRAMMAR_GROUP_ORDER]


def grammar_cards() -> list[dict]:
    """拍平后的语法卡，每张带 group 与挖空结果。"""
    out = []
    for group in grammar_groups():
        for item in group["items"]:
            blank, answer = blank_and_answer(item.get("wrong") or "", item.get("right") or "")
            out.append(
                {
                    "id": str(item["id"]),
                    "group": group["group"],
                    "group_name": group["name"],
                    "point": str(item.get("point") or "").strip(),
                    "rule": str(item.get("rule") or "").strip(),
                    "wrong": str(item.get("wrong") or "").strip(),
                    "right": str(item.get("right") or "").strip(),
                    "blank": blank,
                    "answer": answer,
                }
            )
    return out


def spoken_items() -> list[dict]:
    global _spoken_cache
    if _spoken_cache is not None:
        return _spoken_cache
    try:
        raw = json.loads(_SPOKEN_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    items = [
        item
        for item in (raw.get("items") or [])
        if isinstance(item, dict) and item.get("id") and item.get("formal") and item.get("natural")
    ]
    _spoken_cache = items
    return items


# ------------------------------------------------------------------ 文本与判档
def normalize(text: str) -> str:
    """小写、统一引号、去标点、压空格；库里和用户输入都过这一层再比。"""
    value = (text or "").lower().replace("’", "'").replace("“", '"').replace("”", '"')
    value = re.sub(r"[^a-z0-9'\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def words(text: str) -> list[str]:
    return _WORD_RE.findall(normalize(text))


def similarity(a: str, b: str) -> float:
    """词级相似度（0–1），和跟读用的同一套口径。"""
    left, right = words(a), words(b)
    if not left or not right:
        return 0.0
    return round(difflib.SequenceMatcher(None, left, right).ratio(), 3)


def blank_and_answer(wrong: str, right: str) -> tuple[str, str]:
    """从「错句 → 正确句」找出那一个点，做成挖空。

    删除类（正确句比错句短）不挖空，返回空串，前端改用「整句改写」输入。
    """
    wrong_tokens = (wrong or "").split()
    right_tokens = (right or "").split()
    if not wrong_tokens or not right_tokens:
        return "", ""
    prefix = 0
    limit = min(len(wrong_tokens), len(right_tokens))
    while prefix < limit and wrong_tokens[prefix].lower() == right_tokens[prefix].lower():
        prefix += 1
    suffix = 0
    while (
        suffix < limit - prefix
        and wrong_tokens[len(wrong_tokens) - 1 - suffix].lower()
        == right_tokens[len(right_tokens) - 1 - suffix].lower()
    ):
        suffix += 1
    answer_tokens = right_tokens[prefix : len(right_tokens) - suffix]
    if not answer_tokens:
        return "", ""
    blank = " ".join(right_tokens[:prefix] + ["____"] + right_tokens[len(right_tokens) - suffix :])
    return blank, " ".join(answer_tokens)


def judge_grammar(answer: str, right: str, blank_answer: str = "") -> str:
    """语法卡判档：填对那个点或整句正确 → good；只差一个词 → hard；否则 again。"""
    said = normalize(answer)
    if not said:
        return "again"
    if blank_answer and said == normalize(blank_answer):
        return "good"
    target = normalize(right)
    if said == target:
        return "good"
    said_words, target_words = words(answer), words(right)
    if len(said_words) == len(target_words):
        diff = sum(1 for a, b in zip(said_words, target_words) if a != b)
        if diff == 1:
            return "hard"
    if similarity(answer, right) >= 0.85:
        return "hard"
    return "again"


def judge_spoken(answer: str, natural: str) -> str:
    """口语卡判档：和口语说法比词级相似度，≥0.7 good、≥0.5 hard，其余 again。"""
    score = similarity(answer, natural)
    if score >= 0.7:
        return "good"
    if score >= 0.5:
        return "hard"
    return "again"
