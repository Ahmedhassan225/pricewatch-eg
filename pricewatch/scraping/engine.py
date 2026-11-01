"""One scan cycle: for every enabled item × enabled vendor, discover or refresh the price."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import quote_plus

from sqlalchemy.orm import Session

from pricewatch import settings_store
from pricewatch.models import Item, ItemVendor, LinkStatus, PriceSnapshot, Strategy, Vendor, utcnow
from pricewatch.scraping.extractors import (
    extract_candidates,
    extract_product_price,
    extract_shopify_suggest,
    extract_woocommerce,
    shopify_suggest_url,
    woocommerce_search_url,
)
from pricewatch.scraping.fetcher import Fetcher
from pricewatch.scraping.matcher import Candidate, best_match

log = logging.getLogger(__name__)


@dataclass
class PrevState:
    status: LinkStatus
    in_stock: bool | None
    price: float | None


@dataclass
class LinkResult:
    item_id: int
    vendor_id: int
    status: LinkStatus
    price: float | None = None
    url: str | None = None
    title: str | None = None
    score: float | None = None
    in_stock: bool = True
    error: str | None = None
    strategy_used: str = ""
    candidates: list[Candidate] = field(default_factory=list)


async def search_vendor(
    fetcher: Fetcher, vendor: Vendor, query: str
) -> tuple[list[Candidate], str, str | None]:
    """Run a search on one vendor. Returns (candidates, strategy_used, error)."""
    q = quote_plus(query)
    if vendor.strategy in (Strategy.shopify, Strategy.auto) and "{q}" in vendor.search_url:
        # Shopify fast path — cheap JSON, no browser.
        if vendor.strategy == Strategy.shopify or "myshopify" in vendor.notes.lower():
            r = await fetcher.fetch_http(shopify_suggest_url(vendor.base_url, query))
            if r.ok and r.text.lstrip().startswith("{"):
                cands = extract_shopify_suggest(r.text, vendor.base_url)
                if cands:
                    return cands, "shopify", None
    if vendor.strategy == Strategy.woocommerce:
        r = await fetcher.fetch_http(woocommerce_search_url(vendor.base_url, query))
        if r.ok and r.text.lstrip().startswith("["):
            return extract_woocommerce(r.text, vendor.base_url), "woocommerce", None
        if r.ok and r.text.lstrip().startswith("{"):
            return [], "woocommerce", "Store API error: " + r.text[:120]
        # fall through to the HTML search page
    url = vendor.search_url.replace("{q}", q)
    wait_sel = (vendor.selectors or {}).get("card")
    r = await fetcher.fetch(url, render_js=vendor.render_js, wait_selector=wait_sel)
    if not r.ok:
        return [], "", r.error or f"HTTP {r.status}"
    if r.blocked and r.used_browser:
        return [], "", f"blocked by bot protection (HTTP {r.status})"
    cands, used = extract_candidates(
        r.text, vendor.base_url, vendor.strategy.value, vendor.selectors or {}
    )
    return cands, used, None


async def refresh_pinned(fetcher: Fetcher, vendor: Vendor, link: ItemVendor) -> LinkResult:
    assert link.product_url
    sel = (vendor.selectors or {}).get("product_price")
    r = await fetcher.fetch(link.product_url, render_js=vendor.render_js, wait_selector=sel)
    if not r.ok:
        return LinkResult(
            link.item_id,
            vendor.id,
            LinkStatus.error,
            url=link.product_url,
            error=r.error or f"HTTP {r.status}",
        )
    price, in_stock, title = extract_product_price(r.text, vendor.selectors or {})
    if price is None:
        return LinkResult(
            link.item_id,
            vendor.id,
            LinkStatus.error,
            url=link.product_url,
            title=title,
            error="price not found on product page (tune product_price selector)",
        )
    return LinkResult(
        link.item_id,
        vendor.id,
        LinkStatus.found,
        price=price,
        url=link.product_url,
        title=title or link.title,
        in_stock=in_stock,
        strategy_used="product",
    )


async def check_link(
    fetcher: Fetcher, vendor: Vendor, item: Item, link: ItemVendor, threshold: float
) -> LinkResult:
    try:
        if link.product_url and (link.pinned or link.status == LinkStatus.found):
            res = await refresh_pinned(fetcher, vendor, link)
            if res.status == LinkStatus.found or link.pinned:
                return res
            # discovered URL went stale → fall through to a fresh search
        cands, used, err = await search_vendor(fetcher, vendor, item.query)
        if err:
            return LinkResult(
                item.id,
                vendor.id,
                LinkStatus.error,
                error=err,
                strategy_used=used,
                candidates=cands,
            )
        best = best_match(item.query, cands, threshold)
        if best is None:
            return LinkResult(
                item.id, vendor.id, LinkStatus.not_found, strategy_used=used, candidates=cands
            )
        return LinkResult(
            item.id,
            vendor.id,
            LinkStatus.found,
            price=best.price,
            url=best.url,
            title=best.title,
            score=best.score,
            in_stock=best.in_stock,
            strategy_used=used,
            candidates=cands,
        )
    except Exception as e:  # noqa: BLE001 — one vendor must never break the cycle
        log.exception("check_link failed for %s / %s", vendor.slug, item.name)
        return LinkResult(item.id, vendor.id, LinkStatus.error, error=f"{type(e).__name__}: {e}")


def apply_result(s: Session, link: ItemVendor, res: LinkResult) -> PriceSnapshot | None:
    now = utcnow()
    link.last_checked_at = now
    link.status = res.status
    link.last_error = res.error
    if res.status == LinkStatus.found:
        link.product_url = res.url or link.product_url
        link.title = res.title or link.title
        link.match_score = res.score if res.score is not None else link.match_score
        link.last_price = res.price
        link.in_stock = res.in_stock
        snap = PriceSnapshot(
            item_vendor_id=link.id, price=res.price, in_stock=res.in_stock, captured_at=now
        )
        s.add(snap)
        return snap
    if res.status == LinkStatus.not_found:
        link.in_stock = False
        if not link.pinned:
            link.product_url = None
    return None


def ensure_links(s: Session, item: Item, vendors: list[Vendor]) -> list[ItemVendor]:
    existing = {lk.vendor_id: lk for lk in item.links}
    for v in vendors:
        if v.id not in existing:
            lk = ItemVendor(item_id=item.id, vendor_id=v.id)
            s.add(lk)
            item.links.append(lk)
            existing[v.id] = lk
    s.flush()
    return [existing[v.id] for v in vendors]


def _vendor_due(v: Vendor) -> bool:
    if not v.min_interval_sec or v.last_scanned_at is None:
        return True
    return utcnow() - v.last_scanned_at >= timedelta(seconds=v.min_interval_sec)


async def run_scan(
    s: Session, item_ids: list[int] | None = None, vendor_ids: list[int] | None = None
) -> list[tuple[ItemVendor, LinkResult, PriceSnapshot | None, PrevState]]:
    """Scan and persist. Returns (link, result, new_snapshot) tuples for the analysis stage."""
    threshold = settings_store.get_float(s, "match_threshold", 70)
    vendors = [
        v
        for v in s.query(Vendor).filter(Vendor.enabled.is_(True)).all()
        if (vendor_ids is None or v.id in vendor_ids)
    ]
    vendors = [v for v in vendors if _vendor_due(v)]
    items_q = s.query(Item).filter(Item.enabled.is_(True))
    if item_ids is not None:
        items_q = items_q.filter(Item.id.in_(item_ids))
    items = items_q.all()
    if not vendors or not items:
        return []

    jobs: list[tuple[ItemVendor, Vendor, Item]] = []
    vendor_by_id = {v.id: v for v in vendors}
    for item in items:
        for lk in ensure_links(s, item, vendors):
            jobs.append((lk, vendor_by_id[lk.vendor_id], item))

    results: list[tuple[ItemVendor, LinkResult, PriceSnapshot | None, PrevState]] = []
    async with Fetcher() as fetcher:
        coros = [check_link(fetcher, v, it, lk, threshold) for lk, v, it in jobs]
        outcomes = await asyncio.gather(*coros, return_exceptions=False)
    for (lk, v, _), res in zip(jobs, outcomes, strict=True):
        prev = PrevState(lk.status, lk.in_stock, lk.last_price)
        snap = apply_result(s, lk, res)
        v.last_scanned_at = utcnow()
        results.append((lk, res, snap, prev))
    s.flush()
    return results
