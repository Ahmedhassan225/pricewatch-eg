# PriceWatch EG — Plan

## Goal
Track items (mainly home electronics) across the top trusted Egyptian online vendors,
store price history, detect flash sales, push free phone notifications (iPhone + Android),
and show a dashboard that answers "should I buy now?" with USD/EGP and gold context.

## Decisions
| Topic | Decision | Why |
|---|---|---|
| Runtime | Python 3.11+, FastAPI + Uvicorn, SQLite | single process on a laptop, zero infra |
| Scheduling | APScheduler in-process, scan every 2 min, market data every 15 min | asked for 2-min cadence; FX/gold move slowly |
| Scraping | httpx first, Playwright (Chromium) fallback when `render_js` or blocked | Noon/B.TECH/Raya/Sigma are client-rendered; Jumia/2B/Extra use Cloudflare |
| Extraction | strategy cascade: Shopify JSON → JSON-LD → vendor CSS selectors → heuristic | resilient to redesigns; selectors are editable in the UI |
| Matching | rapidfuzz token-set ratio vs. item query, threshold 70; an exact model code (e.g. GN-H722HLHL) in the title scores 95 | picks the right result even when the store title is Arabic |
| Not found | per item×vendor status `not_found` shown in UI | explicit requirement |
| Pin URL | user can paste the exact product URL per vendor | most reliable path once the item is located |
| Notifications | ntfy.sh topic (free apps on iOS & Android, no account); Telegram bot optional | zero cost, works for owner + friend by subscribing to the same topic |
| FX | open.er-api.com USD→EGP (free, no key) | verified working |
| Gold | gold-api.com XAU/USD (free, no key) → 21K gram EGP = XAU×USD/EGP×(21/24)/31.1035 | verified working; Egyptians track 21K/gram |
| Flash sale | drop ≥10% vs 7-day median, or ≤ target price, or new all-time low; 6h cooldown per vendor link | avoids noisy repeated alerts |
| Availability | per-link transitions: available→(out of stock / listing gone) = out_of_stock; unavailable→available (seen before) = back_in_stock, optional "good price only"; item with no available vendor = unavailable. Fetch errors never count. | owner asked to know when it goes unavailable or returns at a good price |
| Scenario toggles | `notify_<kind>` settings + global `notifications_paused`; out_of_stock off by default (noisy with 14 vendors) | owner asked for per-scenario config |
| Subscribers | `ntfy_topics` list — one topic per person or one shared; bare name or full URL per line | owner asked for multiple subscribers on ntfy |
| Interested toggle | `Item.enabled` surfaced as a one-click ★/☆ button; disabled items are not scanned and never alert | owner asked to toggle interest per item |
| Auth | HTTP Basic Auth middleware, on when `PW_AUTH_PASSWORD` is set; credentials live in `.env` only | dashboard will be exposed through ngrok |
| Mobile | responsive tables become stacked cards < 640px; 16px inputs; wrap nav | owner opens it from a phone browser |
| Buy score | 0–100 from position in 30-day range, trend slope, vendor spread, FX momentum | explainable reasons shown on dashboard |
| UI | Jinja2 + Chart.js, Tailwind via CDN | no build step |

## Top-10 trusted Egyptian vendors (seeded; editable)
Amazon Egypt, Noon Egypt, Jumia Egypt, B.TECH, 2B Egypt, Raya Shop, Carrefour Egypt,
Tradeline (Apple premium reseller), Dubai Phone, El Araby Group.
Added 2026-11-01 at the owner's request: Homzmart (Next.js, browser), Sharaf DG Egypt (Cloudflare, browser),
Shaheen and El Ksass (WooCommerce Store API — JSON, no browser).
Extras available to enable: eXtra Egypt, Sigma Computer.

## Milestones
- [x] M0 Scaffold, CLAUDE.md, plan
- [x] M1 Models + DB + seed vendors
- [x] M2 Price parser + extractors + matcher (unit tested with fixtures)
- [x] M3 Fetcher (httpx + Playwright) + scan engine + scheduler
- [x] M4 Market data (USD/EGP, gold) + history
- [x] M5 Flash-sale detection + buy-now scoring (unit tested)
- [x] M6 Notifications (ntfy, Telegram) + test button
- [x] M7 Dashboard: items, item detail, vendors CRUD, settings, alerts, charts
- [x] M9 Availability alerts, scenario toggles, multi-subscriber ntfy, interested toggle, mobile UI, Basic Auth (2026-11-01)
- [x] M8 CLI (`pricewatch`, `pricewatch scan`, `pricewatch market`), README, run scripts

## Verified (2026-11-01)
- 35 unit tests green; ruff clean.
- Live USD/EGP (open.er-api.com) and gold (gold-api.com) fetched successfully.
- Real scan: Tradeline (Shopify path) found “iPhone 15 128GB” at 63,300 EGP, match 100%.
- Playwright path renders pages (Tradeline search, 2.6 MB). Amazon/Jumia block the cloud IP (503/403); expected to pass from a home IP.

## Verified from the home connection (Windows laptop, 2026-11-01)
- 55 tests green on Windows; test fixtures are now read as UTF-8 (they failed under the cp1252 default).
- Market data, ntfy push to phone, Task Scheduler log-on task and login through ngrok all confirmed.
- GN-H722HLHL scan: Homzmart 62,999 (pinned), Amazon 66,000 (search; no buy box), B.TECH 65,509 out of stock (pinned, because its search hides out-of-stock items).
- Selectors/search URLs fixed: Amazon (title selector returned only "LG", which matched a different fridge), B.TECH, Raya Shop, Dubai Phone.
- Matcher: if the query has a model code and the title lacks it, the score is capped at 60.
- Genuinely not listed: 2B, Raya Shop, Dubai Phone, El Araby, Shaheen, Tradeline, El Ksass (the last with a small search gap on the LG brand).

- Added at the owner's request: EHAB Center (pinned, 56,990 out of stock; robots.txt disallows its site search, so new items need a pinned URL) and Cairo Sales (enabled, checked every 30 min, no price: Cloudflare blocks search with a 403 and intermittently blocks product pages. A pinned read gave 56,990 in stock from hidden page data while the owner's browser showed no price, so the pin was removed until a visible-price selector exists). Also Azmy (server-rendered search, no browser).

## Known limits / follow-ups
- Loose `[class*='price']` product selectors can catch add-on prices (Sharaf read a +7,860 warranty as the fridge price). Raya Shop, El Araby and the disabled eXtra and Sigma still use them.
- A full scan of 4 items takes 3–5 minutes, so the 2-minute cadence skips ticks while one runs.
- Pinned reads trust JSON-LD/meta prices first, so a store that hides the price on screen but leaves it in page data reads as a false price. Add a visible-price check if this recurs.
- The `captcha` challenge marker in `fetcher.py` also matches pages that merely load a reCAPTCHA script (seen on EHAB and the Cairo Sales homepage), so a browser search on such a site would report "blocked" wrongly. Pinned pages are unaffected.
- Seed edits don't reach an existing DB (`seed_defaults` skips existing slugs): change live rows through the Vendors page as well.
- A discovered (unpinned) link that keeps refreshing is never re-scored against the query, so a wrong match persists until the link is cleared (`engine.py` `check_link`). `guess_in_stock` can also misreport stock on Amazon product pages.
- Noon and Carrefour fail with `ERR_HTTP2_PROTOCOL_ERROR` in Playwright; cause not established. Jumia and Sharaf DG show Cloudflare interactive challenges.
- `fetcher.py` still claims Chrome/130 while the bundled Chromium is 156.
- Future upgrade (deliberately deferred, owner's decision 2026-11-01): optional Claude assist for one-off link discovery and selector repair. Not for the 2-min loop — an LLM agent polling 10 items × 10 vendors every 2 min would cost ~$700/day in web-search fees and read stale snippets.
- Scraping from a datacenter IP is mostly blocked; from a home laptop it works far better, and Playwright with a persistent profile passes most Cloudflare checks. Selectors will need occasional tuning via Vendors → Test.
- 2-min cadence × (items × vendors) can be heavy; per-vendor `min_interval_sec` throttles individual vendors.
