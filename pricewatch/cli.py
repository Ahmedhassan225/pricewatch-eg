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
    ad = sub.add_parser(
        "add", help="track a new item, e.g. pricewatch add 'LG GN-H722HLHL' --target 60000"
    )
    ad.add_argument("name")
    ad.add_argument("--query", help="search text (defaults to name)")
    ad.add_argument("--target", type=float, help="target price in EGP")
    ad.add_argument(
        "--pin", action="append", default=[], metavar="VENDOR_SLUG=URL", help="pin a product URL"
    )
    ad.add_argument("--no-scan", action="store_true", help="don't scan immediately")
    sub.add_parser("vendors", help="list vendors with their slugs")
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
    elif cmd == "add":
        from pricewatch.models import Item, ItemVendor, LinkStatus, Vendor
        from pricewatch.service import scan_and_alert

        with session_scope() as s:
            it = Item(name=args.name, query=args.query or args.name, target_price=args.target)
            s.add(it)
            s.flush()
            for pin in args.pin:
                slug, _, url = pin.partition("=")
                v = s.query(Vendor).filter_by(slug=slug.strip()).first()
                if v is None:
                    print(f"unknown vendor slug {slug!r} (see `pricewatch vendors`)")
                    continue
                s.add(
                    ItemVendor(
                        item_id=it.id,
                        vendor_id=v.id,
                        product_url=url.strip(),
                        pinned=True,
                        status=LinkStatus.pending,
                    )
                )
            s.flush()
            print(f"added item #{it.id}: {it.name}")
            if not args.no_scan:
                print(asyncio.run(scan_and_alert(s, item_ids=[it.id])))
                for lk in sorted(
                    it.links, key=lambda x: (x.status != LinkStatus.found, x.last_price or 1e18)
                ):
                    price = f"{lk.last_price:,.0f}" if lk.last_price else "—"
                    detail = lk.product_url or lk.last_error or ""
                    print(f"  {lk.vendor.name:18} {lk.status.value:10} {price:>10}  {detail}")
    elif cmd == "vendors":
        from pricewatch.models import Vendor

        with session_scope() as s:
            for v in s.query(Vendor).order_by(Vendor.name).all():
                print(
                    f"{v.slug:14} {'on ' if v.enabled else 'off'}  {v.strategy.value:11} {v.name}"
                )
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
