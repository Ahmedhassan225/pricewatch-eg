# Architecture

```
browser ──HTTP──▶ FastAPI (pricewatch/web) ──▶ SQLite (data/pricewatch.db)
                      │
                      ├─ APScheduler (pricewatch/scheduler.py)
                      │     ├─ scan_job   every 2 min  → service.scan_and_alert
                      │     └─ market_job every 15 min → market.service.refresh_market
                      │
service.scan_and_alert
   ├─ scraping.engine.run_scan      item × vendor → LinkResult (+ PriceSnapshot)
   │     ├─ fetcher.Fetcher         httpx fast path → Playwright persistent Chromium
   │     ├─ extractors              shopify json → json-ld → css → heuristic
   │     └─ matcher.best_match      rapidfuzz token-set + numeric-token guard
   ├─ analysis.flash.detect         target hit / flash drop / all-time low (+ cooldown)
   └─ notify.dispatcher.dispatch    ntfy (+ telegram)
```

## Data model
- `vendors` — editable store definitions (search URL template, strategy, selectors, flags)
- `items` — what to track (name, search query, target price)
- `item_vendors` — the item as seen on one vendor: product URL (discovered or pinned), status
  `pending|found|not_found|error`, last price, match score
- `price_snapshots` — one row per successful check (the history behind every chart)
- `market_rates` — `usd_egp`, `gold_usd_oz`, `gold_egp_21k_g` over time
- `alerts` — what was detected, whether it was delivered, and why not
- `settings` — UI-editable preferences (ntfy topic, thresholds, interval)

## Decision score (analysis/decision.py)
Start at 50, then: position in 30-day range (±25), all-time low (+15), target (±15),
14-day trend of daily minimum (±10), best vendor vs vendor median (+8),
USD/EGP 30-day change (+8 / −5), gold 21K 30-day change (+3).
≥75 BUY NOW · ≥60 GOOD PRICE · ≥40 WATCH · else WAIT · no price → NO DATA.

## Why a browser
Most Egyptian storefronts render prices client-side (Noon, B.TECH, Raya, Carrefour, Sigma)
or sit behind Cloudflare (Jumia, 2B, eXtra). A persistent Chromium profile keeps cookies and
challenge clearances between cycles, so after the first successful load the cost per check
is one page load. Vendors flagged `render_js=False` (Tradeline/Shopify) skip the browser.
