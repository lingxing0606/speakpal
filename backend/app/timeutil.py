"""时间出口统一：库里存的是 naive UTC，API 一律输出带 `Z` 的 UTC ISO。

不这么做的话，前端 `new Date('2026-10-29T05:23:11')` 会按本地时区解析，
显示成 05:23 而不是 13:23（差 8 小时）。带 `Z` 就没有歧义。
"""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """naive UTC 当前时间（库里一直存 naive UTC）。替代已弃用的 datetime.utcnow()。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
