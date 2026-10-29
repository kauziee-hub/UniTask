from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from app import cognito
from app.security import hash_password, verify_password


def test_password_hashing():
    stored = hash_password("correct-horse")
    assert stored.startswith("scrypt$")
    assert verify_password("correct-horse", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("anything", None)


class StaticJwks:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, token):
        return type("Key", (), {"key": self.key})()


def test_cognito_id_token_verification(monkeypatch):
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "ap-south-1_TEST")
    monkeypatch.setenv("COGNITO_APP_CLIENT_ID", "client123")
    monkeypatch.setenv("COGNITO_REGION", "ap-south-1")
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwks = StaticJwks(private.public_key())
    now = datetime.now(timezone.utc)
    claims = {
        "sub": "abc-123",
        "aud": "client123",
        "iss": "https://cognito-idp.ap-south-1.amazonaws.com/ap-south-1_TEST",
        "token_use": "id",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    good = jwt.encode(claims, private, algorithm="RS256")
    assert cognito.verify_id_token(good, jwks)["sub"] == "abc-123"

    wrong_audience = jwt.encode({**claims, "aud": "other"}, private, algorithm="RS256")
    assert cognito.verify_id_token(wrong_audience, jwks) is None
    access_token = jwt.encode({**claims, "token_use": "access"}, private, algorithm="RS256")
    assert cognito.verify_id_token(access_token, jwks) is None
    expired = jwt.encode({**claims, "exp": now - timedelta(minutes=1)}, private, algorithm="RS256")
    assert cognito.verify_id_token(expired, jwks) is None
