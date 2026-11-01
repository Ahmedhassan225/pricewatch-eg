from pricewatch.analysis.availability import detect_stock_change, is_available
from pricewatch.models import AlertKind, LinkStatus

F, NF, ERR = LinkStatus.found, LinkStatus.not_found, LinkStatus.error
BASE = dict(median_30d=10000.0, target_price=None, good_price_only=False)


def test_is_available():
    assert is_available(F, True) and is_available(F, None)
    assert (
        not is_available(F, False) and not is_available(NF, True) and not is_available(None, None)
    )


def test_out_of_stock_when_marked():
    ev = detect_stock_change(
        prev_status=F,
        prev_in_stock=True,
        prev_price=9900,
        new_status=F,
        new_in_stock=False,
        price=9900,
        **BASE,
    )
    assert ev.kind == AlertKind.out_of_stock and "out of stock" in ev.reason


def test_out_of_stock_when_listing_disappears():
    ev = detect_stock_change(
        prev_status=F,
        prev_in_stock=True,
        prev_price=9900,
        new_status=NF,
        new_in_stock=False,
        price=None,
        **BASE,
    )
    assert ev.kind == AlertKind.out_of_stock and "disappeared" in ev.reason


def test_error_is_not_a_stock_change():
    assert (
        detect_stock_change(
            prev_status=F,
            prev_in_stock=True,
            prev_price=9900,
            new_status=ERR,
            new_in_stock=True,
            price=None,
            **BASE,
        )
        is None
    )


def test_first_discovery_is_not_back_in_stock():
    assert (
        detect_stock_change(
            prev_status=LinkStatus.pending,
            prev_in_stock=None,
            prev_price=None,
            new_status=F,
            new_in_stock=True,
            price=9000,
            **BASE,
        )
        is None
    )


def test_back_in_stock_good_price():
    ev = detect_stock_change(
        prev_status=F,
        prev_in_stock=False,
        prev_price=9900,
        new_status=F,
        new_in_stock=True,
        price=9500,
        **BASE,
    )
    assert ev.kind == AlertKind.back_in_stock and ev.good_price


def test_back_in_stock_bad_price_filtered_when_configured():
    kw = dict(BASE, good_price_only=True)
    assert (
        detect_stock_change(
            prev_status=NF,
            prev_in_stock=False,
            prev_price=9900,
            new_status=F,
            new_in_stock=True,
            price=12000,
            **kw,
        )
        is None
    )
    ev = detect_stock_change(
        prev_status=NF,
        prev_in_stock=False,
        prev_price=9900,
        new_status=F,
        new_in_stock=True,
        price=12000,
        **BASE,
    )
    assert ev is not None and not ev.good_price


def test_back_in_stock_target_beats_median():
    ev = detect_stock_change(
        prev_status=F,
        prev_in_stock=False,
        prev_price=9900,
        new_status=F,
        new_in_stock=True,
        price=11000,
        median_30d=10000.0,
        target_price=11500,
        good_price_only=True,
    )
    assert ev is not None and ev.good_price and "target" in ev.reason
