from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from pricewatch import scheduler, settings_store
from pricewatch.db import get_session
from pricewatch.market import service as market
from pricewatch.models import (
    Alert,
    Item,
    ItemVendor,
    LinkStatus,
    PriceSnapshot,
    Strategy,
    Vendor,
    utcnow,
)
from pricewatch.notify.dispatcher import channels_configured
from pricewatch.scraping.engine import search_vendor
from pricewatch.scraping.fetcher import Fetcher
from pricewatch.service import (
    current_prices,
    item_history,
    scan_and_alert,
    send_test_alert,
    verdict_for,
)
from pricewatch.web.auth import auth_enabled

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _fmt_money(v: float | None) -> str:
    return "—" if v is None else f"{v:,.0f}"


def _ago(dt) -> str:
    if dt is None:
        return "never"
    secs = int((utcnow() - dt).total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


templates.env.filters["money"] = _fmt_money
templates.env.filters["ago"] = _ago


def render(request: Request, name: str, s: Session, **ctx):
    ctx.setdefault("channels", channels_configured(s))
    ctx.setdefault("sched", scheduler.state)
    ctx.setdefault("paused", settings_store.get(s, "notifications_paused") == "1")
    ctx.setdefault("auth_on", auth_enabled())
    return templates.TemplateResponse(request, name, ctx)


# ---------------- Dashboard ----------------
@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, s: Session = Depends(get_session, scope="function")):
    items = s.query(Item).order_by(Item.created_at.desc()).all()
    rows = []
    for it in items:
        found = current_prices(it)
        v = verdict_for(s, it)
        hist = item_history(s, it, days=30)
        rows.append(
            {
                "item": it,
                "best": found[0] if found else None,
                "found_count": len(found),
                "vendor_count": sum(1 for lk in it.links if lk.vendor.enabled),
                "verdict": v,
                "spark": [p for _, p in hist][-60:],
            }
        )
    fx, gold, gold21 = (market.latest(s, k) for k in ("usd_egp", "gold_usd_oz", "gold_egp_21k_g"))
    alerts = s.query(Alert).order_by(Alert.created_at.desc()).limit(8).all()
    return render(
        request,
        "dashboard.html",
        s,
        rows=rows,
        fx=fx,
        gold=gold,
        gold21=gold21,
        fx_chg=market.change_pct(s, "usd_egp", 30),
        gold_chg=market.change_pct(s, "gold_egp_21k_g", 30),
        alerts=alerts,
        active="dashboard",
    )


@router.get("/api/market/{kind}")
def api_market(kind: str, days: int = 90, s: Session = Depends(get_session, scope="function")):
    if kind not in market.KINDS:
        raise HTTPException(404)
    return {"kind": kind, "points": market.series(s, kind, days)}


@router.get("/api/status")
def api_status():
    st = dict(scheduler.state)
    for k in ("last_scan", "last_market"):
        st[k] = st[k].isoformat() if st[k] else None
    return st


# ---------------- Items ----------------
@router.post("/items")
def add_item(
    name: str = Form(...),
    query: str = Form(""),
    category: str = Form("Home electronics"),
    target_price: str = Form(""),
    s: Session = Depends(get_session, scope="function"),
):
    it = Item(
        name=name.strip(),
        query=(query or name).strip(),
        category=category.strip() or "Home electronics",
        target_price=float(target_price) if target_price.strip() else None,
    )
    s.add(it)
    s.flush()
    return RedirectResponse(f"/items/{it.id}", status_code=303)


@router.get("/items/{item_id}", response_class=HTMLResponse)
def item_detail(
    item_id: int,
    request: Request,
    s: Session = Depends(get_session, scope="function"),
    msg: str = "",
):
    it = s.get(Item, item_id)
    if not it:
        raise HTTPException(404)
    vendors = s.query(Vendor).filter(Vendor.enabled.is_(True)).order_by(Vendor.name).all()
    links = {lk.vendor_id: lk for lk in it.links}
    rows = [(v, links.get(v.id)) for v in vendors]
    rows.sort(
        key=lambda r: (
            r[1] is None or r[1].status != LinkStatus.found,
            (r[1].last_price if r[1] and r[1].last_price else 1e18),
        )
    )
    v = verdict_for(s, it)
    hist = item_history(s, it, days=90)
    alerts = (
        s.query(Alert)
        .filter(Alert.item_id == it.id)
        .order_by(Alert.created_at.desc())
        .limit(20)
        .all()
    )
    return render(
        request,
        "item.html",
        s,
        item=it,
        rows=rows,
        verdict=v,
        history=json.dumps([[t.isoformat(), p] for t, p in hist]),
        alerts=alerts,
        msg=msg,
        active="dashboard",
    )


@router.get("/api/items/{item_id}/history")
def api_item_history(
    item_id: int, days: int = 90, s: Session = Depends(get_session, scope="function")
):
    it = s.get(Item, item_id)
    if not it:
        raise HTTPException(404)
    since = utcnow() - timedelta(days=days)
    out = {}
    for lk in it.links:
        pts = (
            s.query(PriceSnapshot)
            .filter(PriceSnapshot.item_vendor_id == lk.id, PriceSnapshot.captured_at >= since)
            .order_by(PriceSnapshot.captured_at)
            .all()
        )
        # A None price leaves a gap in the chart while the vendor is out of stock.
        if any(p.in_stock is not False for p in pts):
            out[lk.vendor.name] = [
                [p.captured_at.isoformat(), None if p.in_stock is False else p.price] for p in pts
            ]
    return out


@router.post("/items/{item_id}/edit")
def edit_item(
    item_id: int,
    name: str = Form(...),
    query: str = Form(...),
    category: str = Form(""),
    target_price: str = Form(""),
    enabled: str = Form("off"),
    notes: str = Form(""),
    s: Session = Depends(get_session, scope="function"),
):
    it = s.get(Item, item_id)
    if not it:
        raise HTTPException(404)
    it.name, it.query, it.notes = name.strip(), query.strip(), notes
    it.category = category.strip() or it.category
    it.target_price = float(target_price) if target_price.strip() else None
    it.enabled = enabled == "on"
    return RedirectResponse(f"/items/{item_id}", status_code=303)


@router.post("/items/{item_id}/toggle")
def toggle_item(
    item_id: int, next: str = Form("/"), s: Session = Depends(get_session, scope="function")
):
    """One-click 'interested' switch. Paused items are not scanned and never alert."""
    it = s.get(Item, item_id)
    if not it:
        raise HTTPException(404)
    it.enabled = not it.enabled
    return RedirectResponse(next or "/", status_code=303)


@router.post("/items/{item_id}/delete")
def delete_item(item_id: int, s: Session = Depends(get_session, scope="function")):
    it = s.get(Item, item_id)
    if it:
        s.delete(it)
    return RedirectResponse("/", status_code=303)


@router.post("/items/{item_id}/scan")
async def scan_item(item_id: int):
    """Queue a scan and return at once; results appear on the item page when it finishes."""
    scheduler.start_item_scan(item_id)
    return RedirectResponse(
        f"/items/{item_id}?msg=Rescan+started.+Refresh+in+a+minute+or+two+for+results.",
        status_code=303,
    )


@router.post("/items/{item_id}/pin/{vendor_id}")
def pin_link(
    item_id: int,
    vendor_id: int,
    product_url: str = Form(""),
    s: Session = Depends(get_session, scope="function"),
):
    lk = s.query(ItemVendor).filter_by(item_id=item_id, vendor_id=vendor_id).first()
    if lk is None:
        lk = ItemVendor(item_id=item_id, vendor_id=vendor_id)
        s.add(lk)
    url = product_url.strip()
    if url:
        lk.product_url, lk.pinned, lk.status, lk.last_error = url, True, LinkStatus.pending, None
    else:  # unpin → rediscover via search
        lk.pinned, lk.product_url, lk.status = False, None, LinkStatus.pending
    return RedirectResponse(f"/items/{item_id}", status_code=303)


# ---------------- Vendors ----------------
@router.get("/vendors", response_class=HTMLResponse)
def vendors_page(request: Request, s: Session = Depends(get_session, scope="function")):
    vendors = s.query(Vendor).order_by(Vendor.enabled.desc(), Vendor.name).all()
    return render(
        request,
        "vendors.html",
        s,
        vendors=vendors,
        strategies=[x.value for x in Strategy],
        active="vendors",
    )


def _vendor_from_form(v: Vendor, form: dict) -> None:
    v.name = form["name"].strip()
    v.slug = form.get("slug", v.slug or "").strip().lower().replace(
        " ", "-"
    ) or v.name.lower().replace(" ", "-")
    v.base_url = form["base_url"].strip().rstrip("/")
    v.search_url = form["search_url"].strip()
    v.strategy = Strategy(form.get("strategy", "auto"))
    v.render_js = form.get("render_js") == "on"
    v.enabled = form.get("enabled") == "on"
    v.trusted = form.get("trusted", "on") == "on"
    v.min_interval_sec = int(form.get("min_interval_sec") or 0)
    v.notes = form.get("notes", "")
    v.selectors = {
        k: form.get(f"sel_{k}", "").strip()
        for k in ("card", "title", "price", "link", "product_price")
        if form.get(f"sel_{k}", "").strip()
    }


@router.post("/vendors")
async def add_vendor(request: Request, s: Session = Depends(get_session, scope="function")):
    form = dict(await request.form())
    v = Vendor(slug="", name="", base_url="", search_url="")
    _vendor_from_form(v, form)
    if s.query(Vendor).filter_by(slug=v.slug).first():
        raise HTTPException(400, "slug already exists")
    s.add(v)
    return RedirectResponse("/vendors", status_code=303)


@router.post("/vendors/{vendor_id}/edit")
async def edit_vendor(
    vendor_id: int, request: Request, s: Session = Depends(get_session, scope="function")
):
    v = s.get(Vendor, vendor_id)
    if not v:
        raise HTTPException(404)
    _vendor_from_form(v, dict(await request.form()))
    return RedirectResponse("/vendors", status_code=303)


@router.post("/vendors/{vendor_id}/toggle")
def toggle_vendor(vendor_id: int, s: Session = Depends(get_session, scope="function")):
    v = s.get(Vendor, vendor_id)
    if v:
        v.enabled = not v.enabled
    return RedirectResponse("/vendors", status_code=303)


@router.post("/vendors/{vendor_id}/delete")
def delete_vendor(vendor_id: int, s: Session = Depends(get_session, scope="function")):
    v = s.get(Vendor, vendor_id)
    if v:
        s.delete(v)
    return RedirectResponse("/vendors", status_code=303)


@router.post("/api/vendors/{vendor_id}/test")
async def test_vendor(
    vendor_id: int,
    q: str = Form("samsung galaxy s24"),
    s: Session = Depends(get_session, scope="function"),
):
    """Run one live search and show what the extractor sees — for tuning selectors."""
    v = s.get(Vendor, vendor_id)
    if not v:
        raise HTTPException(404)
    async with Fetcher() as f:
        cands, used, err = await search_vendor(f, v, q)
    return JSONResponse(
        {
            "vendor": v.name,
            "query": q,
            "strategy_used": used,
            "error": err,
            "count": len(cands),
            "candidates": [
                {"title": c.title[:120], "price": c.price, "url": c.url, "in_stock": c.in_stock}
                for c in cands[:15]
            ],
        }
    )


# ---------------- Alerts & settings ----------------
@router.get("/alerts", response_class=HTMLResponse)
def alerts_page(request: Request, s: Session = Depends(get_session, scope="function")):
    alerts = s.query(Alert).order_by(Alert.created_at.desc()).limit(200).all()
    return render(request, "alerts.html", s, alerts=alerts, active="alerts")


@router.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request, s: Session = Depends(get_session, scope="function"), msg: str = ""
):
    return render(
        request,
        "settings.html",
        s,
        cfg=settings_store.get_all(s),
        scenarios=settings_store.SCENARIOS,
        msg=msg,
        active="settings",
    )


@router.post("/settings")
async def save_settings(request: Request, s: Session = Depends(get_session, scope="function")):
    form = {k: str(v) for k, v in (await request.form()).items()}
    for flag in [k for k, _, _ in settings_store.SCENARIOS] + [
        "back_in_stock_good_price_only",
        "notifications_paused",
    ]:
        form[flag] = "1" if form.get(flag) == "on" else "0"
    settings_store.set_many(s, form)
    try:
        scheduler.reschedule_scan(int(float(form.get("scan_interval_sec", "120"))))
    except Exception:  # noqa: BLE001
        pass
    return RedirectResponse("/settings?msg=Saved", status_code=303)


@router.post("/settings/test-notify")
async def test_notify(s: Session = Depends(get_session, scope="function")):
    a = await send_test_alert(s)
    msg = "Test notification sent ✓" if a.sent else f"Failed: {a.send_error}"
    return RedirectResponse(f"/settings?msg={msg}", status_code=303)


@router.post("/scan-now")
async def scan_now(s: Session = Depends(get_session, scope="function")):
    scheduler.state["last_scan_summary"] = await scan_and_alert(s)
    scheduler.state["last_scan"] = utcnow()
    return RedirectResponse("/", status_code=303)


@router.post("/market-now")
async def market_now(s: Session = Depends(get_session, scope="function")):
    await market.refresh_market(s)
    scheduler.state["last_market"] = utcnow()
    return RedirectResponse("/", status_code=303)
