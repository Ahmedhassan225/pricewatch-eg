from __future__ import annotations

import httpx


async def send_telegram(bot_token: str, chat_ids: list[str], text: str) -> None:
    if not bot_token or not chat_ids:
        raise ValueError("telegram not configured")
    async with httpx.AsyncClient(timeout=15) as c:
        for cid in chat_ids:
            r = await c.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": cid.strip(), "text": text, "disable_web_page_preview": True},
            )
            r.raise_for_status()
