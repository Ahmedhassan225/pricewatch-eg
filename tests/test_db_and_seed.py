from pricewatch.models import Item, Vendor


def test_seed_vendors_inserted(db_session):
    vendors = db_session.query(Vendor).all()
    assert len(vendors) >= 10
    assert sum(v.enabled for v in vendors) == 14
    slugs = {v.slug for v in vendors}
    assert {
        "amazon-eg",
        "noon-eg",
        "jumia-eg",
        "btech",
        "2b",
        "rayashop",
        "carrefour-eg",
        "tradeline",
        "dubaiphone",
        "elaraby",
    } <= slugs


def test_seed_item_present_with_pin(db_session):
    items = db_session.query(Item).all()
    assert len(items) == 1 and "GN-H722HLHL" in items[0].query
    pinned = [lk for lk in items[0].links if lk.pinned]
    assert pinned and pinned[0].vendor.slug == "homzmart"
