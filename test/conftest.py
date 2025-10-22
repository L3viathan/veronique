import sqlite3
import pytest

import veronique.objects as O
from veronique import db
from veronique.context import context



@pytest.fixture
def conn(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    monkeypatch.setattr(db, "conn", conn)
    monkeypatch.setattr(db, "version", 0)
    cur = conn.cursor()
    with open("veronique_initial_pw", "w") as f:
        f.write("admin")
    for migration in db.MIGRATIONS:
        cur.execute("BEGIN")
        migration(cur)
        cur.execute("COMMIT")
    context.user = O.User(0)
    yield conn


@pytest.fixture
def regular_user(conn):
    u = O.User.new(
        name="someone",
        password="password",
        readable_verbs=[],
        writable_verbs=[],
        viewable_queries=[],
    )
    orig_user = context.user
    try:
        context.user = u
        yield u
    finally:
        context.user = orig_user
