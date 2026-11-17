"""BM25 关键词检索（方案 §2.2）：语法卡 / 口语卡 / 词库 + 用户历史。

- 内置语料在首次 `search` 时建一次索引，存模块级变量常驻内存；不落盘、不下载模型。
- `bm25s` 缺失或建索引失败时 `search` 返回空列表，报告照常生成。
- 用户历史（study_items + 历史报告 fixes）每次现场建一个小 BM25，不缓存、不跨用户。
"""

from __future__ import annotations

import json
import re
import threading

from . import library, wordbank

try:
    import bm25s
except Exception:  # noqa: BLE001 - 没装依赖时检索降级为空，不影响主流程
    bm25s = None

_WORD_RE = re.compile(r"[a-z]+(?:'[a-z]+)?")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

# None = 还没建；False = 建失败（不再重试）；tuple = (retriever, docs)
_index_lock = threading.Lock()
_index: tuple | bool | None = None
_USER_DOC_LIMIT = 300
_USER_REPORT_LIMIT = 10


def tokenize(text: str) -> list[str]:
    """英文小写单词 + 中文二元组；查询与语料共用这一套。"""
    value = (text or "").lower()[:4000]
    tokens = _WORD_RE.findall(value)
    chars = _CJK_RE.findall(value)
    tokens.extend(chars[i] + chars[i + 1] for i in range(len(chars) - 1))
    return tokens


def _corpus() -> list[dict]:
    docs: list[dict] = []
    for card in library.grammar_cards():
        docs.append(
            {
                "ref": card["id"],
                "kind": "grammar",
                "title": card["point"],
                "text": f"{card['rule']} {card['wrong']} {card['right']}",
            }
        )
    for item in library.spoken_items():
        docs.append(
            {
                "ref": item["id"],
                "kind": "spoken",
                "title": str(item.get("formal") or item.get("id") or ""),
                "text": (
                    f"{item.get('formal', '')} {item.get('natural', '')} {item.get('why', '')}"
                ),
            }
        )
    for scope in wordbank.SCOPES:
        for word in wordbank.next_words(scope, set(), 10000):
            docs.append(
                {
                    "ref": f"word:{word['term']}",
                    "kind": "word",
                    "title": word["term"],
                    "text": f"{word['meaning_zh']} {word['example']}",
                }
            )
    return docs


def _build_index():
    if bm25s is None:
        return False
    docs = _corpus()
    if not docs:
        return False
    retriever = bm25s.BM25()
    retriever.index(
        [tokenize(f"{doc['title']} {doc['text']}") for doc in docs],
        show_progress=False,
    )
    return retriever, docs


def _get_index():
    global _index
    if _index is None:
        with _index_lock:
            if _index is None:
                try:
                    _index = _build_index()
                except Exception as exc:  # noqa: BLE001 - 建索引失败只降级为空结果
                    print(f"[rag] 索引构建失败：{type(exc).__name__}", flush=True)
                    _index = False
    return _index or None


def search(query: str, k: int = 4, kinds=None) -> list[dict]:
    """检索内置语料，返回 {ref, kind, title, text, score}；失败返回 []。"""
    if bm25s is None:
        return []
    tokens = tokenize(query)
    if not tokens:
        return []
    size = max(1, min(int(k or 4), 10))
    index = _get_index()
    if not index:
        return []
    retriever, docs = index
    wanted = set(kinds) if kinds else None
    try:
        # 先多取一些再按 kind 过滤，避免过滤后不够 k 条
        pool = min(len(docs), max(size * 6, 20))
        results, scores = retriever.retrieve([tokens], k=pool, show_progress=False)
        out = []
        for doc_id, score in zip(results[0], scores[0]):
            if float(score) <= 0:
                continue
            doc = docs[int(doc_id)]
            if wanted and doc["kind"] not in wanted:
                continue
            out.append({**doc, "score": round(float(score), 4)})
            if len(out) >= size:
                break
        return out
    except Exception as exc:  # noqa: BLE001 - 检索失败只降级为空结果
        print(f"[rag] 检索失败：{type(exc).__name__}", flush=True)
        return []


def _user_docs(db, user_id: int) -> list[dict]:
    """该用户自己的学习卡与历史纠错；查询层已按 user_id 过滤。"""
    from ..models import PracticeSession, Report, StudyItem

    docs: list[dict] = []
    rows = (
        db.query(StudyItem)
        .filter(StudyItem.user_id == user_id)
        .order_by(StudyItem.id.desc())
        .limit(_USER_DOC_LIMIT)
        .all()
    )
    for item in rows:
        docs.append(
            {
                "ref": f"item:{item.id}",
                "kind": item.kind or "word",
                "title": item.term or "",
                "text": f"{item.meaning_zh or ''} {item.example or ''} {item.context or ''}",
            }
        )
    reports = (
        db.query(Report)
        .join(PracticeSession, Report.session_id == PracticeSession.id)
        .filter(PracticeSession.user_id == user_id, Report.source == "llm")
        .order_by(Report.id.desc())
        .limit(_USER_REPORT_LIMIT)
        .all()
    )
    for rep in reports:
        try:
            fixes = json.loads(rep.fixes_json or "[]")
        except (TypeError, ValueError):
            fixes = []
        for index, fix in enumerate(fixes if isinstance(fixes, list) else []):
            if not isinstance(fix, dict):
                continue
            original = str(fix.get("original") or "").strip()
            better = str(fix.get("better") or "").strip()
            reason = str(fix.get("reason") or "").strip()
            if not original and not better:
                continue
            docs.append(
                {
                    "ref": f"fix:{rep.id}:{index}",
                    "kind": "fix",
                    "title": f"{original} → {better}",
                    "text": reason,
                }
            )
    return docs


def search_user_history(db, user_id: int, query: str, k: int = 3) -> list[dict]:
    """现场从该用户的 study_items + 历史报告 fixes 建小 BM25；不缓存、不跨用户。"""
    if bm25s is None or db is None:
        return []
    tokens = tokenize(query)
    if not tokens:
        return []
    docs = _user_docs(db, user_id)
    if not docs:
        return []
    size = max(1, min(int(k or 3), 5))
    try:
        retriever = bm25s.BM25()
        retriever.index(
            [tokenize(f"{doc['title']} {doc['text']}") for doc in docs],
            show_progress=False,
        )
        results, scores = retriever.retrieve(
            [tokens], k=min(len(docs), size), show_progress=False
        )
        out = []
        for doc_id, score in zip(results[0], scores[0]):
            if float(score) <= 0:
                continue
            out.append({**docs[int(doc_id)], "score": round(float(score), 4)})
        return out
    except Exception as exc:  # noqa: BLE001 - 历史检索失败只降级为空结果
        print(f"[rag] 历史检索失败：{type(exc).__name__}", flush=True)
        return []
