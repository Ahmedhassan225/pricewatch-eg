"""'Should I buy now?' — a transparent 0–100 score with reasons.

Inputs are plain numbers so this module is trivially unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pricewatch.analysis.stats import daily_min, safe_median, slope_per_day, window


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
        return Verdict(0, "NO DATA", ["No vendor currently lists this item."])

    reasons: list[str] = []
    score = 50.0
    v = Verdict(0, "", best_price=best_price)

    hist30 = window(history, now, 30)
    v.min_30d = min(hist30) if hist30 else None
    v.median_30d = safe_median(hist30)
    v.all_time_low = min([p for _, p in history] + [best_price])

    # 1) Position inside the 30-day range (weight ±25)
    if hist30 and len(hist30) >= 3:
        lo, hi = min(hist30), max(hist30)
        if hi > lo:
            pos = (best_price - lo) / (hi - lo)  # 0 = at the low, 1 = at the high
            score += (0.5 - pos) * 50
            reasons.append(
                f"Price sits at {pos * 100:.0f}% of its 30-day range ({lo:,.0f}–{hi:,.0f} EGP)."
            )
        else:
            reasons.append("Price has been flat for 30 days.")
    else:
        score -= 5
        reasons.append("Less than 3 days of history — confidence is low.")

    # 2) All-time low bonus
    if len(history) >= 5 and best_price <= v.all_time_low:
        score += 15
        reasons.append("This is the lowest price we have ever recorded.")

    # 3) Target
    if target_price:
        if best_price <= target_price:
            score += 15
            reasons.append(f"Below your target of {target_price:,.0f} EGP.")
        else:
            gap = (best_price - target_price) / target_price * 100
            score -= min(15, gap / 2)
            reasons.append(f"{gap:.0f}% above your target of {target_price:,.0f} EGP.")

    # 4) Trend of daily minimum over 14 days (weight ±10)
    dm = daily_min([(t, p) for t, p in history if (now - t).days <= 14])
    slope = slope_per_day(dm)
    if slope is not None and v.median_30d:
        weekly = slope * 7 / v.median_30d * 100
        v.trend_pct_per_week = round(weekly, 2)
        if weekly <= -1.5:
            score -= 10
            reasons.append(f"Prices are trending down ({weekly:.1f}%/week) — waiting may pay off.")
        elif weekly >= 1.5:
            score += 10
            reasons.append(
                f"Prices are trending up (+{weekly:.1f}%/week) — delaying likely costs more."
            )
        else:
            reasons.append("Price trend is roughly flat.")

    # 5) Vendor spread — a big gap means this vendor is unusually cheap right now
    if vendor_prices and len(vendor_prices) >= 2:
        med = safe_median(vendor_prices)
        if med and best_price < med * 0.92:
            score += 8
            pct = (1 - best_price / med) * 100
            reasons.append(f"Best vendor is {pct:.0f}% under the vendor median ({med:,.0f} EGP).")

    # 6) Macro: EGP weakening or gold spiking → imported electronics get repriced upward
    if usd_egp_change_30d_pct is not None:
        if usd_egp_change_30d_pct >= 3:
            score += 8
            fx = usd_egp_change_30d_pct
            reasons.append(f"USD/EGP is up {fx:.1f}% in 30 days — imported goods usually follow.")
        elif usd_egp_change_30d_pct <= -3:
            score -= 5
            fx = abs(usd_egp_change_30d_pct)
            reasons.append(f"USD/EGP is down {fx:.1f}% in 30 days — prices may soften.")
    if gold_change_30d_pct is not None and gold_change_30d_pct >= 5:
        score += 3
        reasons.append(
            f"Gold (21K EGP) is up {gold_change_30d_pct:.1f}% — inflation pressure is rising."
        )

    v.score = int(max(0, min(100, round(score))))
    v.label = _label(v.score)
    v.reasons = reasons
    return v
