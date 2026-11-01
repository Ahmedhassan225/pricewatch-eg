"""Finding products through a store's published sitemap when its search page is closed to us."""

import asyncio

import httpx
import pytest
import respx

from pricewatch.models import Strategy, Vendor
from pricewatch.scraping import fetcher as fetcher_module
from pricewatch.scraping.engine import search_vendor
from pricewatch.scraping.extractors import (
    is_sitemap_url,
    one_url_per_product,
    parse_sitemap_urls,
    title_from_url,
)
from pricewatch.scraping.fetcher import Fetcher
from pricewatch.scraping.matcher import best_match

SITEMAP = "https://shop.test/store-sitemap.xml"
SHARP = "https://shop.test/product/sharp-1-5-hp-split-air-conditioner-ah-xp12bme/"
LG_OTHER = "https://shop.test/product/lg-top-freezer-506-liter-silver-gn-h722hfhl/"
XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{SHARP}</loc><lastmod>2026-10-01</lastmod></url>
  <url><loc><![CDATA[{LG_OTHER}]]></loc></url>
  <url><loc>https://shop.test/about-us/</loc></url>
</urlset>"""
PAGE = """<html><head><title>Buy Sharp</title>
<meta property="og:title" content="Sharp 1.5 HP Split Air Conditioner – AH-XP12BME"></head><body>
<div class="product-price"><span class="total--sale-price">31,270</span></div>
<button>Add to cart</button></body></html>"""


@pytest.fixture(autouse=True)
def empty_cache():
    fetcher_module._sitemaps.clear()


def _vendor():
    return Vendor(
        slug="shop",
        name="Shop",
        base_url="https://shop.test",
        search_url=SITEMAP,
        strategy=Strategy.auto,
        render_js=False,
        selectors={"product_price": ".product-price .total--sale-price"},
        notes="",
    )


async def _search(query):
    async with Fetcher() as f:
        return await search_vendor(f, _vendor(), query)


def test_is_sitemap_url():
    assert is_sitemap_url(SITEMAP)
    assert is_sitemap_url(SITEMAP + "?v=1")
    assert not is_sitemap_url("https://shop.test/search/?q={q}")
    assert not is_sitemap_url("https://shop.test/feed.xml?q={q}")


def test_parse_sitemap_urls_reads_plain_and_cdata_entries():
    assert parse_sitemap_urls(XML) == [SHARP, LG_OTHER, "https://shop.test/about-us/"]


def test_one_url_per_product_prefers_english_in_any_order():
    ar, en = "https://s.test/ar/products/tv-x100", "https://s.test/en/products/tv-x100"
    other = "https://s.test/ar/products/fan-y200"
    assert one_url_per_product([ar, en, other]) == [en, other]
    assert one_url_per_product([en, ar]) == [en]


@respx.mock(assert_all_called=False)
def test_a_product_listed_in_two_languages_opens_one_page(respx_mock):
    ar = "https://shop.test/ar/products/sharp-ac-ah-xp12bme"
    en = "https://shop.test/en/products/sharp-ac-ah-xp12bme"
    xml = f"<urlset><url><loc>{ar}</loc></url><url><loc>{en}</loc></url></urlset>"
    respx_mock.get(SITEMAP).mock(return_value=httpx.Response(200, text=xml))
    ar_page = respx_mock.get(ar).mock(return_value=httpx.Response(200, text=PAGE))
    en_page = respx_mock.get(en).mock(return_value=httpx.Response(200, text=PAGE))

    cands, _, err = asyncio.run(_search("AH-XP12BME"))

    assert err is None and [c.url for c in cands] == [en]
    assert en_page.called and not ar_page.called


def test_title_from_url_uses_the_last_path_part():
    assert title_from_url(SHARP) == "sharp 1 5 hp split air conditioner ah xp12bme"


@respx.mock(assert_all_called=False)
def test_finds_product_and_reads_real_title_and_price(respx_mock):
    respx_mock.get(SITEMAP).mock(return_value=httpx.Response(200, text=XML))
    page = respx_mock.get(SHARP).mock(return_value=httpx.Response(200, text=PAGE))
    other = respx_mock.get(LG_OTHER).mock(return_value=httpx.Response(200, text=PAGE))

    cands, used, err = asyncio.run(_search("AH-XP12BME"))

    assert err is None and used == "sitemap"
    assert page.called and not other.called  # only the matching page is opened
    best = best_match("AH-XP12BME", cands, 70)
    assert best is not None
    assert best.url == SHARP and best.price == 31270 and best.in_stock
    assert best.title == "Sharp 1.5 HP Split Air Conditioner – AH-XP12BME"


@respx.mock(assert_all_called=False)
def test_a_neighbouring_model_code_opens_no_page(respx_mock):
    respx_mock.get(SITEMAP).mock(return_value=httpx.Response(200, text=XML))
    other = respx_mock.get(LG_OTHER).mock(return_value=httpx.Response(200, text=PAGE))

    cands, used, err = asyncio.run(_search("LG GN-H722HLHL"))

    assert (cands, used, err) == ([], "sitemap", None)
    assert not other.called


@respx.mock(assert_all_called=False)
def test_sitemap_is_downloaded_once_across_searches(respx_mock):
    route = respx_mock.get(SITEMAP).mock(return_value=httpx.Response(200, text=XML))

    async def two_searches_at_once():
        async with Fetcher() as f:
            v = _vendor()
            await asyncio.gather(
                search_vendor(f, v, "NOSUCHCODE1"), search_vendor(f, v, "NOSUCHCODE2")
            )

    asyncio.run(two_searches_at_once())
    asyncio.run(_search("NOSUCHCODE3"))

    assert route.call_count == 1


@respx.mock(assert_all_called=False)
def test_sitemap_failure_is_an_error_and_is_not_cached(respx_mock):
    route = respx_mock.get(SITEMAP).mock(return_value=httpx.Response(503, text="down"))

    cands, used, err = asyncio.run(_search("AH-XP12BME"))
    assert cands == [] and used == "sitemap" and "503" in err

    route.mock(return_value=httpx.Response(200, text=XML))
    _, _, err = asyncio.run(_search("NOSUCHCODE"))
    assert err is None


@respx.mock(assert_all_called=False)
def test_unreadable_product_page_is_an_error_not_a_miss(respx_mock):
    """A wrong "not found" would drop a known link, so a failed read must stay an error."""
    respx_mock.get(SITEMAP).mock(return_value=httpx.Response(200, text=XML))
    respx_mock.get(SHARP).mock(return_value=httpx.Response(200, text="<html><h1>x</h1></html>"))

    cands, used, err = asyncio.run(_search("AH-XP12BME"))

    assert cands == [] and used == "sitemap" and "AH-XP12BME" not in (err or "") and err
