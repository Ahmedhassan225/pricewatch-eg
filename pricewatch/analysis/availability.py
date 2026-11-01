"""Stock / availability transitions for one vendor link. Pure, unit-testable."""

from __future__ import annotations

from dataclasses import dataclass

from pricewatch.models import AlertKind, LinkStatus


@dataclass
class StockEvent:
    kind: AlertKind
    reason: str
    good_price: bool = False


def is_available(status: LinkStatus | None, in_stock: bool | None) -> bool:
    return status == LinkStatus.found and in_stock is not False


def detect_stock_change(
    *,
    prev_status: LinkStatus | None,
    prev_in_stock: bool | None,
    prev_price: float | None,
    new_status: LinkStatus,
    new_in_stock: bool | None,
    price: float | None,
    median_30d: float | None,
    target_price: float | None,
    good_price_only: bool,
) -> StockEvent | None:
    """Return an out_of_stock / back_in_stock event, or None.

    A fetch *error* is transient and never counts as a stock change.
    "Back in stock" needs the link to have been seen with a price before, so the very
    first discovery of an item is not reported as a return.
    """
    if new_status == LinkStatus.error:
        return None
    was = is_available(prev_status, prev_in_stock)
    now = is_available(new_status, new_in_stock)
    if was and not now:
        why = "marked out of stock" if new_status == LinkStatus.found else "listing disappeared"
        return StockEvent(AlertKind.out_of_stock, why)
    if not was and now and prev_price is not None and price is not None:
        good = bool(target_price and price <= target_price) or bool(
            median_30d and price <= median_30d
        )
        if good_price_only and not good:
            return None
        if good:
            ref = (
                f"your target {target_price:,.0f}"
                if target_price and price <= target_price
                else (f"the 30-day median {median_30d:,.0f}")
            )
            return StockEvent(
                AlertKind.back_in_stock, f"back in stock at a good price (≤ {ref} EGP)", True
            )
        return StockEvent(AlertKind.back_in_stock, "back in stock")
    return None
