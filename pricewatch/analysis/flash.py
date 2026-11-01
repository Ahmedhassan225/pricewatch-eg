"""Flash-sale / notable-price detection for one new snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from pricewatch.analysis.stats import safe_median, window
from pricewatch.models import AlertKind


@dataclass
class Detection:
    kind: AlertKind
    price: float
    baseline: float | None
    reason: str


def detect(
    *,
    price: float,
    history: list[
        tuple[datetime, float]
    ],  # previous snapshots for this vendor link, excluding `price`
    now: datetime,
    target_price: float | None,
    flash_drop_pct: float,
    last_alert_at: datetime | None,
    last_alert_price: float | None,
    cooldown: timedelta,
) -> Detection | None:
    """Return the most important detection, or None.

    Priority: target hit > flash drop vs 7-day median > new all-time low.
    Cooldown: suppress unless the price is lower than the last alerted price.
    """
    in_cooldown = last_alert_at is not None and now - last_alert_at < cooldown
    if in_cooldown and (last_alert_price is None or price >= last_alert_price):
        return None

    if target_price and price <= target_price:
        return Detection(
            AlertKind.target_hit,
            price,
            target_price,
            f"at or below your target {target_price:,.0f} EGP",
        )

    recent = window(history, now, 7)
    med7 = safe_median(recent) if len(recent) >= 3 else None
    if med7 and med7 > 0:
        drop = (med7 - price) / med7 * 100
        if drop >= flash_drop_pct:
            return Detection(
                AlertKind.flash_sale,
                price,
                med7,
                f"{drop:.0f}% below the 7-day median {med7:,.0f} EGP",
            )

    if len(history) >= 5:
        prev_min = min(p for _, p in history)
        if price < prev_min * 0.97:
            return Detection(
                AlertKind.all_time_low,
                price,
                prev_min,
                f"new all-time low (previous {prev_min:,.0f} EGP)",
            )
    return None
