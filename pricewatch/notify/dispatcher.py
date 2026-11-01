"""Fan an Alert out to every configured channel; record success/failure on the row."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from pricewatch import settings_store
from pricewatch.models import Alert
from pricewatch.notify.ntfy import send_ntfy
from pricewatch.notify.telegram import send_telegram

log = logging.getLogger(__name__)


def channels_configured(s: Session) -> dict[str, bool]:
    cfg = settings_store.get_all(s)
    return {
        "ntfy": bool(cfg.get("ntfy_topic")),
        "telegram": bool(cfg.get("telegram_bot_token") and cfg.get("telegram_chat_ids")),
    }


async def dispatch(s: Session, alert: Alert) -> None:
    cfg = settings_store.get_all(s)
    errors: list[str] = []
    sent_any = False
    text = alert.message + (f"\n{alert.url}" if alert.url else "")

    if cfg.get("ntfy_topic"):
        try:
            await send_ntfy(
                cfg["ntfy_server"],
                cfg["ntfy_topic"],
                alert.title,
                alert.message,
                click_url=alert.url,
            )
            sent_any = True
        except Exception as e:  # noqa: BLE001
            errors.append(f"ntfy: {e}")
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

    if not cfg.get("ntfy_topic") and not cfg.get("telegram_bot_token"):
        errors.append("no notification channel configured (Settings → ntfy topic)")

    alert.sent = sent_any
    alert.send_error = "; ".join(errors) or None
    if errors:
        log.warning("alert %s delivery issues: %s", alert.id, alert.send_error)
