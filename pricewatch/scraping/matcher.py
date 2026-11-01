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


def _clean(s: str) -> str:
    return _NOISE.sub(" ", s.lower()).strip()


def score_title(query: str, title: str) -> float:
    q, t = _clean(query), _clean(title)
    if not q or not t:
        return 0.0
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
