import pytest


def test_unauthenticated(client):
    _, resp = client.get("/", follow_redirects=False)
    assert resp.is_redirect
    assert resp.headers["location"] == "/login"


def test_authenticated(admin_client):
    _, resp = admin_client.get("/", follow_redirects=False)
    assert not resp.is_redirect


def test_user_cant_write(user_client):
    _, resp = user_client.get("/", follow_redirects=False)
    assert not resp.is_redirect

    _, resp = user_client.post("/users/new")
    assert resp.status_code == 403
