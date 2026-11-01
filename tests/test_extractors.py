from pathlib import Path

from pricewatch.scraping.extractors import (
    extract_candidates,
    extract_css,
    extract_heuristic,
    extract_jsonld,
    extract_product_price,
    extract_shopify_suggest,
    extract_woocommerce,
)

FX = Path(__file__).parent / "fixtures"


def test_shopify():
    c = extract_shopify_suggest(
        (FX / "shopify_suggest.json").read_text(encoding="utf-8"), "https://shop.example"
    )
    assert [x.price for x in c] == [45999.0, 1299.0]
    assert c[0].url == "https://shop.example/products/iphone-15-128-black"


def test_jsonld_itemlist():
    c = extract_jsonld((FX / "jsonld_list.html").read_text(encoding="utf-8"), "https://v.example")
    by = {x.title: x for x in c}
    assert (
        by["Dyson V15 Detect Absolute"].price == 38999.0
        and by["Dyson V15 Detect Absolute"].in_stock
    )
    assert by["Dyson V8 Origin"].in_stock is False
    assert by["Dyson V8 Origin"].url == "https://v.example/p/dyson-v8"


def test_css_selectors():
    sel = {
        "card": "li.product-item",
        "title": ".product-item-link",
        "price": ".special-price .price, .price",
        "link": "a.product-item-link",
    }
    c = extract_css((FX / "css_cards.html").read_text(encoding="utf-8"), "https://v.example", sel)
    assert len(c) == 3
    assert c[0].price == 42500.0 and c[0].url == "https://v.example/en/samsung-s24-256"
    assert c[1].price == 69999.0
    assert c[2].price is None


def test_heuristic_finds_priced_anchor():
    c = extract_heuristic((FX / "css_cards.html").read_text(encoding="utf-8"), "https://v.example")
    titles = {x.title for x in c}
    assert "Samsung Galaxy S24 256GB" in titles


def test_auto_cascade_uses_css_when_no_jsonld():
    sel = {"card": "li.product-item", "title": ".product-item-link", "price": ".price", "link": "a"}
    c, used = extract_candidates(
        (FX / "css_cards.html").read_text(encoding="utf-8"), "https://v.example", "auto", sel
    )
    assert used == "css" and len(c) == 2  # only priced ones


def test_product_page_prefers_jsonld():
    price, in_stock, title = extract_product_price(
        (FX / "product_page.html").read_text(encoding="utf-8"), {"product_price": ".price"}
    )
    assert price == 20499.0 and in_stock and "55UR78006LK" in title


def test_product_page_css_fallback():
    html = '<html><head><meta property="og:title" content="X"/></head><body><div class="final">LE 9,999</div></body></html>'
    price, _, title = extract_product_price(html, {"product_price": ".final"})
    assert price == 9999.0 and title == "X"


def test_woocommerce_minor_unit_and_sku():
    c = extract_woocommerce(
        (FX / "woocommerce_search.json").read_text(encoding="utf-8"), "https://elksass.com"
    )
    assert c[0].price == 31990.0 and "GR-EF40P-T-S" in c[0].title and c[0].in_stock
    assert c[1].price == 65999.0 and c[1].in_stock is False
