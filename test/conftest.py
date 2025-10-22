import sqlite3
import pytest

from sanic_testing.reusable import ReusableClient

import veronique.objects as O
from veronique import db
from veronique.context import context
from veronique.api import app


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
def client(conn):
    with ReusableClient(app) as rc:
        yield rc


@pytest.fixture
def admin_client(client):
    _, resp = client.post("/login", data={"username": "admin", "password": "admin"})
    with ReusableClient(app, client_kwargs={"cookies": {"session": resp.cookies["session"]}}) as rc:
        yield rc
