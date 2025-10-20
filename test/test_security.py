from veronique.security import sign, unsign, hash_password, is_correct


def test_roundtrip():
    data = {"arbitrary": ["stuff", "and"], "more": "things"}
    assert unsign(sign(data)) == data


def test_wrong_signature():
    data = {"arbitrary": ["stuff", "and"], "more": "things"}
    token = sign(data)
    sig, _, payload = token.partition(".")
    assert unsign("1"*len(sig) + ".{payload}") is None


def test_password_hashing():
    pwd = "ny49324nyf"
    h, s = hash_password(pwd)

    assert hash_password(pwd, bytes.fromhex(s)) == (h, s)
    assert is_correct(pwd, h, s)
    assert not is_correct("wrongpwd", h, s)
