"""Glue between scraping, analysis, alerts and notifications. Called by the scheduler and CLI."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from pricewatch import settings_store
from pricewatch.analysis.decision import Verdict, decide
from pricewatch.analysis.flash import detect
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
    return sorted(
        [
            lk
            for lk in item.links
            if lk.status == LinkStatus.found and lk.last_price and lk.vendor.enabled
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


def _last_alert(s: Session, link_id: int) -> Alert | None:
    return (
        s.query(Alert)
        .filter(Alert.item_vendor_id == link_id, Alert.kind != AlertKind.test)
        .order_by(Alert.created_at.desc())
        .first()
    )


async def scan_and_alert(
    s: Session, item_ids: list[int] | None = None, vendor_ids: list[int] | None = None
) -> dict:
    results = await run_scan(s, item_ids=item_ids, vendor_ids=vendor_ids)
    cfg = settings_store.get_all(s)
    drop_pct = float(cfg.get("flash_drop_pct") or 10)
    cooldown = timedelta(hours=float(cfg.get("alert_cooldown_hours") or 6))
    created: list[Alert] = []
    for link, res, snap in results:
        if snap is None or res.price is None:
            continue
        hist = link_history(s, link.id, exclude_id=snap.id)
        last = _last_alert(s, link.id)
        det = detect(
            price=res.price,
            history=hist,
            now=snap.captured_at,
            target_price=link.item.target_price,
            flash_drop_pct=drop_pct,
            last_alert_at=last.created_at if last else None,
            last_alert_price=last.price if last else None,
            cooldown=cooldown,
        )
        if det is None:
            continue
        if det.kind == AlertKind.all_time_low and cfg.get("notify_all_time_low") != "1":
            continue
        if det.kind == AlertKind.target_hit and cfg.get("notify_target_hit") != "1":
            continue
        label = {
            "flash_sale": "⚡ Flash sale",
            "target_hit": "🎯 Target hit",
            "all_time_low": "📉 All-time low",
        }[det.kind.value]
        alert = Alert(
            item_id=link.item_id,
            item_vendor_id=link.id,
            kind=det.kind,
            title=f"{label}: {link.item.name}",
            message=f"{link.vendor.name}: {res.price:,.0f} EGP — {det.reason}",
            price=res.price,
            baseline=det.baseline,
            url=link.product_url,
        )
        s.add(alert)
        created.append(alert)
    s.flush()
    for a in created:
        await dispatch(s, a)
    found = sum(1 for _, r, _ in results if r.status == LinkStatus.found)
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
