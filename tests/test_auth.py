"""AuthN + AuthZ: token lifecycle, scope enforcement, anon mode, OIDC.

The OIDC test mints an RS256 keypair locally and patches PyJWKClient to
return the public key, so we exercise the real ``jwt.decode`` path
without hitting the network.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from usg_sdn.auth import oidc as oidc_mod
from usg_sdn.auth.models import Scope
from usg_sdn.auth.tokens import mint, parse, verify_secret
from usg_sdn.config import settings
from usg_sdn.store import AuthRepo
from usg_sdn.store.db import Base
from usg_sdn.store.models_sql import ApiTokenRow  # noqa: F401  register mapper


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as s:
        yield s
    await engine.dispose()


# --- API token primitives -------------------------------------------------


def test_token_mint_format() -> None:
    minted = mint()
    assert minted.plaintext.startswith(settings.api_token_prefix)
    parsed = parse(minted.plaintext)
    assert parsed is not None
    token_id, secret = parsed
    assert token_id == minted.id
    assert verify_secret(secret, minted.secret_hash)


def test_token_parse_rejects_garbage() -> None:
    assert parse("not-a-token") is None
    assert parse(settings.api_token_prefix + "short.x") is None
    assert parse(settings.api_token_prefix + "a" * 16) is None  # missing .secret


async def test_token_repo_roundtrip(session: AsyncSession) -> None:
    minted = mint()
    repo = AuthRepo(session)
    await repo.create(
        token_id=minted.id,
        name="ci-bot",
        secret_hash=minted.secret_hash,
        prefix=minted.prefix,
        scopes=["intent:read", "operations:read"],
    )
    rows = await repo.list()
    assert len(rows) == 1
    assert rows[0].name == "ci-bot"
    assert await repo.revoke(minted.id) is True
    assert await repo.revoke(minted.id) is False
    rows_active = await repo.list()
    assert rows_active == []
    rows_all = await repo.list(include_revoked=True)
    assert len(rows_all) == 1


# --- API integration ------------------------------------------------------


@pytest.fixture
def client_factory(monkeypatch, tmp_path):
    """Build a TestClient with auth toggled and a fresh in-memory SQLite DB."""

    def _build(*, auth_enabled: bool, oidc: dict | None = None):
        # Point the controller's DB at a per-test SQLite file so we don't
        # leak state between tests in the same process.
        db_path = tmp_path / f"auth-{auth_enabled}.db"
        monkeypatch.setattr(settings, "db_url", f"sqlite+aiosqlite:///{db_path}")
        monkeypatch.setattr(settings, "auth_enabled", auth_enabled)
        monkeypatch.setattr(settings, "reconcile_enabled", False)
        if oidc:
            for k, v in oidc.items():
                monkeypatch.setattr(settings, k, v)

        # Force the engine + session-maker to rebuild against the new URL.
        from usg_sdn.store import db as db_mod

        new_engine = create_async_engine(settings.db_url, future=True)
        monkeypatch.setattr(db_mod, "engine", new_engine)
        monkeypatch.setattr(
            db_mod, "SessionLocal", async_sessionmaker(new_engine, expire_on_commit=False)
        )

        from usg_sdn.api.app import app

        return TestClient(app)

    return _build


def test_anon_mode_lets_everything_through(client_factory) -> None:
    with client_factory(auth_enabled=False) as client:
        r = client.get("/auth/me")
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] == "anonymous"
        assert "operations:push" in body["scopes"]


def test_missing_bearer_returns_401(client_factory) -> None:
    with client_factory(auth_enabled=True) as client:
        r = client.get("/intent")
        assert r.status_code == 401
        assert r.headers.get("www-authenticate", "").lower() == "bearer"


def test_api_token_lifecycle_and_scope_enforcement(client_factory) -> None:
    with client_factory(auth_enabled=False) as client:
        # Mint a viewer-scope token via the auth API (anon has admin
        # because auth is off).
        r = client.post("/auth/tokens", json={"name": "viewer-bot", "role": "viewer"})
        assert r.status_code == 201, r.text
        issued = r.json()
        token = issued["token"]
        assert token.startswith(settings.api_token_prefix)

    # Now turn auth on and use the token.
    with client_factory(auth_enabled=True) as client:
        # /auth/me works
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        # The token store is per-DB-file, so the token from the previous
        # client doesn't exist in this client's DB. We have to recreate.
        # (Above proves the first half: token issuance + format.)
        assert r.status_code == 401  # token not in this DB
    # Real lifecycle test, single DB:
    with client_factory(auth_enabled=False) as anon:
        r = anon.post("/auth/tokens", json={"name": "viewer", "role": "viewer"})
        token = r.json()["token"]
        # Switch to enforcing without rebuilding the DB.
        from usg_sdn.config import settings as s

        s.auth_enabled = True
        try:
            r = anon.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200
            assert r.json()["kind"] == "api-token"

            # viewer scope can read intent (404 because none stored — but
            # crucially NOT 401/403).
            r = anon.get("/intent", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 404

            # viewer cannot push
            r = anon.post(
                "/operations/push?device=x&confirm=true",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 403
            body = r.json()
            assert body["detail"]["error"] == "insufficient_scope"
            assert "operations:push" in body["detail"]["missing"]
        finally:
            s.auth_enabled = False


def test_revoked_token_is_rejected(client_factory) -> None:
    with client_factory(auth_enabled=False) as anon:
        r = anon.post("/auth/tokens", json={"name": "ephemeral", "role": "viewer"})
        issued = r.json()
        token = issued["token"]
        token_id = issued["id"]
        r = anon.delete(f"/auth/tokens/{token_id}")
        assert r.status_code == 204

        from usg_sdn.config import settings as s

        s.auth_enabled = True
        try:
            r = anon.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 401
        finally:
            s.auth_enabled = False


# --- OIDC -----------------------------------------------------------------


def _rsa_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_priv = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pem_pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return key, pem_priv, pem_pub


def test_oidc_jwt_validation_against_mocked_jwks(monkeypatch) -> None:
    key, pem_priv, pem_pub = _rsa_keypair()
    monkeypatch.setattr(settings, "oidc_issuer", "https://idp.example/")
    monkeypatch.setattr(settings, "oidc_audience", "usg-sdn")
    monkeypatch.setattr(settings, "oidc_jwks_url", "https://idp.example/.well-known/jwks.json")
    oidc_mod.reset_cache()

    now = datetime.now(timezone.utc)
    claims = {
        "iss": "https://idp.example/",
        "aud": "usg-sdn",
        "sub": "alice@example",
        "name": "Alice Operator",
        "scope": "intent:read operations:read",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    token = jwt.encode(claims, pem_priv, algorithm="RS256")

    class _StubKey:
        def __init__(self, k):
            self.key = k

    class _StubClient:
        def __init__(self, *_, **__):
            pass

        def get_signing_key_from_jwt(self, _t):
            return _StubKey(pem_pub)

    monkeypatch.setattr(oidc_mod, "PyJWKClient", _StubClient)
    oidc_mod.reset_cache()

    principal = oidc_mod.verify(token)
    assert principal.kind.value == "oidc"
    assert principal.subject == "alice@example"
    assert Scope.INTENT_READ in principal.scopes
    assert Scope.OPERATIONS_PUSH not in principal.scopes


def test_oidc_jwt_wrong_issuer_rejected(monkeypatch) -> None:
    key, pem_priv, pem_pub = _rsa_keypair()
    monkeypatch.setattr(settings, "oidc_issuer", "https://idp.example/")
    monkeypatch.setattr(settings, "oidc_audience", "usg-sdn")
    monkeypatch.setattr(settings, "oidc_jwks_url", "https://idp.example/.well-known/jwks.json")
    oidc_mod.reset_cache()

    now = datetime.now(timezone.utc)
    claims = {
        "iss": "https://attacker.example/",  # wrong
        "aud": "usg-sdn",
        "sub": "mallory",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    token = jwt.encode(claims, pem_priv, algorithm="RS256")

    class _StubKey:
        def __init__(self, k):
            self.key = k

    class _StubClient:
        def __init__(self, *_, **__):
            pass

        def get_signing_key_from_jwt(self, _t):
            return _StubKey(pem_pub)

    monkeypatch.setattr(oidc_mod, "PyJWKClient", _StubClient)
    oidc_mod.reset_cache()

    with pytest.raises(oidc_mod.OidcError):
        oidc_mod.verify(token)
