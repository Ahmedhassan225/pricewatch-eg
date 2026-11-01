import os
import tempfile

import pytest

os.environ.setdefault("PW_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))


@pytest.fixture
def db_session():
    from pricewatch.db import init_db, reset_engine_for_tests, session_scope

    path = os.path.join(tempfile.mkdtemp(), "t.db")
    reset_engine_for_tests(f"sqlite:///{path}")
    init_db()
    with session_scope() as s:
        yield s
