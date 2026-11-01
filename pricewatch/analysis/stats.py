"""Small pure helpers over (timestamp, price) series. No DB, no network."""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median


def window(points: list[tuple[datetime, float]], now: datetime, days: int) -> list[float]:
    since = now - timedelta(days=days)
    return [p for t, p in points if t >= since]


def slope_per_day(points: list[tuple[datetime, float]]) -> float | None:
    """Least-squares slope of price vs. days. None with < 3 points."""
    if len(points) < 3:
        return None
    t0 = points[0][0]
    xs = [(t - t0).total_seconds() / 86400 for t, _ in points]
    ys = [p for _, p in points]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sxx


def daily_min(points: list[tuple[datetime, float]]) -> list[tuple[datetime, float]]:
    by_day: dict[datetime, float] = {}
    for t, p in points:
        d = t.replace(hour=0, minute=0, second=0, microsecond=0)
        by_day[d] = min(by_day.get(d, p), p)
    return sorted(by_day.items())


def safe_median(xs: list[float]) -> float | None:
    return median(xs) if xs else None
