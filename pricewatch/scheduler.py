from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from pricewatch import settings_store
from pricewatch.config import settings
from pricewatch.db import session_scope
from pricewatch.market.service import refresh_market
from pricewatch.service import scan_and_alert

log = logging.getLogger(__name__)
_scan_lock = asyncio.Lock()
scheduler = AsyncIOScheduler(timezone="Africa/Cairo")
state: dict = {"last_scan": None, "last_scan_summary": None, "last_market": None, "scanning": False}


async def scan_job() -> None:
    if _scan_lock.locked():
        log.info("previous scan still running; skipping this tick")
        return
    async with _scan_lock:
        state["scanning"] = True
        try:
            with session_scope() as s:
                state["last_scan_summary"] = await scan_and_alert(s)
        except Exception:  # noqa: BLE001
            log.exception("scan job failed")
        finally:
            from pricewatch.models import utcnow

            state["last_scan"] = utcnow()
            state["scanning"] = False


async def market_job() -> None:
    try:
        with session_scope() as s:
            await refresh_market(s)
        from pricewatch.models import utcnow

        state["last_market"] = utcnow()
    except Exception:  # noqa: BLE001
        log.exception("market job failed")


def start() -> None:
    with session_scope() as s:
        interval = int(settings_store.get_float(s, "scan_interval_sec", settings.scan_interval_sec))
    scheduler.add_job(
        scan_job,
        IntervalTrigger(seconds=max(30, interval)),
        id="scan",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        market_job,
        IntervalTrigger(seconds=settings.market_interval_sec),
        id="market",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    # run both once at startup so the dashboard isn't empty
    asyncio.get_event_loop().create_task(market_job())
    asyncio.get_event_loop().create_task(scan_job())
    log.info(
        "scheduler started: scan every %ss, market every %ss",
        interval,
        settings.market_interval_sec,
    )


def reschedule_scan(interval_sec: int) -> None:
    if scheduler.running:
        scheduler.reschedule_job("scan", trigger=IntervalTrigger(seconds=max(30, interval_sec)))


def stop() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
