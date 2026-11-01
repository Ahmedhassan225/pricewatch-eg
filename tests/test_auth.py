import base64

from pricewatch.config import settings
from pricewatch.web.auth import _credentials_ok, auth_enabled


def test_auth_disabled_without_password(monkeypatch):
    monkeypatch.setattr(settings, "auth_password", "")
    assert not auth_enabled()


def test_credentials(monkeypatch):
    monkeypatch.setattr(settings, "auth_user", "admin")
    monkeypatch.setattr(settings, "auth_password", "s3cret")
    ok = "Basic " + base64.b64encode(b"admin:s3cret").decode()
    bad = "Basic " + base64.b64encode(b"admin:wrong").decode()
    assert _credentials_ok(ok)
    assert not _credentials_ok(bad)
    assert not _credentials_ok(None)
    assert not _credentials_ok("Bearer x")
    assert not _credentials_ok("Basic not-base64!!")
