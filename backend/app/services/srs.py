"""间隔重复调度（SM-2 简化版）。

用户每次复习给一个反馈：again / hard / good / easy。
- again：这次没想起来，间隔回到 1 天，熟练度下调；
- hard：小步延长（×1.2），熟练度略降；
- good：按当前熟练度延长（×ease）；
- easy：大步延长（×ease×1.3），熟练度上调。

ease（熟练度）夹在 1.3–2.8，间隔最长 180 天，避免一条卡被排到几年后。
"""

from __future__ import annotations

from datetime import datetime, timedelta

QUALITIES = {"again": 0, "hard": 1, "good": 2, "easy": 3}

EASE_MIN, EASE_MAX = 1.3, 2.8
MAX_INTERVAL_DAYS = 180


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def schedule(
    ease: float,
    interval_days: int,
    reps: int,
    lapses: int,
    quality: str,
    now: datetime | None = None,
):
    """返回 (ease, interval_days, reps, lapses, due_at)。"""
    q = QUALITIES.get(str(quality).lower())
    if q is None:
        raise ValueError("quality 只能是 again / hard / good / easy")

    now = now or datetime.utcnow()
    ease = float(ease or 2.5)
    interval_days = int(interval_days or 0)
    reps = int(reps or 0)
    lapses = int(lapses or 0)

    if q == 0:  # again
        ease = _clamp(ease - 0.2, EASE_MIN, EASE_MAX)
        interval_days = 1
        reps = 0
        lapses += 1
    elif q == 1:  # hard
        ease = _clamp(ease - 0.15, EASE_MIN, EASE_MAX)
        interval_days = 1 if interval_days == 0 else max(1, round(interval_days * 1.2))
        reps += 1
    elif q == 2:  # good
        if reps == 0:
            interval_days = 1
        elif reps == 1:
            interval_days = 6
        else:
            interval_days = max(1, round(interval_days * ease))
        reps += 1
    else:  # easy
        if reps == 0:
            interval_days = 2
        elif reps == 1:
            interval_days = 8
        else:
            interval_days = max(1, round(interval_days * ease * 1.3))
        ease = _clamp(ease + 0.15, EASE_MIN, EASE_MAX)
        reps += 1

    interval_days = min(interval_days, MAX_INTERVAL_DAYS)
    return ease, interval_days, reps, lapses, now + timedelta(days=interval_days)
