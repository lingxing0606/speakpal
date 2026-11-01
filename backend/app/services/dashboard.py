"""学习数据面板：打卡、热力图、各维度均分。纯函数，方便单测。

口径（docs/design.md §19）：
- 「练习日」= 这一天至少发过一轮作答（user turn），按用户本地时区切日。
- 连续天数：从今天往回数；今天还没练不算断，从昨天接着数。
- 维度均分只用正式计分的报告（source=llm），示例报告不计分也不进来；
  每个维度只在含有它的报告里平均（发音/流利度只来自录音轮，文字表达只来自打字轮），附样本数。
- 近 7 天变化用可比 band（只含两种作答方式都评的共享维度），和成长曲线同一口径。
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Iterable

HEATMAP_WEEKS = 12
DIMENSION_ORDER = (
    "pronunciation",
    "fluency",
    "grammar_vocab",
    "task_completion",
    "written_expression",
)


def local_day(dt: datetime, tz_offset_min: int) -> date:
    """库里是 naive UTC；tz_offset_min 用 JS getTimezoneOffset() 的口径（北京时间 = -480）。"""
    return (dt - timedelta(minutes=tz_offset_min)).date()


def streaks(days: set[date], today: date) -> tuple[int, int]:
    """返回 (当前连续天数, 历史最长连续天数)。"""
    current = 0
    cursor = today if today in days else today - timedelta(days=1)
    while cursor in days:
        current += 1
        cursor -= timedelta(days=1)
    longest = run = 0
    prev = None
    for d in sorted(days):
        run = run + 1 if prev is not None and d - prev == timedelta(days=1) else 1
        longest = max(longest, run)
        prev = d
    return current, longest


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def build_dashboard(
    turn_times: Iterable[datetime],
    reports: Iterable[dict],
    now_utc: datetime,
    tz_offset_min: int = 0,
) -> dict:
    """turn_times：用户每一轮作答的时间；reports：{created_at, source, dimensions, comparable_band}。"""
    today = local_day(now_utc, tz_offset_min)
    per_day = Counter(local_day(t, tz_offset_min) for t in turn_times)
    current, longest = streaks(set(per_day), today)

    # 热力图：最近 12 周，按周一对齐，最后一列包含今天
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=HEATMAP_WEEKS - 1)
    heatmap = []
    d = start
    while d <= today:
        heatmap.append({"date": d.isoformat(), "count": per_day.get(d, 0)})
        d += timedelta(days=1)

    scored = [r for r in reports if r.get("source") == "llm"]
    dims = []
    for name in DIMENSION_ORDER:
        vals = [
            float(r["dimensions"][name])
            for r in scored
            if isinstance(r.get("dimensions"), dict)
            and isinstance(r["dimensions"].get(name), (int, float))
        ]
        if vals:
            dims.append({"name": name, "avg": round(sum(vals) / len(vals), 1), "samples": len(vals)})

    recent_cut = today - timedelta(days=6)
    prev_cut = today - timedelta(days=13)
    recent, previous = [], []
    for r in scored:
        band = r.get("comparable_band")
        if band is None:
            continue
        day = local_day(r["created_at"], tz_offset_min)
        if recent_cut <= day <= today:
            recent.append(float(band))
        elif prev_cut <= day < recent_cut:
            previous.append(float(band))
    recent_avg, prev_avg = _avg(recent), _avg(previous)
    delta = round(recent_avg - prev_avg, 2) if recent_avg is not None and prev_avg is not None else None

    return {
        "today": today.isoformat(),
        "current_streak": current,
        "longest_streak": longest,
        "practice_days": len(per_day),
        "practiced_today": today in per_day,
        "total_turns": sum(per_day.values()),
        "scored_reports": len(scored),
        "heatmap": heatmap,
        "dimensions": dims,
        "week": {
            "recent_band": recent_avg,
            "recent_count": len(recent),
            "previous_band": prev_avg,
            "previous_count": len(previous),
            "delta": delta,
        },
    }
