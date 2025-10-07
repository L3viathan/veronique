from hashlib import pbkdf2_hmac
from secrets import token_bytes
from hmac import compare_digest


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
