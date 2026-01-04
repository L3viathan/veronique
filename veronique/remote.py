from contextlib import contextmanager

import requests

import veronique.objects as O
from veronique import db
from veronique.context import context


class RemoteConnection:
    def __init__(self, host, token):
        self.host = host
        self.token = token

    def cursor(self):
        return self

    def execute(self, query, params=None):
        r = requests.post(
            f"{self.host}/queries/remote",
            json={"q": query, "p": params or {}},
            headers={"Authorization": f"Digest {self.token}"},
        )
        r.raise_for_status()
        return Fetchable(r.json())


class Fetchable:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def __iter__(self):
        return iter(self.fetchall())

    def fetchone(self):
        return self.rows[0] if self.rows else None


@contextmanager
def connect(host, token):
    conn = RemoteConnection(host, token)
    orig_conn = db.conn
    try:
        db.conn = conn
        context.user = O.User(0)
        yield conn
    finally:
        db.conn = orig_conn
        del context.user
