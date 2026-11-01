from __future__ import annotations

import argparse
import asyncio
import logging
import sys


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="pricewatch", description="PriceWatch EG")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("serve", help="run the web dashboard + scheduler (default)")
    sc = sub.add_parser("scan", help="run one scan cycle and exit")
    sc.add_argument("--item", type=int, action="append", help="limit to item id(s)")
    sub.add_parser("market", help="refresh USD/EGP and gold once and exit")
    sub.add_parser("test-notify", help="send a test notification")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cmd = args.cmd or "serve"

    if cmd == "serve":
        import uvicorn

        from pricewatch.config import settings

        print(f"PriceWatch EG → http://{settings.host}:{settings.port}")
        uvicorn.run("pricewatch.main:app", host=settings.host, port=settings.port, log_level="info")
        return

    from pricewatch.db import init_db, session_scope

    init_db()
    if cmd == "scan":
        from pricewatch.service import scan_and_alert

        with session_scope() as s:
            print(asyncio.run(scan_and_alert(s, item_ids=args.item)))
    elif cmd == "market":
        from pricewatch.market.service import refresh_market

        with session_scope() as s:
            for r in asyncio.run(refresh_market(s)):
                print(f"{r.kind:16} {r.value:>12,.2f}  ({r.source})")
    elif cmd == "test-notify":
        from pricewatch.service import send_test_alert

        with session_scope() as s:
            a = asyncio.run(send_test_alert(s))
            print("sent" if a.sent else f"NOT sent: {a.send_error}")
            sys.exit(0 if a.sent else 1)


if __name__ == "__main__":
    main()
