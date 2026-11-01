"""Clicks must be saved before the browser is sent back to the page, and a running
scan must not hold the database's write lock while it waits on vendors."""

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from pricewatch import scheduler
from pricewatch.db import session_scope
from pricewatch.models import Item, ItemVendor, LinkStatus, Vendor
from pricewatch.scraping import engine
from pricewatch.scraping.engine import LinkResult, run_scan
from pricewatch.web.routes import router


def _client_reading_at_response_start(read, seen: list) -> TestClient:
    app = FastAPI()
    app.include_router(router)

    async def spy_app(scope, receive, send):
        async def spy_send(message):
            if message["type"] == "http.response.start":
                seen.append(read())
            await send(message)

        await app(scope, receive, spy_send)

    return TestClient(spy_app, follow_redirects=False)


def _item_enabled(item_id: int) -> bool:
    with session_scope() as s:
        return s.get(Item, item_id).enabled


def test_toggle_is_saved_before_the_redirect(db_session):
    item_id = db_session.query(Item).first().id
    was = db_session.query(Item).first().enabled
    db_session.commit()
    seen: list[bool] = []
    client = _client_reading_at_response_start(lambda: _item_enabled(item_id), seen)
    r = client.post(f"/items/{item_id}/toggle", data={"next": "/"})
    assert r.status_code == 303
    assert seen == [not was]


def test_pin_is_saved_before_the_redirect(db_session):
    item_id = db_session.query(Item).first().id
    vendor_id = db_session.query(Vendor).filter_by(slug="2b").one().id
    db_session.commit()

    def read():
        with session_scope() as s:
            lk = s.query(ItemVendor).filter_by(item_id=item_id, vendor_id=vendor_id).first()
            return lk.product_url if lk else None

    seen: list = []
    client = _client_reading_at_response_start(read, seen)
    url = "https://2b.com.eg/en/some-product.html"
    r = client.post(f"/items/{item_id}/pin/{vendor_id}", data={"product_url": url})
    assert r.status_code == 303
    assert seen == [url]


def test_rescan_returns_without_waiting_for_the_scan(db_session, monkeypatch):
    item_id = db_session.query(Item).first().id
    db_session.commit()
    events: list[str] = []

    async def slow_job(i):
        events.append("started")
        await asyncio.sleep(3600)
        events.append("finished")

    monkeypatch.setattr(scheduler, "scan_item_job", slow_job)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app, follow_redirects=False) as client:
        r = client.post(f"/items/{item_id}/scan")
        assert r.status_code == 303 and "msg=" in r.headers["location"]
        assert "finished" not in events


def _only_vendor(s, slug: str) -> Vendor:
    target = s.query(Vendor).filter_by(slug=slug).one()
    for v in s.query(Vendor).all():
        v.enabled = v.id == target.id
    s.commit()
    return target


def test_scan_does_not_block_writes_while_fetching(db_session, monkeypatch):
    item = db_session.query(Item).first()
    _only_vendor(db_session, "2b")
    item_id = item.id

    async def fake_check_link(fetcher, vendor, it, link, threshold):
        # a click arriving mid-scan: fails with "database is locked" if the scan holds the lock
        with session_scope() as other:
            other.get(Item, item_id).notes = "written during scan"
        return LinkResult(it.id, vendor.id, LinkStatus.not_found)

    monkeypatch.setattr(engine, "check_link", fake_check_link)
    asyncio.run(run_scan(db_session, item_ids=[item_id]))
    db_session.commit()
    with session_scope() as s:
        assert s.get(Item, item_id).notes == "written during scan"


def test_pin_made_during_a_scan_survives_the_scan_result(db_session, monkeypatch):
    item = db_session.query(Item).first()
    vendor = _only_vendor(db_session, "2b")
    item_id, vendor_id = item.id, vendor.id
    url = "https://2b.com.eg/en/pinned.html"

    async def fake_check_link(fetcher, v, it, link, threshold):
        with session_scope() as other:
            lk = other.query(ItemVendor).filter_by(item_id=item_id, vendor_id=vendor_id).one()
            lk.product_url, lk.pinned, lk.status = url, True, LinkStatus.pending
        return LinkResult(it.id, v.id, LinkStatus.not_found)

    monkeypatch.setattr(engine, "check_link", fake_check_link)
    asyncio.run(run_scan(db_session, item_ids=[item_id]))
    db_session.commit()
    with session_scope() as s:
        lk = s.query(ItemVendor).filter_by(item_id=item_id, vendor_id=vendor_id).one()
        assert (lk.product_url, lk.pinned, lk.status) == (url, True, LinkStatus.pending)
