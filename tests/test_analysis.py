from datetime import datetime, timedelta

from pricewatch.analysis.decision import decide
from pricewatch.analysis.flash import detect
from pricewatch.models import AlertKind

NOW = datetime(2026, 11, 1, 12, 0)


def hist(prices, step_hours=6):
    return [
        (NOW - timedelta(hours=step_hours * (len(prices) - i)), p) for i, p in enumerate(prices)
    ]


def test_flash_sale_detected_vs_7d_median():
    d = detect(
        price=8900,
        history=hist([10000, 10100, 9900, 10000, 10050]),
        now=NOW,
        target_price=None,
        flash_drop_pct=10,
        last_alert_at=None,
        last_alert_price=None,
        cooldown=timedelta(hours=6),
    )
    assert d is not None and d.kind == AlertKind.flash_sale and d.baseline == 10000


def test_small_drop_not_flash():
    d = detect(
        price=9700,
        history=hist([10000, 10100, 9900, 10000, 10050]),
        now=NOW,
        target_price=None,
        flash_drop_pct=10,
        last_alert_at=None,
        last_alert_price=None,
        cooldown=timedelta(hours=6),
    )
    assert d is None


def test_target_beats_flash():
    d = detect(
        price=8900,
        history=hist([10000, 10100, 9900]),
        now=NOW,
        target_price=9000,
        flash_drop_pct=10,
        last_alert_at=None,
        last_alert_price=None,
        cooldown=timedelta(hours=6),
    )
    assert d.kind == AlertKind.target_hit


def test_cooldown_suppresses_unless_lower():
    kwargs = dict(
        history=hist([10000, 10100, 9900, 10000, 10050]),
        now=NOW,
        target_price=None,
        flash_drop_pct=10,
        last_alert_at=NOW - timedelta(hours=1),
        cooldown=timedelta(hours=6),
    )
    assert detect(price=8900, last_alert_price=8900, **kwargs) is None
    assert detect(price=8500, last_alert_price=8900, **kwargs) is not None


def test_all_time_low():
    d = detect(
        price=9500,
        history=hist([10000, 9900, 9950, 9900, 10000, 9900]),
        now=NOW,
        target_price=None,
        flash_drop_pct=20,
        last_alert_at=None,
        last_alert_price=None,
        cooldown=timedelta(hours=6),
    )
    assert d.kind == AlertKind.all_time_low


def test_no_data_verdict():
    v = decide(best_price=None, history=[], now=NOW)
    assert v.label == "NO DATA" and v.score == 0


def test_buy_now_at_range_low_with_rising_fx():
    history = [(NOW - timedelta(days=d), 10000 + (d % 7) * 150) for d in range(30, 0, -1)]
    v = decide(
        best_price=9800,
        history=history,
        now=NOW,
        target_price=10500,
        vendor_prices=[9800, 10900, 11200],
        usd_egp_change_30d_pct=4.0,
    )
    assert v.label in ("BUY NOW", "GOOD PRICE") and v.score >= 60
    assert any("target" in r.lower() for r in v.reasons)


def test_wait_when_at_range_high_and_falling():
    history = [
        (NOW - timedelta(days=d), 12000 - (30 - d) * 60) for d in range(30, 0, -1)
    ]  # falling trend
    v = decide(best_price=11900, history=history, now=NOW)
    assert v.label == "WAIT" and v.score < 40


def test_hours_of_history_cannot_produce_buy_now():
    prices = [70000, 70000, 70000, 70000, 70000, 60000]
    history = [(NOW - timedelta(hours=6 - i), p) for i, p in enumerate(prices)]
    v = decide(best_price=60000, history=history, now=NOW)
    assert v.label == "WATCH"
    assert any("3 days" in r for r in v.reasons)
    assert not any("lowest price" in r for r in v.reasons)


def test_flat_message_states_the_days_actually_observed():
    history = [(NOW - timedelta(days=d), 60000) for d in range(5, 0, -1)]
    v = decide(best_price=60000, history=history, now=NOW)
    assert any("flat for 5 days" in r for r in v.reasons)


def test_factors_add_up_to_the_score_and_match_the_reasons():
    history = [(NOW - timedelta(days=d), 10000 + (d % 7) * 150) for d in range(30, 0, -1)]
    v = decide(
        best_price=9800,
        history=history,
        now=NOW,
        target_price=9000,
        vendor_prices=[9800, 10900, 11200],
        usd_egp_change_30d_pct=1.0,
        gold_change_30d_pct=0.5,
    )
    assert v.score < 100  # the cap would otherwise hide the sum
    assert 50 + sum(f.points for f in v.factors) == v.score
    assert [f.text for f in v.factors] == v.reasons


def test_factors_also_list_checks_that_changed_nothing():
    history = [(NOW - timedelta(days=d), 60000) for d in range(5, 0, -1)]
    v = decide(
        best_price=60000,
        history=history,
        now=NOW,
        vendor_prices=[60000, 60500],
        usd_egp_change_30d_pct=0.0,
        gold_change_30d_pct=0.0,
    )
    neutral = [f.text for f in v.factors if f.points == 0]
    assert any("target" in t.lower() for t in neutral)
    assert any("USD/EGP" in t for t in neutral)
    assert any("Gold" in t for t in neutral)
    assert any("vendor" in t.lower() for t in neutral)
