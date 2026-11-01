"""Fan an Alert out to every configured channel; record success/failure on the row."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from pricewatch import settings_store
from pricewatch.models import Alert, AlertKind
from pricewatch.notify.ntfy import send_ntfy
from pricewatch.notify.telegram import send_telegram

TAGS = {
    AlertKind.flash_sale: ("fire,moneybag", 4),
    AlertKind.target_hit: ("dart,moneybag", 4),
    AlertKind.all_time_low: ("chart_with_downwards_trend", 4),
    AlertKind.back_in_stock: ("white_check_mark,package", 4),
    AlertKind.out_of_stock: ("no_entry", 3),
    AlertKind.unavailable: ("x", 3),
    AlertKind.test: ("bell", 3),
}
log = logging.getLogger(__name__)


def channels_configured(s: Session) -> dict[str, bool]:
    cfg = settings_store.get_all(s)
    return {
        "ntfy": bool(settings_store.ntfy_topics(cfg)),
        "telegram": bool(cfg.get("telegram_bot_token") and cfg.get("telegram_chat_ids")),
    }


async def dispatch(s: Session, alert: Alert) -> None:
    cfg = settings_store.get_all(s)
    errors: list[str] = []
    sent_any = False
    text = alert.message + (f"\n{alert.url}" if alert.url else "")

    topics = settings_store.ntfy_topics(cfg)
    tags, priority = TAGS.get(alert.kind, ("bell", 3))
    for topic in topics:
        # a topic may be a bare name (uses the configured server) or a full URL
        server, _, name = topic.rpartition("/") if "://" in topic else ("", "", topic)
        try:
            await send_ntfy(
                server or cfg["ntfy_server"],
                name,
                alert.title,
                alert.message,
                click_url=alert.url,
                priority=priority,
                tags=tags,
            )
            sent_any = True
        except Exception as e:  # noqa: BLE001
            errors.append(f"ntfy {name}: {e}")
    if cfg.get("telegram_bot_token") and cfg.get("telegram_chat_ids"):
        try:
            await send_telegram(
                cfg["telegram_bot_token"],
                cfg["telegram_chat_ids"].split(","),
                f"{alert.title}\n{text}",
            )
            sent_any = True
        except Exception as e:  # noqa: BLE001
            errors.append(f"telegram: {e}")

    if not topics and not cfg.get("telegram_bot_token"):
        errors.append("no notification channel configured (Settings → ntfy topics)")

    alert.sent = sent_any
    alert.send_error = "; ".join(errors) or None
    if errors:
        log.warning("alert %s delivery issues: %s", alert.id, alert.send_error)
