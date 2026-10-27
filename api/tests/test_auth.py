import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from synapse_api import auth
from synapse_api.config import get_settings
from synapse_api.domain.enums import Role
from synapse_api.main import create_app

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def client(monkeypatch) -> TestClient:
    fake_jwks = SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=KEY.public_key()))
    monkeypatch.setattr(auth, "_jwks_client", lambda: fake_jwks)
    return TestClient(create_app())


def token(key=KEY, **overrides) -> str:
    settings = get_settings()
    claims = {
        "sub": "po-1",
        "name": "Aline Mbarga",
        "iss": settings.oidc_issuer,
        "aud": settings.oidc_audience,
        "exp": int(time.time()) + 60,
        "realm_access": {"roles": ["PO", "offline_access"]},
    } | overrides
    return jwt.encode(claims, key, algorithm="RS256")


def me(client: TestClient, bearer: str | None):
    headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    return client.get("/me", headers=headers)


def test_valid_token_exposes_synapse_roles_only(client):
    res = me(client, token())
    assert res.status_code == 200
    assert res.json()["roles"] == ["PO"]


@pytest.mark.parametrize(
    "bad",
    [
        None,
        token(key=OTHER_KEY),
        token(exp=int(time.time()) - 10),
        token(iss="https://ailleurs.example/realms/x"),
        token(aud="autre-client"),
    ],
)
def test_invalid_tokens_are_rejected(client, bad):
    assert me(client, bad).status_code == 401


def test_user_from_claims_ignores_unknown_roles():
    user = auth.user_from_claims({"sub": "x", "realm_access": {"roles": ["TESTEUR", "uma_authorization"]}})
    assert user.roles == frozenset({Role.TESTEUR})
    assert user.name == "x"
