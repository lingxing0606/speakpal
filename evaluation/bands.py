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

# ---- 作答模式与维度权重（口径见 docs/rubric-band.md §2.3）----
#
# 权重按「证据强度」给，不做平均主义：
# - 发音在本项目没有声学证据（rules.py 注明“由模型依转写推断”），纯录音里降到 20；
# - 纯打字压根没有发音/流利度，原本属于这两维的 40 分转给文字表达（35）与语言复杂度（35）；
# - 混合时语音证据只覆盖录音轮、文字证据只覆盖打字轮，所以各降一档，共享维度保持 50。
DIMENSION_WEIGHTS = {
    "voice": {
        "pronunciation": 20,
        "fluency": 20,
        "grammar_vocab": 30,
        "task_completion": 30,
    },
    "typed": {
        "written_expression": 35,
        "grammar_vocab": 35,
        "task_completion": 30,
    },
    "mixed": {
        "pronunciation": 15,
        "fluency": 15,
        "written_expression": 20,
        "grammar_vocab": 25,
        "task_completion": 25,
    },
}

# 只在录音轮才有的维度
VOICE_ONLY = ("pronunciation", "fluency")
# 只在打字轮才有的维度
TYPED_ONLY = ("written_expression",)
# 两种作答都会评、可用于跨模式比较的维度
SHARED_DIMS = ("grammar_vocab", "task_completion")


def infer_answer_mode(scores):
    """从参与打分的维度反推作答模式：voice / typed / mixed / None。"""
    has_voice = any(scores.get(d) is not None for d in VOICE_ONLY)
    has_typed = any(scores.get(d) is not None for d in TYPED_ONLY)
    if has_voice and has_typed:
        return "mixed"
    if has_typed:
        return "typed"
    if has_voice:
        return "voice"
    return None


def weighted_total(scores, mode=None):
    """按作答模式加权求综合分；缺失维度按剩余权重重新归一，缺维度不当 0 分。"""
    if not scores:
        return None
    mode = mode or infer_answer_mode(scores)
    weights = DIMENSION_WEIGHTS.get(mode) or {}
    pairs = [
        (float(scores[dim]), weights[dim])
        for dim in scores
        if scores.get(dim) is not None and dim in weights
    ]
    total_w = sum(w for _, w in pairs)
    if not pairs or total_w <= 0:
        # 认不出作答模式（只剩共享维度）时退回等权平均，总比不出分好
        vals = [float(v) for v in scores.values() if v is not None]
        return int(round(sum(vals) / len(vals))) if vals else None
    return int(round(sum(s * w for s, w in pairs) / total_w))


def comparable_score(scores):
    """跨模式可比的子分：只用「录音/打字都会评」的两个维度。"""
    vals = [float(scores[d]) for d in SHARED_DIMS if scores.get(d) is not None]
    if not vals:
        return None
    return int(round(sum(vals) / len(vals)))


def comparable_band(scores):
    return score_to_band(comparable_score(scores))


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
    """各维 0–100 分 → 综合分（加权，见 DIMENSION_WEIGHTS；不再做等权平均）。"""
    return weighted_total(scores)


def report_bands(dimension_bands):
    """维度 band → {total_score, dimensions, bands, band, cefr, answer_mode, comparable_*}。

    dimension_bands 里允许有 None（模型没给该维），逐维跳过；作答模式由出现的维度反推。
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
    mode = infer_answer_mode(scores)
    total = weighted_total(scores, mode)
    band = score_to_band(total) if total is not None else None
    return {
        "total_score": total,
        "dimensions": scores,
        "bands": bands,
        "band": band,
        "cefr": band_to_cefr(band),
        "answer_mode": mode,
        "comparable_score": comparable_score(scores),
        "comparable_band": comparable_band(scores),
    }
