from __future__ import annotations

from sqlalchemy.orm import Session

from pricewatch.models import Item, ItemVendor, LinkStatus, Strategy, Vendor
from pricewatch.scraping.vendors import SEED_VENDORS


def seed_defaults(s: Session) -> int:
    """Insert seed vendors that don't exist yet. Never overwrites user edits."""
    existing = {v.slug for v in s.query(Vendor.slug).all()}
    added = 0
    for d in SEED_VENDORS:
        if d["slug"] in existing:
            continue
        s.add(
            Vendor(
                slug=d["slug"],
                name=d["name"],
                base_url=d["base_url"],
                search_url=d["search_url"],
                strategy=Strategy(d.get("strategy", "auto")),
                render_js=d.get("render_js", True),
                selectors=d.get("selectors", {}),
                enabled=d.get("enabled", True),
                trusted=d.get("trusted", True),
                min_interval_sec=d.get("min_interval_sec", 0),
                notes=d.get("notes", ""),
            )
        )
        added += 1
    return added


# First item the owner asked to track. Pinned URLs were verified by hand on 2026-11-01;
# every other vendor is discovered by search on the first scan.
SEED_ITEMS: list[dict] = [
    {
        "name": "LG GN-H722HLHL refrigerator (506 L, top freezer, silver)",
        "query": "LG GN-H722HLHL",
        "category": "Home appliances",
        "pins": {
            "homzmart": "https://homzmart.com/p/lg-refrigerator-506-liter-smart-no-frost-silver-gn-h722hlhl--SHOPLA18",
            "btech": "https://btech.com/ar/p/lg-no-frost-refrigerator-inverter-506l-gn-h722hlhu",
            "ehabcenter": "https://ehabcenter.com/product/lg-refrigerator-inverter-linear-silver-stainless/",
            "cairosales": "https://cairosales.com/en/refrigerators/lg-top-freezer-506-liter-18-cubic-feet-digital-hygiene-fresh-filter-door-cooling-gn-h722hlhl.html",
        },
    },
]


def seed_items(s: Session) -> int:
    """Insert the starter item(s) once, only on a brand-new database."""
    if s.query(Item).count() > 0:
        return 0
    vendors = {v.slug: v for v in s.query(Vendor).all()}
    added = 0
    for d in SEED_ITEMS:
        it = Item(name=d["name"], query=d["query"], category=d.get("category", "Home electronics"))
        s.add(it)
        s.flush()
        for slug, url in d.get("pins", {}).items():
            if slug in vendors:
                s.add(
                    ItemVendor(
                        item_id=it.id,
                        vendor_id=vendors[slug].id,
                        product_url=url,
                        pinned=True,
                        status=LinkStatus.pending,
                    )
                )
        added += 1
    return added
