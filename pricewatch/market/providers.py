"""Free, key-less market data: USD→EGP and gold. Each provider returns a float or raises."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)
TROY_OZ_GRAMS = 31.1034768


@dataclass
class Quote:
    kind: str
    value: float
    source: str


async def fetch_usd_egp(client: httpx.AsyncClient) -> Quote:
    # Primary: open.er-api.com (no key, daily). Fallback: exchangerate-api open endpoint mirror.
    for url, picker, source in (
        ("https://open.er-api.com/v6/latest/USD", lambda d: d["rates"]["EGP"], "open.er-api.com"),
        (
            "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json",
            lambda d: d["usd"]["egp"],
            "fawazahmed0/currency-api",
        ),
    ):
        try:
            r = await client.get(url, timeout=20)
            r.raise_for_status()
            return Quote("usd_egp", float(picker(r.json())), source)
        except Exception as e:  # noqa: BLE001
            log.warning("fx provider %s failed: %s", source, e)
    raise RuntimeError("all USD/EGP providers failed")


async def fetch_gold_usd_oz(client: httpx.AsyncClient) -> Quote:
    for url, picker, source in (
        ("https://api.gold-api.com/price/XAU", lambda d: d["price"], "gold-api.com"),
        (
            "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/xau.json",
            lambda d: d["xau"]["usd"],
            "fawazahmed0/currency-api",
        ),
    ):
        try:
            r = await client.get(url, timeout=20)
            r.raise_for_status()
            return Quote("gold_usd_oz", float(picker(r.json())), source)
        except Exception as e:  # noqa: BLE001
            log.warning("gold provider %s failed: %s", source, e)
    raise RuntimeError("all gold providers failed")


def gold_21k_gram_egp(gold_usd_oz: float, usd_egp: float) -> float:
    """Egyptian shops quote 21-karat per gram. 21/24 purity of a 24K troy ounce."""
    return round(gold_usd_oz * usd_egp * (21 / 24) / TROY_OZ_GRAMS, 2)


async def fetch_all() -> list[Quote]:
    async with httpx.AsyncClient(headers={"User-Agent": "pricewatch-eg/0.1"}) as client:
        quotes: list[Quote] = []
        fx = gold = None
        try:
            fx = await fetch_usd_egp(client)
            quotes.append(fx)
        except Exception as e:  # noqa: BLE001
            log.error("fx failed: %s", e)
        try:
            gold = await fetch_gold_usd_oz(client)
            quotes.append(gold)
        except Exception as e:  # noqa: BLE001
            log.error("gold failed: %s", e)
        if fx and gold:
            quotes.append(
                Quote("gold_egp_21k_g", gold_21k_gram_egp(gold.value, fx.value), "derived")
            )
        return quotes
