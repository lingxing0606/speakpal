"""间隔重复调度（简化 SM-2，按 docs/design.md §16.2 实现）。

三档反馈：`again`（忘了）/ `hard`（模糊）/ `good`（认识）。
- again：间隔记 1 天，但 **due_at +10 分钟**（本场重排到队尾、今天内还会再出现），lapses +1；
- hard：max(1, interval × 1.2) 天；
- good：max(1, interval × 2.5) 天。
间隔上限 60 天。

ease（难度因子）按 SM-2：again −0.2、hard −0.15、good +0.1，下限 1.3。
"""

from __future__ import annotations

from datetime import datetime, timedelta

RESULTS = ("again", "hard", "good")

INTERVAL_CAP_DAYS = 60
EASE_MIN, EASE_MAX = 1.3, 2.8
# again 之后「今天内还会再出现」：给 10 分钟，避免立刻原地打转
AGAIN_DELAY = timedelta(minutes=10)


def schedule(
    ease: float,
    interval_days: float,
    reps: int,
    lapses: int,
    result: str,
    now: datetime | None = None,
):
    """返回 (ease, interval_days, reps, lapses, due_at)。"""
    key = str(result or "").strip().lower()
    if key not in RESULTS:
        raise ValueError("result 只能是 again / hard / good")

    now = now or datetime.utcnow()
    ease = float(ease or 2.5)
    interval_days = float(interval_days or 0)
    reps = int(reps or 0)
    lapses = int(lapses or 0)

    if key == "again":
        ease = max(EASE_MIN, min(EASE_MAX, ease - 0.2))
        interval_days = 1.0
        reps += 1
        lapses += 1
        return ease, interval_days, reps, lapses, now + AGAIN_DELAY

    if key == "hard":
        ease = max(EASE_MIN, min(EASE_MAX, ease - 0.15))
        interval_days = 1.0 if interval_days <= 0 else max(1.0, round(interval_days * 1.2, 1))
    else:  # good
        ease = max(EASE_MIN, min(EASE_MAX, ease + 0.1))
        interval_days = 1.0 if interval_days <= 0 else max(1.0, round(interval_days * 2.5, 1))

    interval_days = min(interval_days, float(INTERVAL_CAP_DAYS))
    reps += 1
    return ease, interval_days, reps, lapses, now + timedelta(days=interval_days)
