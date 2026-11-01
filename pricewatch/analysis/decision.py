"""'Should I buy now?' — a transparent 0–100 score with reasons.

Inputs are plain numbers so this module is trivially unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pricewatch.analysis.stats import daily_min, safe_median, slope_per_day, window

BASE_SCORE = 50
MIN_HISTORY_DAYS = 3


@dataclass
class Factor:
    points: int  # what this check added to or took from the score; 0 = checked, no effect
    text: str


@dataclass
class Verdict:
    score: int
    label: str  # BUY NOW | GOOD PRICE | WAIT | WATCH | NO DATA
    reasons: list[str] = field(default_factory=list)
    best_price: float | None = None
    min_30d: float | None = None
    median_30d: float | None = None
    all_time_low: float | None = None
    trend_pct_per_week: float | None = None
    factors: list[Factor] = field(default_factory=list)


def _label(score: int) -> str:
    if score >= 75:
        return "BUY NOW"
    if score >= 60:
        return "GOOD PRICE"
    if score >= 40:
        return "WATCH"
    return "WAIT"


def decide(
    *,
    best_price: float | None,
    history: list[tuple[datetime, float]],  # cross-vendor min price snapshots over time
    now: datetime,
    target_price: float | None = None,
    vendor_prices: list[float] | None = None,
    usd_egp_change_30d_pct: float | None = None,
    gold_change_30d_pct: float | None = None,
) -> Verdict:
    if best_price is None:
        text = "No vendor currently lists this item."
        return Verdict(0, "NO DATA", [text], factors=[Factor(0, text)])

    factors: list[Factor] = []

    def add(points: float, text: str) -> None:
        factors.append(Factor(round(points), text))

    v = Verdict(0, "", best_price=best_price)

    hist30 = window(history, now, 30)
    v.min_30d = min(hist30) if hist30 else None
    v.median_30d = safe_median(hist30)
    v.all_time_low = min([p for _, p in history] + [best_price])
    days_seen = (now - min(t for t, _ in history)).total_seconds() / 86400 if history else 0
    enough_history = days_seen >= MIN_HISTORY_DAYS
    range_days = min(30, int(days_seen))

    # 1) Position inside the observed range, up to 30 days (weight ±25)
    if enough_history:
        lo, hi = min(hist30), max(hist30)
        if hi > lo:
            pos = max(0.0, min(1.0, (best_price - lo) / (hi - lo)))  # 0 = at the low, 1 = high
            add(
                (0.5 - pos) * 50,
                f"Price is {pos * 100:.0f}% of the way from its {range_days}-day low "
                f"to its high ({lo:,.0f}–{hi:,.0f} EGP).",
            )
        else:
            add(0, f"Price has been flat for {range_days} days.")
    else:
        add(-5, f"Less than {MIN_HISTORY_DAYS} days of history — confidence is low.")

    # 2) All-time low bonus
    if enough_history and best_price <= v.all_time_low:
        add(15, "This is the lowest price we have ever recorded.")

    # 3) Target
    if target_price:
        if best_price <= target_price:
            add(15, f"Below your target of {target_price:,.0f} EGP.")
        else:
            gap = (best_price - target_price) / target_price * 100
            add(-min(15, gap / 2), f"{gap:.0f}% above your target of {target_price:,.0f} EGP.")
    else:
        add(0, "No target price set for this item.")

    # 4) Trend of daily minimum over 14 days (weight ±10)
    dm = daily_min([(t, p) for t, p in history if (now - t).days <= 14])
    slope = slope_per_day(dm)
    if slope is not None and v.median_30d:
        weekly = slope * 7 / v.median_30d * 100
        v.trend_pct_per_week = round(weekly, 2)
        if weekly <= -1.5:
            add(-10, f"Prices are trending down ({weekly:.1f}%/week) — waiting may pay off.")
        elif weekly >= 1.5:
            add(10, f"Prices are trending up (+{weekly:.1f}%/week) — delaying likely costs more.")
        else:
            add(0, "Price trend is roughly flat.")
    else:
        add(0, "Not enough days yet to see a price trend.")

    # 5) Vendor spread — a big gap means this vendor is unusually cheap right now
    if vendor_prices and len(vendor_prices) >= 2:
        med = safe_median(vendor_prices)
        if med and best_price < med * 0.92:
            pct = (1 - best_price / med) * 100
            add(8, f"Best vendor is {pct:.0f}% under the vendor median ({med:,.0f} EGP).")
        else:
            add(0, "Best vendor is close to the other vendors' prices.")

    # 6) Macro: EGP weakening or gold spiking → imported electronics get repriced upward
    if usd_egp_change_30d_pct is not None:
        fx = usd_egp_change_30d_pct
        if fx >= 3:
            add(8, f"USD/EGP is up {fx:.1f}% in 30 days — imported goods usually follow.")
        elif fx <= -3:
            add(-5, f"USD/EGP is down {abs(fx):.1f}% in 30 days — prices may soften.")
        else:
            add(0, f"USD/EGP moved {fx:+.1f}%, too little to change the score.")
    if gold_change_30d_pct is not None:
        gold = gold_change_30d_pct
        if gold >= 5:
            add(3, f"Gold (21K EGP) is up {gold:.1f}% — inflation pressure is rising.")
        else:
            add(0, f"Gold (21K EGP) moved {gold:+.1f}%, too little to change the score.")

    v.score = int(max(0, min(100, BASE_SCORE + sum(f.points for f in factors))))
    v.label = _label(v.score)
    v.factors = factors
    v.reasons = [f.text for f in factors]
    return v
