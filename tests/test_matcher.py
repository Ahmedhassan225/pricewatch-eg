from pricewatch.scraping.matcher import Candidate, best_match, score_title


def test_score_prefers_exact_model():
    q = "Samsung Galaxy S24 256GB"
    good = "Samsung Galaxy S24 5G Dual SIM 256GB 8GB RAM Onyx Black"
    wrong = "Samsung Galaxy S23 256GB Phantom Black"
    assert score_title(q, good) > score_title(q, wrong)
    assert score_title(q, wrong) < 70  # missing numeric token "24" penalised


def test_best_match_threshold_and_price():
    q = "LG 55 inch 4K TV UR78"
    cands = [
        Candidate("LG 55UR78006LK 55 inch 4K UHD Smart TV", 21999, "u1"),
        Candidate("LG 55UR78006LK 55 inch 4K UHD Smart TV", 20999, "u2"),
        Candidate("Samsung 55 inch Crystal 4K TV", 19999, "u3"),
        Candidate("LG 55 inch 4K TV UR78 — case", None, "u4"),
    ]
    best = best_match(q, cands, 70)
    assert best is not None and best.url == "u2"  # same score → cheaper wins


def test_best_match_none_when_below_threshold():
    assert (
        best_match("Dyson V15 Detect", [Candidate("Philips Air Fryer XXL", 5000, "u")], 70) is None
    )


def test_model_code_matches_arabic_title():
    q = "LG GN-H722HLHL refrigerator"
    arabic = "ثلاجة ال جي 506 لتر سمارت نوفروست فضي - GN-H722HLHL"
    other_variant = "LG Top Freezer 506 Liter Door Cooling GN-H722HFHL"
    assert score_title(q, arabic) >= 90
    assert score_title(q, other_variant) < 70  # different suffix = different product
    best = best_match(
        q, [Candidate(arabic, 62999, "u1"), Candidate(other_variant, 65999, "u2")], 70
    )
    assert best is not None and best.url == "u1"
