from app.domain.auth.passwords import hash_password, needs_rehash, verify_password


def test_hash_is_not_plaintext_and_is_salted():
    h1 = hash_password("correct horse battery staple")
    h2 = hash_password("correct horse battery staple")
    assert "correct horse" not in h1
    assert h1.startswith("$argon2id$")
    assert h1 != h2  # random salt


def test_verify_accepts_correct_and_rejects_wrong():
    h = hash_password("s3cr3t-passphrase")
    assert verify_password(h, "s3cr3t-passphrase") is True
    assert verify_password(h, "wrong") is False


def test_verify_returns_false_on_garbage_hash():
    assert verify_password("not-a-hash", "whatever") is False


def test_needs_rehash_false_for_fresh_hash_true_for_garbage():
    assert needs_rehash(hash_password("abcdefghij")) is False
    assert needs_rehash("not-a-hash") is True
