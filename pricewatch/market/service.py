from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from pricewatch.market.providers import fetch_all
from pricewatch.models import MarketRate, utcnow

KINDS = ("usd_egp", "gold_usd_oz", "gold_egp_21k_g")


async def refresh_market(s: Session) -> list[MarketRate]:
    rows = []
    for q in await fetch_all():
        row = MarketRate(kind=q.kind, value=q.value, source=q.source)
        s.add(row)
        rows.append(row)
    s.flush()
    return rows


def latest(s: Session, kind: str) -> MarketRate | None:
    return (
        s.query(MarketRate)
        .filter(MarketRate.kind == kind)
        .order_by(MarketRate.captured_at.desc())
        .first()
    )


def series(s: Session, kind: str, days: int = 90) -> list[tuple[str, float]]:
    """Daily last value for charts."""
    since = utcnow() - timedelta(days=days)
    rows = (
        s.query(func.date(MarketRate.captured_at), func.max(MarketRate.id))
        .filter(MarketRate.kind == kind, MarketRate.captured_at >= since)
        .group_by(func.date(MarketRate.captured_at))
        .order_by(func.date(MarketRate.captured_at))
        .all()
    )
    ids = [r[1] for r in rows]
    if not ids:
        return []
    vals = {m.id: m.value for m in s.query(MarketRate).filter(MarketRate.id.in_(ids)).all()}
    return [(str(d), vals[i]) for d, i in rows]


def change_pct(s: Session, kind: str, days: int) -> float | None:
    cur = latest(s, kind)
    if cur is None:
        return None
    since = utcnow() - timedelta(days=days)
    ref = (
        s.query(MarketRate)
        .filter(MarketRate.kind == kind, MarketRate.captured_at <= since)
        .order_by(MarketRate.captured_at.desc())
        .first()
    )
    if ref is None:
        ref = (
            s.query(MarketRate)
            .filter(MarketRate.kind == kind)
            .order_by(MarketRate.captured_at.asc())
            .first()
        )
    if ref is None or ref.id == cur.id or ref.value == 0:
        return None
    return round((cur.value - ref.value) / ref.value * 100, 2)
