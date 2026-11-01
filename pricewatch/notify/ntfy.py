"""ntfy.sh — free push to iPhone (App Store 'ntfy') and Android (Play/F-Droid 'ntfy').
Both phones subscribe to the same topic; no accounts, no cost."""

from __future__ import annotations

import httpx


async def send_ntfy(
    server: str,
    topic: str,
    title: str,
    message: str,
    *,
    click_url: str | None = None,
    priority: int = 4,
    tags: str = "moneybag,fire",
) -> None:
    if not topic:
        raise ValueError("ntfy topic is empty")
    headers = {
        "Title": title.encode("utf-8", "ignore").decode("latin-1", "ignore") or "PriceWatch",
        "Priority": str(priority),
        "Tags": tags,
    }
    if click_url:
        headers["Click"] = click_url
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{server.rstrip('/')}/{topic}", content=message.encode("utf-8"), headers=headers
        )
        r.raise_for_status()
