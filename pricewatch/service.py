"""Glue between scraping, analysis, alerts and notifications. Called by the scheduler and CLI."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from pricewatch import settings_store
from pricewatch.analysis.availability import detect_stock_change, is_available
from pricewatch.analysis.decision import Verdict, decide
from pricewatch.analysis.flash import detect
from pricewatch.analysis.stats import safe_median, window
from pricewatch.market import service as market
from pricewatch.models import Alert, AlertKind, Item, ItemVendor, LinkStatus, PriceSnapshot, utcnow
from pricewatch.notify.dispatcher import dispatch
from pricewatch.scraping.engine import run_scan

log = logging.getLogger(__name__)


def link_history(s: Session, link_id: int, days: int = 400, exclude_id: int | None = None):
    since = utcnow() - timedelta(days=days)
    q = s.query(PriceSnapshot).filter(
        PriceSnapshot.item_vendor_id == link_id, PriceSnapshot.captured_at >= since
    )
    if exclude_id is not None:
        q = q.filter(PriceSnapshot.id != exclude_id)
    return [(p.captured_at, p.price) for p in q.order_by(PriceSnapshot.captured_at).all()]


def item_history(s: Session, item: Item, days: int = 400) -> list[tuple]:
    """Cross-vendor minimum price per capture bucket (hour)."""
    link_ids = [lk.id for lk in item.links]
    if not link_ids:
        return []
    since = utcnow() - timedelta(days=days)
    rows = (
        s.query(PriceSnapshot)
        .filter(PriceSnapshot.item_vendor_id.in_(link_ids), PriceSnapshot.captured_at >= since)
        .order_by(PriceSnapshot.captured_at)
        .all()
    )
    buckets: dict = {}
    for r in rows:
        b = r.captured_at.replace(minute=0, second=0, microsecond=0)
        buckets[b] = min(buckets.get(b, r.price), r.price)
    return sorted(buckets.items())


def current_prices(item: Item) -> list[ItemVendor]:
    """Vendors that have the item available right now, cheapest first."""
    return sorted(
        [
            lk
            for lk in item.links
            if is_available(lk.status, lk.in_stock) and lk.last_price and lk.vendor.enabled
        ],
        key=lambda lk: lk.last_price,
    )


def verdict_for(s: Session, item: Item) -> Verdict:
    found = current_prices(item)
    best = found[0].last_price if found else None
    return decide(
        best_price=best,
        history=item_history(s, item),
        now=utcnow(),
        target_price=item.target_price,
        vendor_prices=[lk.last_price for lk in found],
        usd_egp_change_30d_pct=market.change_pct(s, "usd_egp", 30),
        gold_change_30d_pct=market.change_pct(s, "gold_egp_21k_g", 30),
    )


def _last_alert(
    s: Session, link_id: int, kinds: tuple[AlertKind, ...] | None = None
) -> Alert | None:
    q = s.query(Alert).filter(Alert.item_vendor_id == link_id, Alert.kind != AlertKind.test)
    if kinds:
        q = q.filter(Alert.kind.in_(kinds))
    return q.order_by(Alert.created_at.desc()).first()


PRICE_KINDS = (AlertKind.flash_sale, AlertKind.target_hit, AlertKind.all_time_low)
STOCK_KINDS = (AlertKind.back_in_stock, AlertKind.out_of_stock)
LABELS = {
    AlertKind.flash_sale: "⚡ Flash sale",
    AlertKind.target_hit: "🎯 Target hit",
    AlertKind.all_time_low: "📉 All-time low",
    AlertKind.back_in_stock: "✅ Back in stock",
    AlertKind.out_of_stock: "⛔ Out of stock",
    AlertKind.unavailable: "🚫 Unavailable everywhere",
}


def _median_30d(s: Session, item: Item) -> float | None:
    return safe_median(window(item_history(s, item), utcnow(), 30))


async def scan_and_alert(
    s: Session, item_ids: list[int] | None = None, vendor_ids: list[int] | None = None
) -> dict:
    results = await run_scan(s, item_ids=item_ids, vendor_ids=vendor_ids)
    cfg = settings_store.get_all(s)
    on = lambda key: cfg.get(key) == "1"  # noqa: E731
    drop_pct = float(cfg.get("flash_drop_pct") or 10)
    cooldown = timedelta(hours=float(cfg.get("alert_cooldown_hours") or 6))
    created: list[Alert] = []
    touched: dict[int, tuple[Item, bool]] = {}  # item_id -> (item, available_before_scan)

    for link, res, snap, prev in results:
        item = link.item
        if item.id not in touched:
            # availability before this scan: scanned links use their previous state,
            # untouched links their current one
            scanned = {lk.id: pv for lk, _, _, pv in results if lk.item_id == item.id}
            before = any(
                (
                    is_available(scanned[lk.id].status, scanned[lk.id].in_stock)
                    if lk.id in scanned
                    else is_available(lk.status, lk.in_stock)
                )
                for lk in item.links
                if lk.vendor.enabled
            )
            touched[item.id] = (item, before)

        # --- stock transitions ---
        ev = detect_stock_change(
            prev_status=prev.status,
            prev_in_stock=prev.in_stock,
            prev_price=prev.price,
            new_status=res.status,
            new_in_stock=res.in_stock,
            price=res.price,
            median_30d=_median_30d(s, item),
            target_price=item.target_price,
            good_price_only=on("back_in_stock_good_price_only"),
        )
        if ev and on(f"notify_{ev.kind.value}"):
            last = _last_alert(s, link.id, (ev.kind,))
            if not (last and utcnow() - last.created_at < cooldown):
                price_txt = f"{res.price:,.0f} EGP — " if res.price else ""
                created.append(
                    Alert(
                        item_id=item.id,
                        item_vendor_id=link.id,
                        kind=ev.kind,
                        title=f"{LABELS[ev.kind]}: {item.name}",
                        message=f"{link.vendor.name}: {price_txt}{ev.reason}",
                        price=res.price,
                        url=link.product_url,
                    )
                )

        # --- price events (only for available listings) ---
        if snap is None or res.price is None or res.in_stock is False:
            continue
        hist = link_history(s, link.id, exclude_id=snap.id)
        last = _last_alert(s, link.id, PRICE_KINDS)
        det = detect(
            price=res.price,
            history=hist,
            now=snap.captured_at,
            target_price=item.target_price,
            flash_drop_pct=drop_pct,
            last_alert_at=last.created_at if last else None,
            last_alert_price=last.price if last else None,
            cooldown=cooldown,
        )
        if det is None or not on(f"notify_{det.kind.value}"):
            continue
        created.append(
            Alert(
                item_id=item.id,
                item_vendor_id=link.id,
                kind=det.kind,
                title=f"{LABELS[det.kind]}: {item.name}",
                message=f"{link.vendor.name}: {res.price:,.0f} EGP — {det.reason}",
                price=res.price,
                baseline=det.baseline,
                url=link.product_url,
            )
        )

    # --- item-level: nobody has it any more ---
    if on("notify_unavailable"):
        for item, before in touched.values():
            after = any(
                is_available(lk.status, lk.in_stock) for lk in item.links if lk.vendor.enabled
            )
            if before and not after:
                created.append(
                    Alert(
                        item_id=item.id,
                        kind=AlertKind.unavailable,
                        title=f"{LABELS[AlertKind.unavailable]}: {item.name}",
                        message="No enabled vendor lists this item as available right now.",
                    )
                )

    for a in created:
        s.add(a)
    s.commit()  # don't hold the write lock while sending notifications
    if cfg.get("notifications_paused") == "1":
        for a in created:
            a.sent, a.send_error = False, "notifications paused in Settings"
    else:
        for a in created:
            await dispatch(s, a)
    found = sum(1 for _, r, _, _ in results if r.status == LinkStatus.found)
    summary = {"checked": len(results), "found": found, "alerts": len(created)}
    log.info("scan done: %s", summary)
    return summary


async def send_test_alert(s: Session) -> Alert:
    a = Alert(
        kind=AlertKind.test,
        title="PriceWatch test",
        message="Notifications are working 🎉",
        url=None,
    )
    s.add(a)
    s.flush()
    await dispatch(s, a)
    return a
