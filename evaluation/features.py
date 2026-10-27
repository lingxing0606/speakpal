"""从转写文本（可选词级时间戳）提取流利度与语言复杂度特征。

只用标准库。词级时间戳可选；没有时只能算词数类特征。
"""
from __future__ import annotations

import re

FILLERS = {"um", "uh", "erm", "hmm", "mm", "ah", "like", "well", "actually", "basically"}

_TOKEN_RE = re.compile(r"[A-Za-z']+")


def tokenize(text: str):
    return _TOKEN_RE.findall(text.lower())


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


def fluency_features(transcript: str, word_timings=None, pause_threshold: float = 0.3) -> dict:
    """word_timings: [{"word": str, "start": float, "end": float}, ...] 可选。"""
    tokens = tokenize(transcript)
    n = len(tokens)
    out = {"word_count": n}
    if n == 0:
        return out

    fillers = sum(1 for t in tokens if t in FILLERS)
    out["filler_count"] = fillers
    out["filler_rate"] = fillers / n
    out["ttr"] = len(set(tokens)) / n
    out["mtld"] = mtld(tokens)

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
