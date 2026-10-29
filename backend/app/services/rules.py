"""规则子分：把可测特征算成分数，再与模型分融合。

公式与【自定】锚点见 docs/rubric-band.md §3、§4.1。这里只负责“算”和“融合”，
不负责展示；每次融合都把模型原分、规则分、最终分一起留在 scoring_detail 里，
保证任何一次压分都能复现（回看报告就知道是被压了还是模型本来就这么给）。
"""

from __future__ import annotations

import re

from evaluation.bands import band_to_cefr, score_to_band

# ---- 规则常量（全部【自定】，改这里要同步 docs/rubric-band.md §6.5）----

WPM_FLOOR = 70.0  # 语速 70 词/分 记 0
WPM_PLATEAU = 130.0  # 130–200 词/分 记满分
WPM_CEIL = 200.0
WPM_DECAY = 60.0

PAUSE_GOOD = 0.15  # 停顿占比 ≤0.15 记满分
PAUSE_BAD = 0.45  # ≥0.45 记 0

FILLER_GOOD = 0.03
FILLER_BAD = 0.15

W_WPM, W_PAUSE, W_FILLER = 0.40, 0.35, 0.25
FLUENCY_BASE, FLUENCY_SPAN = 45.0, 45.0

MTLD_FLOOR, MTLD_CEIL = 30.0, 90.0
MSL_FLOOR, MSL_CEIL = 6.0, 16.0
W_MTLD, W_MSL, W_CX = 0.45, 0.35, 0.20
COMPLEXITY_BASE, COMPLEXITY_SPAN = 45.0, 45.0

TASK_BASE, TASK_SPAN = 40.0, 60.0
W_TASK_RULE = 0.6  # 清单只测“有没有做”，得体性交给模型

# 通用融合：流利度、语法词汇各占一半；任务完成按 §3.4 的 0.6/0.4
W_RULE_FLUENCY = 0.5
# 规则分只测“语言范围”，准确度只有模型能给，所以模型权重大一些
W_RULE_GRAMMAR = 0.35

CLAMP_GAP = 20.0  # 模型比规则高出 2 档就压
CLAMP_TO = 10.0  # 压回规则分 +10

COMPLEX_MARKERS = (
    "in order to",
    "so that",
    "because",
    "although",
    "though",
    "while",
    "whereas",
    "which",
    "who",
    "that",
    "when",
    "if",
    "unless",
)

# 按整词匹配：否则 "although" 里的 "though" 会被重复计一次（实测踩过）
_MARKER_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(m) for m in COMPLEX_MARKERS) + r")\b"
)

# 场景交际功能清单（【自定】，按场景任务分析法拆；命中靠关键词，待标注数据校准）
TASK_CHECKS = {
    "job_interview": [
        ("自我介绍", ("my name", "i am", "i'm", "i study", "i studied", "graduated", "major", "student")),
        ("项目或经历", ("project", "experience", "internship", "worked", "work on", "built", "developed")),
        ("职责或角色", ("responsible", "my role", "i led", "i designed", "i managed", "team", "in charge")),
        ("挑战或结果", ("challenge", "difficult", "problem", "improved", "result", "success", "increased", "reduced")),
        ("反问或收尾", ("thank you", "any questions", "look forward", "that's all", "thanks for")),
    ],
    "cafe_order": [
        ("点单饮品", ("i'd like", "i would like", "can i get", "i want", "latte", "coffee", "tea", "cappuccino", "americano", "flat white", "order")),
        ("规格", ("large", "small", "medium", "iced", "hot", "extra shot", "milk", "sugar")),
        ("加料或餐点", ("pastry", "croissant", "muffin", "cake", "sandwich", "cookie", "add")),
        ("堂食或外带", ("for here", "to go", "takeaway", "take away", "sit in", "eat in")),
        ("结账或致谢", ("how much", "pay", "card", "cash", "thanks", "thank you", "bill", "receipt")),
    ],
    "ielts_part1": [
        ("直接回答", ("yes", "no", "i live", "i have", "i do", "it is", "there is", "my")),
        ("给出原因或细节", ("because", "since", "so", "actually", "really", "usually", "always")),
        ("举例", ("for example", "for instance", "such as", "like")),
        ("延伸或对比", ("but", "while", "compared", "also", "too", "however", "although")),
    ],
}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _f_wpm(wpm):
    if wpm is None:
        return None
    w = float(wpm)
    if w <= WPM_FLOOR:
        return 0.0
    if w <= WPM_PLATEAU:
        return _clamp01((w - WPM_FLOOR) / (WPM_PLATEAU - WPM_FLOOR))
    if w <= WPM_CEIL:
        return 1.0
    return _clamp01(1.0 - (w - WPM_CEIL) / WPM_DECAY)


def _f_pause(ratio):
    if ratio is None:
        return None
    return _clamp01((PAUSE_BAD - float(ratio)) / (PAUSE_BAD - PAUSE_GOOD))


def _f_filler(rate):
    if rate is None:
        return None
    return _clamp01((FILLER_BAD - float(rate)) / (FILLER_BAD - FILLER_GOOD))


def _f_mtld(value):
    if value is None:
        return None
    return _clamp01((float(value) - MTLD_FLOOR) / (MTLD_CEIL - MTLD_FLOOR))


def _f_msl(value):
    if value is None:
        return None
    return _clamp01((float(value) - MSL_FLOOR) / (MSL_CEIL - MSL_FLOOR))


def _f_cx(count, sentences):
    if sentences is None or sentences <= 0:
        return None
    return _clamp01(count / sentences)


def _weighted(terms, weights):
    """只对可用项加权归一；没有可用项返回 None。"""
    pairs = [(terms[k], weights[k]) for k in terms if terms[k] is not None]
    total = sum(w for _, w in pairs)
    if not pairs or total <= 0:
        return None
    return sum(v * w for v, w in pairs) / total


def _sentence_count(features):
    """句数：有标点用标点；只有录音停顿才用停顿估；都没有返回 None。

    Chrome 的转写通常不带标点，此时 sentence_count 恒为 1，
    mean_sentence_len 会退化成“整段词数”，方向是错的，所以不能用。
    """
    n = features.get("sentence_count") or 0
    if n >= 2:
        return n, "punctuation"
    pauses = features.get("pause_count") or 0
    words = features.get("word_count") or 0
    if pauses >= 1 and words >= 8:
        est = min(1 + int(pauses), max(1, words // 4))
        return est, "pauses"
    return None, "none"


def count_complex_markers(text: str) -> int:
    return len(_MARKER_RE.findall((text or "").lower()))


def evaluate_fluency(features):
    terms = {
        "wpm": _f_wpm(features.get("speech_rate_wpm")),
        "pause": _f_pause(features.get("pause_ratio")),
        "filler": _f_filler(features.get("filler_rate")),
    }
    weights = {"wpm": W_WPM, "pause": W_PAUSE, "filler": W_FILLER}
    combined = _weighted(terms, weights)
    if features.get("speech_rate_wpm") is None or features.get("pause_ratio") is None:
        # 没有录音就没有语音证据，不拿 filler 硬凑（§3.2）
        return {
            "score": None,
            "terms": terms,
            "inputs": {
                "speech_rate_wpm": features.get("speech_rate_wpm"),
                "pause_ratio": features.get("pause_ratio"),
                "filler_rate": features.get("filler_rate"),
            },
            "note": "无语音证据（未录音），流利度仅由模型文本推断",
        }
    score = FLUENCY_BASE + FLUENCY_SPAN * combined if combined is not None else None
    return {
        "score": score,
        "terms": terms,
        "inputs": {
            "speech_rate_wpm": features.get("speech_rate_wpm"),
            "pause_ratio": features.get("pause_ratio"),
            "filler_rate": features.get("filler_rate"),
        },
        "note": "规则分由语速 / 停顿占比 / 填充词占比加权得出",
    }


def evaluate_complexity(features, text: str):
    sentences, src = _sentence_count(features)
    words = features.get("word_count") or 0
    words_per_sentence = (words / sentences) if sentences else None
    markers = count_complex_markers(text or "")

    terms = {
        "mtld": _f_mtld(features.get("mtld")),
        "msl": _f_msl(words_per_sentence),
        "cx": _f_cx(markers, sentences),
    }
    weights = {"mtld": W_MTLD, "msl": W_MSL, "cx": W_CX}
    if terms["msl"] is None:
        # 没有可用句长时把它的权重让给从句标记（§3.3 修正方案）
        weights["cx"] = W_CX + W_MSL
    combined = _weighted(terms, weights)
    if combined is None:
        return {
            "score": None,
            "terms": terms,
            "inputs": {"word_count": words, "sentence_count": sentences},
            "note": "文本过短，无法计算语言复杂度",
        }
    note = "规则分由词汇多样性 / 句长 / 从句标记加权得出"
    if features.get("mtld") is None:
        note += "；样本不足 50 词，未计 MTLD"
    if sentences is None:
        note += "；无标点也无停顿，未计平均句长"
    return {
        "score": COMPLEXITY_BASE + COMPLEXITY_SPAN * combined,
        "terms": terms,
        "inputs": {
            "word_count": words,
            "sentence_count": sentences,
            "sentence_source": src,
            "mean_sentence_len": round(words_per_sentence, 2) if words_per_sentence else None,
            "complex_markers": markers,
            "mtld": features.get("mtld"),
            "diversity_metric": features.get("diversity_metric"),
            "diversity": features.get("diversity"),
        },
        "note": note,
    }


def evaluate_task(scene_id: str, user_text: str):
    checks = TASK_CHECKS.get(scene_id)
    if not checks:
        return {"score": None, "hits": [], "missed": [], "hit_rate": None, "note": "该场景没有任务清单"}
    low = (user_text or "").lower()
    hits, missed = [], []
    for label, keywords in checks:
        if any(k in low for k in keywords):
            hits.append(label)
        else:
            missed.append(label)
    rate = len(hits) / len(checks)
    return {
        "score": TASK_BASE + TASK_SPAN * rate,
        "hits": hits,
        "missed": missed,
        "hit_rate": rate,
        "note": f"场景任务清单命中 {len(hits)}/{len(checks)}",
    }


def fuse(model_score, rule_score, weight_rule, note=""):
    """模型分与规则分融合；只压不抬。

    返回的 detail 里同时保留 model_score / rule_score / final_score，
    压分时还有 clamped=True 和 clamp_reason，报告里能看懂这次分为什么被改。
    """
    detail = {
        "model_score": round(model_score, 1) if model_score is not None else None,
        "rule_score": round(rule_score, 1) if rule_score is not None else None,
        "final_score": None,
        "weight_rule": weight_rule,
        "clamped": False,
        "clamp_reason": None,
        "note": note,
    }
    if rule_score is None or model_score is None:
        detail["final_score"] = round(model_score, 1) if model_score is not None else None
        detail["note"] = (note + "；" if note else "") + "无规则证据，仅用模型分"
        return detail

    final = (1.0 - weight_rule) * model_score + weight_rule * rule_score
    gap = model_score - rule_score
    if gap > CLAMP_GAP:
        final = rule_score + CLAMP_TO
        detail["clamped"] = True
        detail["clamp_reason"] = (
            f"模型分比规则分高 {gap:.1f} 分（超过 {CLAMP_GAP:.0f}），按“只压不抬”压回规则分 +{CLAMP_TO:.0f}"
        )
    elif -gap > CLAMP_GAP:
        detail["note"] = (note + "；" if note else "") + "模型分显著低于可测指标，请人工复核"
    detail["final_score"] = round(max(0.0, min(100.0, final)), 1)
    return detail


def apply_to_report(data: dict, features: dict, scene_id: str, user_text: str) -> dict:
    """把规则分与模型分融合，重算 dimensions / bands / band / cefr / total_score。

    只应在模型正常返回（source=llm）时调用；降级报告不允许借规则分“凑”出成绩。
    """
    if data.get("source") != "llm":
        return data
    model_bands = data.get("bands") or {}
    if not model_bands:
        return data

    model_scores = {dim: 10.0 * b + 10.0 for dim, b in model_bands.items()}

    fluency = evaluate_fluency(features)
    complexity = evaluate_complexity(features, user_text)
    task = evaluate_task(scene_id, user_text)

    detail = {}
    final_scores = {}

    # 发音：没有规则证据，模型分就是最终分（报告里也这么写）
    if "pronunciation" in model_scores:
        detail["pronunciation"] = fuse(
            model_scores["pronunciation"],
            None,
            0.0,
            note="发音由模型依转写推断（本项目不做声学测评）",
        )
        final_scores["pronunciation"] = detail["pronunciation"]["final_score"]

    if "fluency" in model_scores:
        detail["fluency"] = fuse(
            model_scores["fluency"], fluency["score"], W_RULE_FLUENCY, fluency["note"]
        )
        detail["fluency"]["inputs"] = fluency["inputs"]
        final_scores["fluency"] = detail["fluency"]["final_score"]

    if "grammar_vocab" in model_scores:
        detail["grammar_vocab"] = fuse(
            model_scores["grammar_vocab"],
            complexity["score"],
            W_RULE_GRAMMAR,
            complexity["note"] + "；规则分只测语言范围，准确度来自模型",
        )
        detail["grammar_vocab"]["inputs"] = complexity["inputs"]
        final_scores["grammar_vocab"] = detail["grammar_vocab"]["final_score"]

    if "task_completion" in model_scores:
        detail["task_completion"] = fuse(
            model_scores["task_completion"], task["score"], W_TASK_RULE, task["note"]
        )
        detail["task_completion"]["inputs"] = {
            "hits": task["hits"],
            "missed": task["missed"],
            "hit_rate": task["hit_rate"],
        }
        final_scores["task_completion"] = detail["task_completion"]["final_score"]

    dims = {k: int(round(v)) for k, v in final_scores.items() if v is not None}
    if not dims:
        return data
    total = int(round(sum(dims.values()) / len(dims)))
    band = score_to_band(total)
    used_rules = [k for k, d in detail.items() if d.get("rule_score") is not None]

    out = dict(data)
    out["dimensions"] = dims
    out["bands"] = {k: score_to_band(v) for k, v in dims.items() if score_to_band(v) is not None}
    out["total_score"] = total
    out["band"] = band
    out["cefr"] = band_to_cefr(band)
    out["scoring_detail"] = detail
    out["scoring_note"] = (
        "分数由模型分与可测指标融合得出"
        + (f"（参与融合的维度：{', '.join(used_rules)}）" if used_rules else "")
    )
    return out
