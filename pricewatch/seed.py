from __future__ import annotations

from sqlalchemy.orm import Session

from pricewatch.models import Strategy, Vendor
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
