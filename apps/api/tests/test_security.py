from app.core.security import hash_password, verify_password


def test_password_hash_and_verify_for_login_password():
    password_hash = hash_password("secret123")

    assert password_hash.startswith("$2")
    assert verify_password("secret123", password_hash) is True
    assert verify_password("wrong-pass", password_hash) is False
