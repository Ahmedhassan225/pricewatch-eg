# PriceWatch EG 💸

A small app that runs on your laptop and watches the prices of items you care about
(home electronics mainly, but anything works) across the trusted Egyptian online stores.
Every 2 minutes it re-checks each vendor, keeps the full price history, detects flash
sales, and pushes a free notification to your iPhone and your friend's Android.
The dashboard answers **"should I buy now?"** and shows the USD→EGP and gold (21K/gram)
curves, because those two drive electronics prices in Egypt.

Scraping only — no paid APIs, no cloud, no accounts.

## What you get
- **Top-10 trusted vendors pre-loaded**: Amazon Egypt, Noon, Jumia, B.TECH, 2B, Raya Shop,
  Carrefour Egypt, Tradeline, Dubai Phone, El Araby Group (plus eXtra and Sigma, disabled).
  Add, edit, disable or remove vendors from the Vendors page.
- **Per vendor link or "not found"** for every item, with a one-click Pin to paste the exact
  product URL when auto-discovery misses it.
- **Flash-sale alerts**: drop ≥10% vs the 7-day median, target price hit, or new all-time low.
- **Buy-now verdict** (0–100 score with reasons) using 30-day range, trend, vendor spread,
  USD/EGP momentum and gold momentum.
- **Free phone push** via [ntfy](https://ntfy.sh) (iOS + Android). Telegram optional.

## Install (Windows, macOS or Linux)
Requires Python 3.11+.

```bash
git clone <this repo> pricewatch-eg && cd pricewatch-eg
python -m venv .venv
```
Activate the venv (`.venv\Scripts\activate` on Windows, `source .venv/bin/activate` elsewhere), then:
```bash
pip install -e ".[dev]"
```
```bash
playwright install chromium
```
```bash
cp .env.example .env
```

## Run
```bash
pricewatch
```
Open http://127.0.0.1:8765. The first scan and the market-data fetch run at startup,
then every 2 minutes / 15 minutes. `scripts/run.sh` and `scripts/run.bat` do the same
with the venv activated — good targets for "run at login" (Task Scheduler on Windows,
a LaunchAgent on macOS, or a systemd user service on Linux).

Other commands:
```bash
pricewatch scan          # one scan cycle, prints a summary
```
```bash
pricewatch market        # fetch USD/EGP + gold once
```
```bash
pricewatch test-notify   # send a test push
```

## Phone notifications (free, both platforms)
1. Install **ntfy** on both phones (App Store / Play Store / F-Droid).
2. Pick a long random topic name, e.g. `pricewatch-ahmed-7f3k9q2x`. Anyone who knows it can
   read the alerts, so don't make it guessable.
3. In the app: *Subscribe to topic* → enter that name. Do this on both phones.
4. In PriceWatch → Settings → paste the same topic → *Send test notification*.

## How "not found" and pinning work
For each item × vendor the scanner runs the vendor's search page, extracts product cards
(Shopify JSON → JSON-LD → CSS selectors → heuristic fallback), and picks the best title
match above the threshold. No match → **not found**. If you know the vendor sells it,
open the item page and **Pin** the product URL; pinned pages are read directly every cycle,
which is also the most reliable mode.

## When a vendor stops working
Storefronts redesign often and some use bot protection. On the Vendors page open the
vendor, press **Test search**, and look at what was extracted. Adjust the CSS selectors
(the field hints explain each one) and save. If a vendor shows a captcha, set
`PW_PLAYWRIGHT_HEADLESS=false` in `.env`, restart, solve it once in the window that opens;
the browser profile in `.playwright-profile/` remembers the clearance.

## Development
See `CLAUDE.md` for the project conventions and `docs/PLAN.md` for scope and status.
```bash
pytest -q && ruff check .
```
