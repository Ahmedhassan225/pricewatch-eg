#!/usr/bin/env bash
# Start PriceWatch EG from anywhere (used by launchd / systemd / cron @reboot).
cd "$(dirname "$0")/.." || exit 1
. .venv/bin/activate
exec pricewatch serve
