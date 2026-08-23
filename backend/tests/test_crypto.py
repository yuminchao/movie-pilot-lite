import pytest

from app.config.crypto import InvalidSecret, SecretCipher


@pytest.fixture
def cipher() -> SecretCipher:
    return SecretCipher.from_password("correct horse battery staple")


def test_encrypt_decrypt_round_trip(cipher: SecretCipher) -> None:
    ciphertext = cipher.encrypt("tp=secret; uid=42")

    assert ciphertext != "tp=secret; uid=42"
    assert cipher.decrypt(ciphertext) == "tp=secret; uid=42"


def test_each_encryption_uses_new_nonce(cipher: SecretCipher) -> None:
    assert cipher.encrypt("same") != cipher.encrypt("same")


def test_tampered_ciphertext_is_rejected(cipher: SecretCipher) -> None:
    ciphertext = cipher.encrypt("secret")
    replacement = "A" if ciphertext[-1] != "A" else "B"

    with pytest.raises(InvalidSecret):
        cipher.decrypt(f"{ciphertext[:-1]}{replacement}")

