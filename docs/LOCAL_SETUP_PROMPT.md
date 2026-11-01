# Prompt for a local Claude Code session (Windows laptop)

Copy everything below the line into Claude Code running in a terminal inside the cloned repo.

---

You are finishing the setup of PriceWatch EG on this Windows laptop. Read `CLAUDE.md`,
`README.md` and `docs/PLAN.md` first — the app is complete and tested; your job is to get it
running here, verify the vendors from this home IP, and wire up notifications and remote access.
Do not change the architecture. Work step by step and show me the result of each step.

1. **Environment.** Create `.venv`, install with `pip install -e ".[dev]"`, run
   `playwright install chromium`, then `pytest -q` and `ruff check .`. All 54 tests must pass.

2. **Config.** Copy `.env.example` to `.env`. Ask me for the dashboard password and put it in
   `PW_AUTH_PASSWORD` (user `admin`). Ask me for the ntfy topic names (one per subscriber) and put
   them comma-separated in `PW_NTFY_TOPICS`. Never commit `.env`.

3. **Market data.** Run `pricewatch market` and confirm USD/EGP and gold values print.

4. **First real scan.** Run `pricewatch scan`. The LG GN-H722HLHL refrigerator is pre-seeded.
   Show me the per-vendor table. For every vendor that reports `error` or `not_found` although
   it clearly sells the fridge, open the Vendors page in the dashboard (`pricewatch`, then
   http://127.0.0.1:8765/vendors), use **Test search**, and fix the CSS selectors or search URL
   for that vendor. Vendors known to need attention from a home connection: Amazon Egypt, Jumia,
   2B, Sharaf DG Egypt (Cloudflare — if a captcha appears, set `PW_PLAYWRIGHT_HEADLESS=false`
   in `.env`, restart, solve it once in the window, then set it back to true). Commit selector
   fixes in `pricewatch/scraping/vendors.py` as well so a fresh install gets them.

5. **Notifications.** On the Settings page, send a test notification and confirm it arrived on my
   phone (ntfy app subscribed to my topic). If it fails, show me the error from the Alerts page.

6. **Start at log-on.** Create a Windows Task Scheduler task "PriceWatch EG" that runs
   `scripts\run.bat` when I log on (use `schtasks /create` or walk me through the UI). Verify
   the dashboard answers after a fresh start.

7. **Remote access.** Confirm the red "No login is set" banner is gone. Then run
   `ngrok http 8765` and give me the https URL. Check from the ngrok URL that the browser asks
   for the login. Optionally also pass `--basic-auth="admin:<password>"` to ngrok.

8. **Hand-back.** Tell me: which vendors found the fridge and at what price, which are still
   failing and why, the ngrok URL, and the Task Scheduler task name. Commit and push your
   changes (never `.env`, never the SQLite DB).
