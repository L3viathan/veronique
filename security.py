import json
from contextvars import ContextVar
from pathlib import Path
from hashlib import pbkdf2_hmac
from secrets import token_bytes, token_hex
from hmac import compare_digest


key_path = Path(".veronique-key")
if not key_path.exists():
    key = token_bytes(16)
    key_path.write_text(f"{key.hex()}\n")
else:
    key = bytes.fromhex(key_path.read_text().strip())


def sign(data):
    payload = json.dumps(data, sort_keys=True)
    signature = _hash(payload.encode(), key)
    return f"{signature}.{payload}"


def unsign(data):
    if not data:
        return
    signature, _, payload = data.partition(".")
    if _hash(payload.encode(), key) == signature:
        return json.loads(payload)


def _hash(password, salt):
    return pbkdf2_hmac(
        "sha256",
        password,
        salt,
        500_000,
    ).hex()

def hash_password(password, salt=None):
    if salt is None:
        salt = token_bytes(16)
    return _hash(password.encode(), salt), salt.hex()


def is_correct(password, hash, salt):
    return compare_digest(
        _hash(password.encode(), bytes.fromhex(salt)),
        hash,
    )
