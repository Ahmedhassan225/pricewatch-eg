import pytest

from pricewatch.scraping.parser import guess_in_stock, looks_like_price, parse_price


@pytest.mark.parametrize(
    "text,expected",
    [
        ("EGP 12,999", 12999.0),
        ("12.999 ج.م", 12999.0),
        ("١٢٬٩٩٩ جنيه", 12999.0),
        ("LE 1 299.00", 1299.0),
        ("12999", 12999.0),
        ("12,999.50 EGP", 12999.5),
        ("EGP 1,234,567", 1234567.0),
        ("999,99 LE", 999.99),
        ("E£ 45.5", 45.5),
        ("Price: EGP\n  8,499.00\n", 8499.0),
        ("", None),
        (None, None),
        ("Out of stock", None),
        ("EGP 0", None),
    ],
)
def test_parse_price(text, expected):
    assert parse_price(text) == expected


def test_looks_like_price():
    assert looks_like_price("EGP 12,999")
    assert looks_like_price("١٢٬٩٩٩ ج.م")
    assert not looks_like_price("Samsung 55 inch TV")


def test_guess_in_stock():
    assert guess_in_stock("Add to cart EGP 100")
    assert not guess_in_stock("Sold out — notify me")
    assert not guess_in_stock("غير متوفر")
