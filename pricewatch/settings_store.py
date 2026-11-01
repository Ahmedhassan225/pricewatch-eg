"""User-editable preferences stored in the DB, falling back to env settings."""

from __future__ import annotations

from sqlalchemy.orm import Session

from pricewatch.config import settings
from pricewatch.models import Setting

DEFAULTS: dict[str, str] = {
    "ntfy_topic": settings.ntfy_topic,
    "ntfy_server": settings.ntfy_server,
    "telegram_bot_token": settings.telegram_bot_token,
    "telegram_chat_ids": settings.telegram_chat_ids,
    "flash_drop_pct": str(settings.flash_drop_pct),
    "alert_cooldown_hours": str(settings.alert_cooldown_hours),
    "match_threshold": str(settings.match_threshold),
    "scan_interval_sec": str(settings.scan_interval_sec),
    "notify_all_time_low": "1",
    "notify_target_hit": "1",
}


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
