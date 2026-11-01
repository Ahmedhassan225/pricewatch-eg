"""HTTP Basic Auth as a pure ASGI middleware. Enabled when PW_AUTH_PASSWORD is set."""

from __future__ import annotations

import base64
import secrets

from pricewatch.config import settings


def _credentials_ok(header: str | None) -> bool:
    if not header or not header.lower().startswith("basic "):
        return False
    try:
        raw = base64.b64decode(header.split(" ", 1)[1].strip()).decode("utf-8")
    except Exception:  # noqa: BLE001
        return False
    user, _, password = raw.partition(":")
    return secrets.compare_digest(user, settings.auth_user) and secrets.compare_digest(
        password, settings.auth_password
    )


def auth_enabled() -> bool:
    return bool(settings.auth_password)


class BasicAuthMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not auth_enabled():
            await self.app(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        if _credentials_ok(headers.get("authorization")):
            await self.app(scope, receive, send)
            return
        body = b"Authentication required"
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"www-authenticate", b'Basic realm="PriceWatch EG", charset="UTF-8"'),
                    (b"content-type", b"text/plain; charset=utf-8"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
