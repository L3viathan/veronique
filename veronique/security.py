import json
from base64 import b64decode
from hashlib import pbkdf2_hmac
from hmac import compare_digest
from pathlib import Path
from secrets import token_bytes

from veronique.constants import (
    SECURITY_KEY_SIZE,
    SECURITY_PBKDF2_HMAC_ROUNDS,
    SECURITY_SALT_SIZE,
)

# This key is randomly generated if it doesn't exist. It is used to encrypt the
# auth tokens, but does not need to be known to anyone but the Véronique
# instance itself. It should not be included in backups, as regenerating it
# just invalidates existing sessions. If the key is leaked, it can be used to
# forge session tokens and gain admin access to Véronique.
key_path = Path(".veronique-key")
if not key_path.exists():
    key = token_bytes(SECURITY_KEY_SIZE)
    key_path.write_text(f"{key.hex()}\n")
else:
    key = bytes.fromhex(key_path.read_text().strip())


# This is similar to — but simpler than — JWTs. We don't need a header, since
# we know the algorithm used, and we don't bother with keeping standard fields.
# Whatever data gets passed in gets stored in the token, the authentication
# part is responsible for choosing what to store.
def sign(data):
    payload = json.dumps(data, sort_keys=True)
    signature = _hash_token(payload.encode(), key)
    return f"{signature}.{payload}"


def unsign(data):
    # We return either data (on success), or None.
    if not data:
        return
    # The token comes either from an Authorization header (for remote access)
    # or a cookie (regular access), so we strip a leading "Digest ":
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
        SECURITY_PBKDF2_HMAC_ROUNDS,
    ).hex()


def hash_password(password, salt=None):
    if salt is None:
        salt = token_bytes(SECURITY_SALT_SIZE)
    return _hash_pwd(password.encode(), salt), salt.hex()


def is_correct(password, hash, salt):
    # This (as opposed to using `==`) is important to avoid timing attacks:
    return compare_digest(
        _hash_pwd(password.encode(), bytes.fromhex(salt)),
        hash,
    )
