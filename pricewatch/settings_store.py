"""User-editable preferences stored in the DB, falling back to env settings."""

from __future__ import annotations

from sqlalchemy.orm import Session

from pricewatch.config import settings
from pricewatch.models import Setting

DEFAULTS: dict[str, str] = {
    "ntfy_topics": settings.ntfy_topics,
    "ntfy_server": settings.ntfy_server,
    "telegram_bot_token": settings.telegram_bot_token,
    "telegram_chat_ids": settings.telegram_chat_ids,
    "flash_drop_pct": str(settings.flash_drop_pct),
    "alert_cooldown_hours": str(settings.alert_cooldown_hours),
    "match_threshold": str(settings.match_threshold),
    "scan_interval_sec": str(settings.scan_interval_sec),
    "notifications_paused": "0",  # global do-not-disturb
    # notification scenarios — each can be switched off in Settings
    "notify_flash_sale": "1",
    "notify_target_hit": "1",
    "notify_all_time_low": "1",
    "notify_back_in_stock": "1",
    "back_in_stock_good_price_only": "0",
    "notify_out_of_stock": "0",
    "notify_unavailable": "1",
}

SCENARIOS: list[tuple[str, str, str]] = [
    ("notify_flash_sale", "⚡ Flash sale", "price drops by the threshold vs. its 7-day median"),
    ("notify_target_hit", "🎯 Target hit", "price is at or below the item's target price"),
    ("notify_all_time_low", "📉 All-time low", "lowest price ever recorded for this vendor"),
    ("notify_back_in_stock", "✅ Back in stock", "an item that was unavailable is available again"),
    (
        "notify_out_of_stock",
        "⛔ Out of stock at a vendor",
        "one vendor stops listing it (can be noisy)",
    ),
    ("notify_unavailable", "🚫 Unavailable everywhere", "no enabled vendor has it any more"),
]


def ntfy_topics(cfg: dict[str, str]) -> list[str]:
    raw = cfg.get("ntfy_topics", "")
    return [t.strip() for t in raw.replace("\n", ",").split(",") if t.strip()]


def get_all(s: Session) -> dict[str, str]:
    out = dict(DEFAULTS)
    for row in s.query(Setting).all():
        out[row.key] = row.value
    return out


def get(s: Session, key: str) -> str:
    row = s.get(Setting, key)
    return row.value if row is not None else DEFAULTS.get(key, "")


def get_float(s: Session, key: str, default: float) -> float:
    try:
        return float(get(s, key))
    except (TypeError, ValueError):
        return default


def set_many(s: Session, values: dict[str, str]) -> None:
    for k, v in values.items():
        if k not in DEFAULTS:
            continue
        row = s.get(Setting, k)
        if row is None:
            s.add(Setting(key=k, value=v))
        else:
            row.value = v
