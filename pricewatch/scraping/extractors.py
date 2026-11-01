"""Turn a fetched search page (or product page) into Candidates.

Strategy cascade (see docs/PLAN.md): shopify JSON → JSON-LD → vendor CSS → heuristic.
All functions are pure (HTML in, candidates out) so they can be tested with fixtures.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from pricewatch.scraping.matcher import Candidate
from pricewatch.scraping.parser import guess_in_stock, looks_like_price, parse_price


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def _first_text(node, selector: str | None) -> str:
    if not selector:
        return ""
    for sel in [s.strip() for s in selector.split(",") if s.strip()]:
        el = node.select_one(sel)
        if el is not None:
            txt = el.get("title") if el.name != "img" and not el.get_text(strip=True) else None
            return (txt or el.get_text(" ", strip=True)).strip()
    return ""


def _first_href(node, selector: str | None, base_url: str) -> str:
    sels = [s.strip() for s in (selector or "a[href]").split(",") if s.strip()]
    for sel in sels:
        el = node.select_one(sel)
        if el is not None and el.get("href"):
            return urljoin(base_url, el["href"])
    if node.name == "a" and node.get("href"):
        return urljoin(base_url, node["href"])
    return ""


# ---------- Shopify ----------
def shopify_suggest_url(base_url: str, query: str) -> str:
    from urllib.parse import quote_plus

    return (
        f"{base_url.rstrip('/')}/search/suggest.json?q={quote_plus(query)}"
        "&resources[type]=product&resources[limit]=10&resources[options][unavailable_products]=last"
    )


def extract_shopify_suggest(payload: str, base_url: str) -> list[Candidate]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    products = (data.get("resources", {}).get("results", {}) or {}).get("products", [])
    out: list[Candidate] = []
    for p in products:
        price = parse_price(str(p.get("price") or p.get("price_min") or ""))
        out.append(
            Candidate(
                title=p.get("title", ""),
                price=price,
                url=urljoin(base_url, p.get("url", "")),
                in_stock=bool(p.get("available", True)),
            )
        )
    return out


# ---------- JSON-LD ----------
def _iter_jsonld(soup: BeautifulSoup):
    for tag in soup.find_all("script", type=re.compile("ld\\+json", re.I)):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                yield node
                for key in ("@graph", "itemListElement", "mainEntity", "item"):
                    if key in node:
                        stack.append(node[key])


def _offer_price(offers) -> tuple[float | None, bool]:
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        return None, True
    price = offers.get("price") or offers.get("lowPrice") or offers.get("highPrice")
    avail = str(offers.get("availability", "")).lower()
    in_stock = "outofstock" not in avail and "soldout" not in avail
    return parse_price(str(price) if price is not None else None), in_stock


def extract_jsonld(html: str, base_url: str) -> list[Candidate]:
    out: list[Candidate] = []
    for node in _iter_jsonld(_soup(html)):
        t = node.get("@type")
        types = t if isinstance(t, list) else [t]
        if "Product" not in types:
            continue
        price, in_stock = _offer_price(node.get("offers"))
        offers = node.get("offers")
        url = node.get("url") or (offers.get("url", "") if isinstance(offers, dict) else "")
        out.append(
            Candidate(
                title=str(node.get("name", "")),
                price=price,
                url=urljoin(base_url, str(url or "")),
                in_stock=in_stock,
            )
        )
    return out


# ---------- CSS ----------
def extract_css(html: str, base_url: str, selectors: dict) -> list[Candidate]:
    soup = _soup(html)
    card_sel = selectors.get("card")
    if not card_sel:
        return []
    out: list[Candidate] = []
    for card in soup.select(card_sel)[:40]:
        title = _first_text(card, selectors.get("title"))
        price_txt = _first_text(card, selectors.get("price"))
        url = _first_href(card, selectors.get("link"), base_url)
        if not title or not url:
            continue
        out.append(
            Candidate(
                title=title,
                price=parse_price(price_txt),
                url=url,
                in_stock=guess_in_stock(card.get_text(" ", strip=True)),
            )
        )
    return out


# ---------- Heuristic ----------
def extract_heuristic(html: str, base_url: str) -> list[Candidate]:
    """Last resort: any anchor whose nearby block contains a currency-tagged number."""
    soup = _soup(html)
    out: list[Candidate] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        title = a.get("title") or a.get_text(" ", strip=True)
        if not title or len(title) < 8:
            continue
        block = a
        price = None
        for _ in range(4):  # climb a few levels looking for a price
            block = block.parent
            if block is None:
                break
            txt = block.get_text(" ", strip=True)
            if looks_like_price(txt) and len(txt) < 600:
                m = re.search(
                    r"(?:EGP|LE|L\.E|ج\.م|جنيه|E£|£)\s*[\d٠-٩,\.\s]+|[\d٠-٩,\.]+\s*(?:EGP|LE|L\.E|ج\.م|جنيه)",
                    txt,
                )
                if m:
                    price = parse_price(m.group(0))
                    break
        if price is None:
            continue
        url = urljoin(base_url, a["href"])
        if url in seen:
            continue
        seen.add(url)
        out.append(Candidate(title=title[:300], price=price, url=url))
    return out


# ---------- Product page ----------
def extract_product_price(html: str, selectors: dict) -> tuple[float | None, bool, str | None]:
    """For pinned product URLs. Returns (price, in_stock, title)."""
    soup = _soup(html)
    title = None
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = og["content"].strip()
    elif soup.title and soup.title.string:
        title = soup.title.string.strip()

    for node in _iter_jsonld(soup):
        t = node.get("@type")
        if "Product" in (t if isinstance(t, list) else [t]):
            price, in_stock = _offer_price(node.get("offers"))
            if price is not None:
                return price, in_stock, node.get("name") or title

    sel = selectors.get("product_price") or selectors.get("price")
    if sel:
        for s in [x.strip() for x in sel.split(",") if x.strip()]:
            for el in soup.select(s):
                p = parse_price(el.get_text(" ", strip=True) or el.get("content", ""))
                if p:
                    return p, guess_in_stock(soup.get_text(" ", strip=True)[:5000]), title

    for meta in soup.find_all(
        "meta", attrs={"property": re.compile("price:amount|product:price", re.I)}
    ):
        p = parse_price(meta.get("content", ""))
        if p:
            return p, True, title
    for meta in soup.find_all("meta", attrs={"itemprop": "price"}):
        p = parse_price(meta.get("content", ""))
        if p:
            return p, True, title
    return None, True, title


def extract_candidates(
    html: str, base_url: str, strategy: str, selectors: dict
) -> tuple[list[Candidate], str]:
    """Run the requested strategy (or the auto cascade). Returns (candidates, strategy_used)."""
    order = ["jsonld", "css", "heuristic"] if strategy in ("auto", "shopify") else [strategy]
    for name in order:
        if name == "jsonld":
            cands = extract_jsonld(html, base_url)
        elif name == "css":
            cands = extract_css(html, base_url, selectors)
        else:
            cands = extract_heuristic(html, base_url)
        priced = [c for c in cands if c.price is not None]
        if priced:
            return priced, name
    return [], order[-1]
