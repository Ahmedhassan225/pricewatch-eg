from pricewatch.models import Vendor


def test_seed_vendors_inserted(db_session):
    vendors = db_session.query(Vendor).all()
    assert len(vendors) >= 10
    assert sum(v.enabled for v in vendors) == 10
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
