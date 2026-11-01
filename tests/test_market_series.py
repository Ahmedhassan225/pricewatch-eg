from datetime import timedelta

from pricewatch.market.service import series
from pricewatch.models import MarketRate, utcnow


def _noon(days_ago):
    """A fixed time of day, so readings never straddle midnight when the test runs."""
    return utcnow().replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)


def _add(s, value, captured_at):
    s.add(MarketRate(kind="usd_egp", value=value, source="test", captured_at=captured_at))
    s.flush()


def test_series_empty_without_readings(db_session):
    assert series(db_session, "usd_egp") == []


def test_series_uses_each_reading_while_history_spans_one_day(db_session):
    for i in range(3):
        _add(db_session, 50.0 + i, _noon(1) + timedelta(minutes=15 * i))

    points = series(db_session, "usd_egp")

    assert [v for _, v in points] == [50.0, 51.0, 52.0]
    assert all("T" in stamp for stamp, _ in points)  # ISO time, so the chart can place them


def test_series_keeps_one_point_per_day_once_history_spans_days(db_session):
    _add(db_session, 50.0, _noon(3))
    _add(db_session, 51.0, _noon(3) + timedelta(minutes=30))
    _add(db_session, 52.0, _noon(1))

    points = series(db_session, "usd_egp")

    assert [v for _, v in points] == [51.0, 52.0]
