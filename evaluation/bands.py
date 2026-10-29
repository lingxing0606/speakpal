"""0–100 分、雅思 band、CEFR 等级之间的换算（纯标准库）。

这是全项目唯一的换算入口：后端打分、前端展示、验证层取整都从这里取，
不要在别处再写一套 (score-10)/10。

量表定义见 docs/rubric-band.md。
"""
from __future__ import annotations

import math

# 前四个是口语维度；written_expression 只在用户「打字回答」时出现
DIMENSIONS = (
    "pronunciation",
    "fluency",
    "grammar_vocab",
    "task_completion",
    "written_expression",
)

BAND_MIN = 3.0
BAND_MAX = 9.0

# 档位从低到高，验证层算“相差几档”时用
CEFR_ORDER = ("A2", "B1", "B2", "C1", "C2")


def band_to_score(band):
    """雅思 band → 0–100 展示分。"""
    if band is None:
        return None
    return 10.0 * float(band) + 10.0


def score_to_band(score):
    """0–100 → 最近的 0.5 档雅思 band；低于 A2 下缘（40 分）返回 None。"""
    if score is None:
        return None
    try:
        s = float(score)
    except (TypeError, ValueError):
        return None
    b = (s - 10.0) / 10.0
    if b < BAND_MIN:
        return None
    return round_band(b)


def round_band(band):
    """把任意数值压到 3.0–9.0 区间内最近的 0.5 档。

    .25 / .75 这类恰好骑在中间的值一律向上取（floor(b*2+0.5)/2），
    保证不会产出 5.25 这种不存在的 band。
    """
    b = float(band)
    if b < BAND_MIN:
        return None
    b = min(b, BAND_MAX)
    return math.floor(round(b * 2, 6) + 0.5) / 2.0


def band_to_cefr(band):
    """雅思 band → CEFR 字母。对照见 docs/rubric-band.md §1.2。"""
    if band is None:
        return None
    b = float(band)
    if b >= 8.5:
        return "C2"
    if b >= 7.0:
        return "C1"
    if b >= 5.5:
        return "B2"
    if b >= 4.0:
        return "B1"
    if b >= 3.0:
        return "A2"
    return None


def cefr_of_score(score):
    return band_to_cefr(score_to_band(score))


def cefr_distance(a, b):
    """两个 CEFR 档位相差几档；无法比较（含 None / 未知字母）返回 None。"""
    if a not in CEFR_ORDER or b not in CEFR_ORDER:
        return None
    return abs(CEFR_ORDER.index(a) - CEFR_ORDER.index(b))


def total_from_dimension_scores(scores):
    """四维 0–100 分 → 总分（四舍五入整数）。缺失维度直接跳过。"""
    vals = [float(v) for v in scores.values() if v is not None]
    if not vals:
        return None
    return int(round(sum(vals) / len(vals)))


def report_bands(dimension_bands):
    """四维 band → {total_score, dimensions, bands, band, cefr}。

    dimension_bands 里允许有 None（模型没给该维），逐维跳过。
    """
    bands = {}
    scores = {}
    for name in DIMENSIONS:
        b = dimension_bands.get(name)
        if b is None:
            continue
        b = round_band(b)
        if b is None:
            continue
        bands[name] = b
        scores[name] = int(round(band_to_score(b)))
    total = total_from_dimension_scores(scores)
    band = score_to_band(total) if total is not None else None
    return {
        "total_score": total,
        "dimensions": scores,
        "bands": bands,
        "band": band,
        "cefr": band_to_cefr(band),
    }
