"""新词词库：内置静态 JSON（docs/design.md §18.2）。

- 词表进仓库（`app/data/wordbanks/{scope}.json`），断网也能取词，不引第三方词典依赖。
- 词表是应用自带数据，不是用户数据；用户的进度只存 `study_items(kind=word)`，
  删除账号/清记录时随 §16 的级联一起清掉，词库本身不需要额外清理。
- 取词顺序固定（难度 → 字母），刷新页面不会跳词；已进过清单的词不再推荐。
"""

from __future__ import annotations

import json
from pathlib import Path

_WORDBANK_DIR = Path(__file__).resolve().parent.parent / "data" / "wordbanks"

# 顺序就是前端展示顺序；新增范围只要放一个同名 JSON 并加进这里
SCOPES: tuple[str, ...] = ("gaokao", "cet4", "cet6")
DEFAULT_SCOPE = "cet4"

_LEVEL_ORDER = {"A1": 0, "A2": 1, "B1": 2, "B2": 3, "C1": 4, "C2": 5}

_cache: dict[str, dict] = {}

# 实际存在文件的范围，启动时算一次（没有文件的范围直接跳过，不报错）
_SCOPE_IDS = {s for s in SCOPES if (_WORDBANK_DIR / f"{s}.json").exists()}


def _load(scope: str) -> dict:
    """读一个范围的文件并规范化条目；不存在的返回空词表而不是抛。"""
    if scope in _cache:
        return _cache[scope]
    path = _WORDBANK_DIR / f"{scope}.json"
    data: dict = {"scope": scope, "name": scope, "desc": "", "words": []}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    if isinstance(raw, dict):
        words = [w for w in (raw.get("words") or []) if isinstance(w, dict) and w.get("term")]
        words.sort(
            key=lambda w: (
                _LEVEL_ORDER.get(str(w.get("level") or "").upper(), 9),
                str(w["term"]).lower(),
            )
        )
        data = {
            "scope": scope,
            "name": str(raw.get("name") or scope).strip(),
            "desc": str(raw.get("desc") or "").strip(),
            "words": words,
        }
    _cache[scope] = data
    return data


def scope_ids() -> set[str]:
    return set(_SCOPE_IDS)


def default_scope() -> str:
    ids = scope_ids()
    return DEFAULT_SCOPE if DEFAULT_SCOPE in ids else (sorted(ids)[0] if ids else DEFAULT_SCOPE)


def scopes_out(learned_terms: set[str] | None = None) -> list[dict]:
    """范围列表：名字、说明、总数和已学数，学习页的「选择词库」用。"""
    learned = {str(t).strip().lower() for t in (learned_terms or set()) if t}
    out = []
    for scope in SCOPES:
        data = _load(scope)
        if not data["words"]:
            continue
        out.append(
            {
                "id": scope,
                "name": data["name"],
                "desc": data["desc"],
                "total": len(data["words"]),
                "learned": sum(1 for w in data["words"] if str(w["term"]).lower() in learned),
            }
        )
    return out


def word_out(entry: dict, scope: str) -> dict:
    related = entry.get("related") if isinstance(entry.get("related"), dict) else {}
    return {
        "scope": scope,
        "term": str(entry["term"]).strip(),
        "phonetic": str(entry.get("phonetic") or "").strip(),
        "pos": str(entry.get("pos") or "").strip(),
        "meaning_zh": str(entry.get("meaning_zh") or "").strip(),
        "example": str(entry.get("example") or "").strip(),
        "example_zh": str(entry.get("example_zh") or "").strip(),
        "level": str(entry.get("level") or "").upper(),
        "related": {
            "synonyms": [str(v) for v in (related.get("synonyms") or [])][:8],
            "antonyms": [str(v) for v in (related.get("antonyms") or [])][:8],
            "similar": [str(v) for v in (related.get("similar") or [])][:8],
        },
    }


def totals(scope: str, learned_terms: set[str]) -> dict:
    data = _load(scope)
    learned = {t.lower() for t in learned_terms}
    done = sum(1 for w in data["words"] if str(w["term"]).lower() in learned)
    return {
        "scope": scope,
        "name": data["name"],
        "desc": data["desc"],
        "total": len(data["words"]),
        "learned": done,
        "remaining": len(data["words"]) - done,
    }


def next_words(scope: str, learned_terms: set[str], limit: int = 20) -> list[dict]:
    """该范围里还没进过清单的词，按固定顺序取前 limit 个。"""
    learned = {t.lower() for t in learned_terms}
    picked = []
    for entry in _load(scope)["words"]:
        if str(entry["term"]).lower() in learned:
            continue
        picked.append(word_out(entry, scope))
        if len(picked) >= limit:
            break
    return picked


def find(term: str, scope: str | None = None) -> tuple[dict, str] | None:
    """按词找条目，返回 (entry, scope)；给了 scope 就只在这个范围里找。"""
    target = (term or "").strip().lower()
    if not target:
        return None
    scopes = [scope] if scope in _SCOPE_IDS else list(SCOPES)
    for one in scopes:
        for entry in _load(one)["words"]:
            if str(entry["term"]).lower() == target:
                return entry, one
    return None
