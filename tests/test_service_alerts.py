"""End-to-end alert logic with the scraper replaced by canned results."""

import asyncio

import pytest

from pricewatch import service, settings_store
from pricewatch.models import (
    Alert,
    AlertKind,
    Item,
    ItemVendor,
    LinkStatus,
    PriceSnapshot,
    Vendor,
    utcnow,
)
from pricewatch.scraping.engine import LinkResult, PrevState


def _fake_scan(outcomes):
    async def run_scan(s, item_ids=None, vendor_ids=None):
        out = []
        for link, res in outcomes:
            prev = PrevState(link.status, link.in_stock, link.last_price)
            from pricewatch.scraping.engine import apply_result

            snap = apply_result(s, link, res)
            out.append((link, res, snap, prev))
        s.flush()
        return out

    return run_scan


@pytest.fixture
def item_with_link(db_session):
    s = db_session
    v = s.query(Vendor).filter_by(slug="btech").first()
    it = Item(name="Test TV", query="Test TV", target_price=None)
    s.add(it)
    s.flush()
    lk = ItemVendor(
        item_id=it.id,
        vendor_id=v.id,
        status=LinkStatus.found,
        in_stock=True,
        last_price=10000,
        product_url="https://btech.com/p/x",
    )
    s.add(lk)
    s.flush()
    for _i in range(6):
        s.add(PriceSnapshot(item_vendor_id=lk.id, price=10000, captured_at=utcnow()))
    s.flush()
    return it, lk


def _run(monkeypatch, s, outcomes, cfg=None):
    settings_store.set_many(s, {"ntfy_topics": "", "telegram_bot_token": "", **(cfg or {})})
    monkeypatch.setattr(service, "run_scan", _fake_scan(outcomes))
    return asyncio.run(service.scan_and_alert(s))


def test_out_of_stock_then_unavailable_everywhere(db_session, monkeypatch, item_with_link):
    it, lk = item_with_link
    res = LinkResult(
        it.id, lk.vendor_id, LinkStatus.found, price=10000, url=lk.product_url, in_stock=False
    )
    summary = _run(monkeypatch, db_session, [(lk, res)], {"notify_out_of_stock": "1"})
    kinds = {a.kind for a in db_session.query(Alert).all()}
    assert summary["alerts"] == 2 and kinds == {AlertKind.out_of_stock, AlertKind.unavailable}


def test_out_of_stock_scenario_disabled(db_session, monkeypatch, item_with_link):
    it, lk = item_with_link
    res = LinkResult(
        it.id, lk.vendor_id, LinkStatus.found, price=10000, url=lk.product_url, in_stock=False
    )
    _run(
        monkeypatch,
        db_session,
        [(lk, res)],
        {"notify_out_of_stock": "0", "notify_unavailable": "0"},
    )
    assert db_session.query(Alert).count() == 0


def test_back_in_stock_with_flash_price(db_session, monkeypatch, item_with_link):
    it, lk = item_with_link
    lk.in_stock = False
    db_session.flush()
    res = LinkResult(
        it.id, lk.vendor_id, LinkStatus.found, price=8500, url=lk.product_url, in_stock=True
    )
    summary = _run(monkeypatch, db_session, [(lk, res)])
    kinds = {a.kind for a in db_session.query(Alert).all()}
    assert (
        AlertKind.back_in_stock in kinds
        and AlertKind.flash_sale in kinds
        and summary["alerts"] == 2
    )


def test_no_price_alert_for_out_of_stock_listing(db_session, monkeypatch, item_with_link):
    it, lk = item_with_link
    res = LinkResult(
        it.id, lk.vendor_id, LinkStatus.found, price=5000, url=lk.product_url, in_stock=False
    )
    _run(
        monkeypatch,
        db_session,
        [(lk, res)],
        {"notify_out_of_stock": "0", "notify_unavailable": "0"},
    )
    assert db_session.query(Alert).filter(Alert.kind == AlertKind.flash_sale).count() == 0


def test_paused_notifications_are_recorded_not_sent(db_session, monkeypatch, item_with_link):
    it, lk = item_with_link
    res = LinkResult(
        it.id, lk.vendor_id, LinkStatus.found, price=8000, url=lk.product_url, in_stock=True
    )
    _run(monkeypatch, db_session, [(lk, res)], {"notifications_paused": "1"})
    a = db_session.query(Alert).one()
    assert a.sent is False and "paused" in a.send_error


def _add_out_of_stock_snapshot(s, link, price):
    s.add(PriceSnapshot(item_vendor_id=link.id, price=price, in_stock=False, captured_at=utcnow()))
    s.flush()


def _out_of_stock_link(s, item, slug, price):
    v = s.query(Vendor).filter_by(slug=slug).first()
    lk = ItemVendor(
        item_id=item.id, vendor_id=v.id, status=LinkStatus.found, in_stock=False, last_price=price
    )
    s.add(lk)
    s.flush()
    _add_out_of_stock_snapshot(s, lk, price)
    return lk


def test_item_history_ignores_out_of_stock_prices(db_session, item_with_link):
    it, lk = item_with_link
    _add_out_of_stock_snapshot(db_session, lk, 5000)
    assert {p for _, p in service.item_history(db_session, it)} == {10000}


def test_verdict_lows_ignore_out_of_stock_vendor(db_session, item_with_link):
    it, _ = item_with_link
    _out_of_stock_link(db_session, it, "noon-eg", 5000)
    v = service.verdict_for(db_session, it)
    assert v.best_price == 10000 and v.min_30d == 10000 and v.all_time_low == 10000


def test_link_history_ignores_out_of_stock_prices(db_session, item_with_link):
    _, lk = item_with_link
    _add_out_of_stock_snapshot(db_session, lk, 5000)
    assert {p for _, p in service.link_history(db_session, lk.id)} == {10000}


def test_price_chart_leaves_gaps_while_out_of_stock(db_session, item_with_link):
    from pricewatch.web.routes import api_item_history

    it, lk = item_with_link
    _add_out_of_stock_snapshot(db_session, lk, 5000)
    only_out = _out_of_stock_link(db_session, it, "noon-eg", 4000)

    data = api_item_history(it.id, 90, db_session)

    assert only_out.vendor.name not in data  # never buyable in this range, so no line or legend
    prices = [p for _, p in data[lk.vendor.name]]
    assert prices[-1] is None and set(prices[:-1]) == {10000}


def test_not_interested_item_is_skipped(db_session, item_with_link):
    it, lk = item_with_link
    it.enabled = False
    db_session.flush()
    from pricewatch.scraping.engine import run_scan

    assert asyncio.run(run_scan(db_session, item_ids=[it.id])) == []
