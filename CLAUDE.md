# PriceWatch EG — project guide for Claude Code

Local-first price tracker for Egyptian online stores. Runs on the owner's laptop,
scans vendors every 2 minutes, stores history in SQLite, shows a decision dashboard,
and pushes free notifications to iPhone + Android via ntfy.

## Quick commands
- Setup: `python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]" && playwright install chromium`
- Run:   `pricewatch` (or `python -m pricewatch`) → http://127.0.0.1:8765
- Test:  `pytest -q`      Lint: `ruff check . && ruff format --check .`
- One scan cycle without the server: `pricewatch scan`     Market data only: `pricewatch market`

## Architecture (read docs/ARCHITECTURE.md for detail)
- `pricewatch/main.py`      FastAPI app + lifespan (starts APScheduler)
- `pricewatch/models.py`    SQLAlchemy models: Vendor, Item, ItemVendor, PriceSnapshot, MarketRate, Alert, Setting
- `pricewatch/scraping/`    fetcher (httpx → Playwright fallback), extractors (shopify/jsonld/css/heuristic), matcher, engine
- `pricewatch/market/`      USD/EGP (open.er-api.com) and gold (gold-api.com) providers, 21K/gram EGP derived
- `pricewatch/analysis/`    flash-sale detection, availability transitions, "buy now?" scoring
- `pricewatch/notify/`      ntfy (default; many subscriber topics) and optional Telegram; scenario toggles in settings_store.SCENARIOS
- `pricewatch/scheduler.py` jobs: scan (2 min), market (15 min)
- `pricewatch/web/`         routes + Jinja templates + Chart.js dashboard; `auth.py` Basic Auth (on when PW_AUTH_PASSWORD set)
- `pricewatch/seed.py`      seed vendors + first item (LG GN-H722HLHL) on a fresh DB

## Conventions
- Python 3.11+, type hints everywhere, `ruff` clean, small pure functions in `analysis/` and `scraping/parser.py` so they are unit-testable without network.
- Never make network calls in tests; use `respx` or fixture HTML in `tests/fixtures/`.
- Vendor definitions are DATA (rows in the `vendors` table seeded from `scraping/vendors.py`), never hard-coded branches. Adding a vendor = adding a row.
- Prices are stored in EGP as floats; `parse_price()` handles Arabic-Indic digits, "ج.م", "EGP", "LE", "L.E", thousands separators.
- Every scheduler job must be idempotent and must swallow+log per-vendor errors so one broken site never stops the cycle.
- Credentials and topics live in `.env` / the settings table only — never in code or git.
- Be polite to vendors: per-vendor min interval, jitter, concurrency ≤ 3, real browser UA. Respect site terms; this is for personal use.

## Workflow (Claude Code best practice)
1. Read `docs/PLAN.md` for scope and status; update the checklist when you finish a task.
2. Plan before coding for anything touching >2 files; keep commits small and descriptive. **Never `git commit` or `git push` until the owner confirms**: finish the work, report it, and leave it uncommitted.
3. Write/adjust a test for parser/analysis changes first, then implement, then `pytest -q`.
4. Verify in the real app (`pricewatch` → open dashboard) before declaring done.
5. Do not add new runtime dependencies without noting why in `docs/PLAN.md`.
