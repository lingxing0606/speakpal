"""RAG 离线评测（阶段 2，方案 §2.4）：BM25 vs 按组随机取卡。

运行（仓库根目录）：
    backend\\.venv\\Scripts\\python.exe -m evaluation.rag_eval

只读内置语料，不写索引/缓存；唯一输出是 evaluation/rag_report.json。
"""

from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services import library, rag, wordbank  # noqa: E402

CASES_FILE = Path(__file__).resolve().parent / "rag_cases.json"
REPORT_FILE = Path(__file__).resolve().parent / "rag_report.json"
TOP_K = 3
TRIALS = 200
SEED = 20261117


def load_cases() -> list[dict]:
    payload = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    return list(payload.get("cases") or [])


def rank_of(refs: list[str], expected: str) -> int:
    return refs.index(expected) + 1 if expected in refs else 0


def metrics(ranks: list[int]) -> dict:
    total = len(ranks) or 1
    return {
        "cases": len(ranks),
        "recall@1": round(sum(1 for rank in ranks if rank == 1) / total, 4),
        "recall@3": round(sum(1 for rank in ranks if 0 < rank <= TOP_K) / total, 4),
        "mrr": round(sum(1 / rank for rank in ranks if rank) / total, 4),
    }


def evaluate_bm25(cases: list[dict]) -> tuple[dict, list[dict]]:
    ranks = []
    rows = []
    for case in cases:
        hits = rag.search(case["query"], k=TOP_K, kinds=["grammar", "spoken"])
        refs = [hit["ref"] for hit in hits]
        rank = rank_of(refs, case["expected"])
        ranks.append(rank)
        rows.append({**case, "hits": refs, "rank": rank})
    return metrics(ranks), rows


def card_groups() -> dict:
    groups = {"grammar": {}, "spoken": []}
    for card in library.grammar_cards():
        group = card["id"].split("-")[0]
        groups["grammar"].setdefault(group, []).append(card["id"])
    for item in library.spoken_items():
        groups["spoken"].append(item["id"])
    return groups


def evaluate_random(cases: list[dict], trials: int = TRIALS, seed: int = SEED) -> dict:
    """按语法组随机取卡：grammar 在同类组里抽，spoken 在全量口语卡里抽。"""
    groups = card_groups()
    rng = random.Random(seed)
    recall1 = recall3 = mrr = 0.0
    for case in cases:
        if case["expected"].startswith("spoken"):
            pool = groups["spoken"]
        else:
            pool = groups["grammar"].get(case["expected"].split("-")[0], [])
        for _ in range(trials):
            picked = rng.sample(pool, k=min(TOP_K, len(pool)))
            rank = rank_of(picked, case["expected"])
            recall1 += 1 if rank == 1 else 0
            recall3 += 1 if 0 < rank <= TOP_K else 0
            mrr += 1 / rank if rank else 0
    total = len(cases) * trials
    return {
        "cases": len(cases),
        "trials": trials,
        "recall@1": round(recall1 / total, 4),
        "recall@3": round(recall3 / total, 4),
        "mrr": round(mrr / total, 4),
    }


def corpus_summary() -> dict:
    words = 0
    for scope in wordbank.SCOPES:
        words += len(wordbank.next_words(scope, set(), 10000))
    return {
        "grammar_cards": len(library.grammar_cards()),
        "spoken_cards": len(library.spoken_items()),
        "word_entries": words,
    }


def main() -> None:
    cases = load_cases()
    bm25, rows = evaluate_bm25(cases)
    baseline = evaluate_random(cases)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "corpus": corpus_summary(),
        "top_k": TOP_K,
        "bm25": bm25,
        "random_baseline": baseline,
        "cases": rows,
    }
    REPORT_FILE.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"bm25": bm25, "random_baseline": baseline}, ensure_ascii=False, indent=2))
    misses = [row["id"] for row in rows if not row["rank"]]
    if misses:
        print("misses:", ", ".join(misses))


if __name__ == "__main__":
    main()
