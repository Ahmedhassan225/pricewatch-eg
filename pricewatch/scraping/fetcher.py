"""HTTP fetching with a plain-HTTP fast path and a Playwright fallback.

Plain httpx is used when the vendor allows it (render_js=False). When the vendor is
client-rendered or the plain response looks like a bot challenge, we render with a
persistent Chromium profile so cookies/challenge clearances survive between cycles.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass

import httpx

from pricewatch.config import settings

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-EG,en;q=0.9,ar-EG;q=0.8,ar;q=0.7",
    "Cache-Control": "no-cache",
}
_CHALLENGE_MARKERS = (
    "just a moment",
    "attention required",
    "cf-chl",
    "checking your browser",
    "vercel security checkpoint",
    "captcha",
    "api-services-support@amazon.com",
)


@dataclass
class FetchResult:
    url: str
    status: int
    text: str
    used_browser: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and 200 <= self.status < 400 and bool(self.text)

    @property
    def blocked(self) -> bool:
        low = self.text[:5000].lower()
        return self.status in (403, 429, 503) or any(m in low for m in _CHALLENGE_MARKERS)


class Fetcher:
    def __init__(self, concurrency: int | None = None) -> None:
        self._sem = asyncio.Semaphore(concurrency or settings.fetch_concurrency)
        self._client: httpx.AsyncClient | None = None
        self._pw = None
        self._browser_ctx = None
        self._browser_lock = asyncio.Lock()

    async def __aenter__(self) -> Fetcher:
        self._client = httpx.AsyncClient(
            headers=HEADERS,
            timeout=settings.request_timeout_sec,
            follow_redirects=True,
            http2=False,
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()
        await self._close_browser()

    # ---- plain HTTP ----
    async def fetch_http(self, url: str) -> FetchResult:
        assert self._client is not None
        async with self._sem:
            await asyncio.sleep(random.uniform(0.2, 1.2))  # jitter: be polite
            try:
                r = await self._client.get(url)
                return FetchResult(url=str(r.url), status=r.status_code, text=r.text)
            except httpx.HTTPError as e:
                return FetchResult(url=url, status=0, text="", error=f"{type(e).__name__}: {e}")

    # ---- browser ----
    async def _ensure_browser(self):
        async with self._browser_lock:
            if self._browser_ctx is not None:
                return self._browser_ctx
            try:
                from playwright.async_api import async_playwright
            except ImportError as e:  # pragma: no cover
                raise RuntimeError("playwright not installed: pip install playwright") from e
            self._pw = await async_playwright().start()
            settings.playwright_profile_dir.mkdir(parents=True, exist_ok=True)
            self._browser_ctx = await self._pw.chromium.launch_persistent_context(
                str(settings.playwright_profile_dir),
                headless=settings.playwright_headless,
                user_agent=UA,
                locale="en-EG",
                timezone_id="Africa/Cairo",
                viewport={"width": 1366, "height": 900},
                args=["--disable-blink-features=AutomationControlled"],
                executable_path=settings.chromium_path or None,
            )
            return self._browser_ctx

    async def _close_browser(self) -> None:
        if self._browser_ctx is not None:
            try:
                await self._browser_ctx.close()
            finally:
                self._browser_ctx = None
        if self._pw is not None:
            try:
                await self._pw.stop()
            finally:
                self._pw = None

    async def fetch_browser(self, url: str, wait_selector: str | None = None) -> FetchResult:
        async with self._sem:
            try:
                ctx = await self._ensure_browser()
                page = await ctx.new_page()
                try:
                    resp = await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=settings.request_timeout_sec * 1000,
                    )
                    # give client-side apps a moment to paint prices
                    if wait_selector:
                        try:
                            await page.wait_for_selector(
                                wait_selector.split(",")[0].strip(), timeout=8000
                            )
                        except Exception:
                            pass
                    await page.wait_for_timeout(1500)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=6000)
                    except Exception:
                        pass
                    html = await page.content()
                    status = resp.status if resp else 200
                    return FetchResult(url=page.url, status=status, text=html, used_browser=True)
                finally:
                    await page.close()
            except Exception as e:  # noqa: BLE001 - we want to report any browser failure
                log.warning("browser fetch failed for %s: %s", url, e)
                return FetchResult(
                    url=url, status=0, text="", used_browser=True, error=f"{type(e).__name__}: {e}"
                )

    # ---- policy ----
    async def fetch(
        self, url: str, render_js: bool, wait_selector: str | None = None
    ) -> FetchResult:
        if not render_js:
            r = await self.fetch_http(url)
            if r.ok and not r.blocked:
                return r
            log.info("plain fetch blocked/failed for %s (status %s); trying browser", url, r.status)
        return await self.fetch_browser(url, wait_selector)
