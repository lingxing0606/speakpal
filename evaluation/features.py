"""从转写文本（可选词级时间戳）提取流利度与语言复杂度特征。

只用标准库。词级时间戳可选；没有时只能算词数类特征。
"""
from __future__ import annotations

import re

# 硬填充词：几乎不可能是实词，出现即计入。
HARD_FILLERS = {"um", "uh", "erm", "hmm", "mm", "ah"}

# 软话语标记：本身是实词（I'd *like* a latte / *as well* as），
# 只有出现在句首、逗号/停顿之后、或紧跟在另一个填充词之后，才算话语标记。
SOFT_MARKERS = {"like", "well", "actually", "basically"}

# 兼容旧接口：合起来仍是“填充词表”。判定请用 find_fillers()。
FILLERS = HARD_FILLERS | SOFT_MARKERS

# 软标记前面的间隔里出现这些字符，视为一次停顿。
_PAUSE_RE = re.compile(r"[,;:—–]")
_SENTENCE_END_RE = re.compile(r"[.!?]")

_TOKEN_RE = re.compile(r"[A-Za-z']+")

# MTLD 在短文本上会顶格（14 词简单句能算出 54+），低于该词数一律回退 TTR。
MIN_TOKENS_FOR_MTLD = 50


def tokenize(text: str):
    return _TOKEN_RE.findall(text.lower())


def find_fillers(text: str):
    """按位置判定填充词，返回 (个数, 命中的词)。

    - um/uh/erm/hmm/mm/ah：出现即算。
    - like/well/actually/basically：句首、标点或停顿之后、或紧跟另一个填充词才算。
      所以 "I'd like a latte" 不算，"like, I'd like a latte" 算；
      "as well as" 里的 well 前面是 as，也不算。
    """
    matches = list(_TOKEN_RE.finditer(text or ""))
    count = 0
    matched = []
    prev_end = None
    prev_was_filler = False
    for m in matches:
        tok = m.group(0).lower()
        gap = text[prev_end : m.start()] if prev_end is not None else ""
        counted = False
        if tok in HARD_FILLERS:
            counted = True
        elif tok in SOFT_MARKERS:
            at_start = prev_end is None or _SENTENCE_END_RE.search(gap) is not None
            after_pause = bool(_PAUSE_RE.search(gap))
            if at_start or after_pause or prev_was_filler:
                counted = True
        if counted:
            count += 1
            matched.append(tok)
        prev_end = m.end()
        prev_was_filler = counted
    return count, matched


def mtld(tokens, threshold: float = 0.72, min_tokens: int = 10) -> float:
    """MTLD 近似实现（前向 + 后向平均），用于词汇多样性。"""
    if not tokens:
        return 0.0

    def one_pass(seq):
        factors = 0.0
        types = set()
        seen = 0
        for w in seq:
            types.add(w)
            seen += 1
            if seen >= min_tokens and len(types) / seen < threshold:
                factors += 1.0
                types = set()
                seen = 0
        if seen > 0:
            ttr = len(types) / seen
            factors += max((1.0 - ttr) / (1.0 - threshold), 0.0)
        return factors

    forward = one_pass(tokens)
    backward = one_pass(list(reversed(tokens)))
    denom = (forward + backward) / 2.0
    if denom <= 0:
        return float(len(tokens))
    return len(tokens) / denom


def lexical_diversity(tokens):
    """词汇多样性的取值口径：不足 MIN_TOKENS_FOR_MTLD 词用 TTR，否则用 MTLD。

    返回 (metric, value)。短文本上 MTLD 会虚高：一句 14 词、几乎不重复的话能算出
    mtld≈54.9，接近“词汇多样性满分”，所以必须回退到 TTR 并标出口径。
    """
    n = len(tokens)
    if n == 0:
        return "ttr", 0.0
    if n < MIN_TOKENS_FOR_MTLD:
        return "ttr", len(set(tokens)) / n
    return "mtld", mtld(tokens)


def fluency_features(transcript: str, word_timings=None, pause_threshold: float = 0.3) -> dict:
    """word_timings: [{"word": str, "start": float, "end": float}, ...] 可选。"""
    tokens = tokenize(transcript)
    n = len(tokens)
    out = {"word_count": n}
    if n == 0:
        return out

    filler_count, filler_tokens = find_fillers(transcript)
    out["filler_count"] = filler_count
    out["filler_rate"] = filler_count / n
    out["ttr"] = len(set(tokens)) / n
    metric, value = lexical_diversity(tokens)
    out["diversity_metric"] = metric
    out["diversity"] = value
    # 短文本上 MTLD 没有意义（14 词简单句能算出 54+），不足 50 词时不输出。
    out["mtld"] = mtld(tokens) if n >= MIN_TOKENS_FOR_MTLD else None

    sentences = [s for s in re.split(r"[.!?]+", transcript) if s.strip()]
    out["sentence_count"] = len(sentences)
    out["mean_sentence_len"] = n / len(sentences) if sentences else n

    if word_timings:
        starts = [w["start"] for w in word_timings]
        ends = [w["end"] for w in word_timings]
        duration = max(ends) - min(starts)
        out["duration_sec"] = duration
        out["speech_rate_wpm"] = (n / duration * 60.0) if duration > 0 else None

        pauses = []
        for i in range(1, len(word_timings)):
            gap = word_timings[i]["start"] - word_timings[i - 1]["end"]
            if gap >= pause_threshold:
                pauses.append(gap)
        out["pause_count"] = len(pauses)
        out["mean_pause_sec"] = (sum(pauses) / len(pauses)) if pauses else 0.0

        speaking_time = sum(max(w["end"] - w["start"], 0.0) for w in word_timings)
        out["articulation_rate_wpm"] = (n / speaking_time * 60.0) if speaking_time > 0 else None
        out["pause_ratio"] = (sum(pauses) / duration) if duration > 0 else 0.0

    return out


def speech_features(turn_word_counts, audio_metas, pause_min: float = 0.15) -> dict:
    """从每轮录音元信息聚合语速、停顿等声学特征。

    audio_metas: [{"duration_sec": float, "speech_time_sec": float, "pauses": [..]}]
    """
    total_words = sum(turn_word_counts)
    durations = sum(float((m or {}).get("duration_sec") or 0) for m in audio_metas)
    speech_time = sum(float((m or {}).get("speech_time_sec") or 0) for m in audio_metas)

    pauses = []
    for m in audio_metas:
        for p in (m or {}).get("pauses") or []:
            try:
                v = float(p)
            except (TypeError, ValueError):
                continue
            if v >= pause_min:
                pauses.append(v)

    out = {}
    if durations > 0:
        out["audio_duration_sec"] = round(durations, 2)
        out["speech_rate_wpm"] = total_words / durations * 60.0
        out["pause_ratio"] = sum(pauses) / durations
    if speech_time > 0:
        out["articulation_rate_wpm"] = total_words / speech_time * 60.0
    out["pause_count"] = len(pauses)
    out["mean_pause_sec"] = (sum(pauses) / len(pauses)) if pauses else 0.0
    return out
