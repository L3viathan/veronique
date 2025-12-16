import json
from pathlib import Path
from hashlib import pbkdf2_hmac
from secrets import token_bytes
from hmac import compare_digest
from base64 import b64decode


key_path = Path(".veronique-key")
if not key_path.exists():
    key = token_bytes(16)
    key_path.write_text(f"{key.hex()}\n")
else:
    key = bytes.fromhex(key_path.read_text().strip())


def sign(data):
    payload = json.dumps(data, sort_keys=True)
    signature = _hash_token(payload.encode(), key)
    return f"{signature}.{payload}"


def unsign(data):
    if not data:
        return
    if data.startswith("Digest "):
        data = b64decode(data.removeprefix("Digest ")).decode()
    signature, _, payload = data.partition(".")
    if _hash_token(payload.encode(), key) == signature:
        return json.loads(payload)


def _hash_token(payload, key):
    return pbkdf2_hmac(
        "sha256",
        payload,
        key,
        1,
    ).hex()


def _hash_pwd(password, salt):
    return pbkdf2_hmac(
        "sha256",
        password,
        salt,
        500_000,
    ).hex()


def hash_password(password, salt=None):
    if salt is None:
        salt = token_bytes(16)
    return _hash_pwd(password.encode(), salt), salt.hex()


def is_correct(password, hash, salt):
    return compare_digest(
        _hash_pwd(password.encode(), bytes.fromhex(salt)),
        hash,
    )
