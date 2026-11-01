"""Pick the search result that best matches what the user asked for."""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz


@dataclass
class Candidate:
    title: str
    price: float | None
    url: str
    in_stock: bool = True
    score: float = 0.0


_NOISE = re.compile(r"[^\w\s\-\+\.]", re.UNICODE)
_UNIT_TOKEN = re.compile(
    r"^\d+(?:\.\d+)?(?:gb|tb|mb|mah|mm|cm|m|inch|in|hz|w|kw|kg|g|l|ltr|liter|litre|k|p|x)$"
)


def _clean(s: str) -> str:
    return _NOISE.sub(" ", s.lower()).strip()


def model_codes(text: str) -> set[str]:
    """Tokens that look like model numbers: letters+digits, ≥5 chars (gn-h722hlhl, 55ur78006lk)."""
    out = set()
    for tok in _clean(text).split():
        core = tok.strip("-.")
        if (
            len(core) < 5
            or not any(c.isdigit() for c in core)
            or not any(c.isalpha() for c in core)
        ):
            continue
        if _UNIT_TOKEN.match(core):  # "256gb", "65inch", "5000mah" are specs, not model codes
            continue
        out.add(core)
    return out


def score_title(query: str, title: str) -> float:
    q, t = _clean(query), _clean(title)
    if not q or not t:
        return 0.0
    # An exact model code in the title is decisive — this is how we match Arabic titles
    # ("ثلاجة ال جي 506 لتر - GN-H722HLHL") against an English query.
    codes = model_codes(q)
    compact_title = t.replace(" ", "").replace("-", "")
    if codes and any(c.replace("-", "") in compact_title for c in codes):
        return 95.0
    # token_set handles extra words in store titles ("… 256GB Phantom Black Dual SIM")
    ts = fuzz.token_set_ratio(q, t)
    # every query token that carries a digit (model numbers, sizes: "s24", "55", "ur78")
    # must appear somewhere in the title, ignoring spaces, or we penalise heavily
    compact_t = t.replace(" ", "")
    missing = [tok for tok in q.split() if any(ch.isdigit() for ch in tok) and tok not in compact_t]
    penalty = 25 * len(missing)
    return max(0.0, ts - penalty)


def best_match(query: str, candidates: list[Candidate], threshold: float) -> Candidate | None:
    best: Candidate | None = None
    for c in candidates:
        c.score = score_title(query, c.title)
        if c.price is None:
            continue
        if c.score < threshold:
            continue
        # prefer higher score, then cheaper
        if best is None or (c.score, -c.price) > (best.score, -best.price):
            best = c
    return best
