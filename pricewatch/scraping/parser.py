"""Pure functions for turning messy storefront text into numbers. No network."""

from __future__ import annotations

import re

_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩٬٫", "0123456789,.")
_CURRENCY_HINTS = ("EGP", "LE", "L.E", "ج.م", "جنيه", "£", "E£")
_NUM_RE = re.compile(r"\d[\d,\.\s]*\d|\d")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_ARABIC_INDIC)).strip()


def parse_price(text: str | None) -> float | None:
    """Extract the first plausible EGP amount from text.

    Handles: "EGP 12,999", "12.999 ج.م", "١٢٬٩٩٩ جنيه", "LE 1 299.00", "12999",
    "12,999.50". Returns None when nothing numeric is found or the value is absurd.
    """
    if not text:
        return None
    t = normalize_text(text)
    # strip thousands separators spelled as spaces between digit groups ("1 299")
    t = re.sub(r"(?<=\d) (?=\d{3}\b)", "", t)
    m = _NUM_RE.search(t)
    if not m:
        return None
    raw = m.group(0).replace(" ", "")
    # Decide decimal separator. Egyptian stores mostly use "," thousands and "." decimals,
    # but "12.999" (3 digits after a dot, no other dot) is a thousands separator.
    if raw.count(",") and raw.count("."):
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif raw.count(","):
        parts = raw.split(",")
        raw = raw.replace(",", "") if all(len(p) == 3 for p in parts[1:]) else raw.replace(",", ".")
    elif raw.count(".") == 1:
        whole, frac = raw.split(".")
        if len(frac) == 3 and whole:
            raw = whole + frac
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    if value <= 0 or value > 50_000_000:
        return None
    return round(value, 2)


def looks_like_price(text: str) -> bool:
    t = normalize_text(text)
    return any(h.lower() in t.lower() for h in _CURRENCY_HINTS) and bool(_NUM_RE.search(t))


def guess_in_stock(text: str) -> bool:
    t = normalize_text(text).lower()
    bad = ("out of stock", "sold out", "unavailable", "notify me", "غير متوفر", "نفذت الكمية")
    return not any(b in t for b in bad)
