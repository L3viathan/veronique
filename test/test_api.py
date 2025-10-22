import pytest


def test_unauthenticated(client):
    req, resp = client.get("/", follow_redirects=False)
    assert resp.is_redirect
    assert resp.headers["location"] == "/login"


def test_authenticated(admin_client):
    req, resp = admin_client.get("/", follow_redirects=False)
    assert not resp.is_redirect
