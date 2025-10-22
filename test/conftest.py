import os

import sqlite3
import pytest

from sanic_testing.reusable import ReusableClient


def pytest_sessionstart(session):
    with open("veronique_initial_pw", "w") as f:
        f.write("admin")
    os.environ["VERONIQUE_DB"] = ":memory:"



@pytest.fixture
def client():
    from veronique.api import app
    with ReusableClient(app) as rc:
        yield rc


@pytest.fixture
def admin_client(client):
    from veronique.api import app
    _, resp = client.post("/login", data={"username": "admin", "password": "admin"})
    with ReusableClient(app, client_kwargs={"cookies": {"session": resp.cookies["session"]}}) as rc:
        yield rc
