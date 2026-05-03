"""OIDC JWT validation against an issuer's JWKS.

Validates ``iss``, ``aud``, ``exp``, signature; pulls scopes from either
``scope`` (RFC 8693 space-separated string) or ``scopes`` (array).
JWKS keys are cached in-process for ``settings.oidc_jwks_cache_sec`` seconds.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx
import jwt
from jwt import PyJWKClient, PyJWKClientError

from ..config import settings
from ..logging import log
from .models import Principal, PrincipalKind, Scope


class OidcError(Exception):
    """Raised when JWT validation fails for any reason."""


_JWKS_CLIENT: PyJWKClient | None = None
_JWKS_FETCHED_AT: float = 0.0


def _jwks_url() -> str:
    if settings.oidc_jwks_url:
        return settings.oidc_jwks_url
    if settings.oidc_issuer:
        return settings.oidc_issuer.rstrip("/") + "/.well-known/jwks.json"
    raise OidcError("OIDC not configured (no issuer or jwks_url)")


def _client() -> PyJWKClient:
    global _JWKS_CLIENT, _JWKS_FETCHED_AT
    now = time.time()
    if _JWKS_CLIENT is None or now - _JWKS_FETCHED_AT > settings.oidc_jwks_cache_sec:
        url = _jwks_url()
        _JWKS_CLIENT = PyJWKClient(url, cache_keys=True, lifespan=settings.oidc_jwks_cache_sec)
        _JWKS_FETCHED_AT = now
    return _JWKS_CLIENT


def reset_cache() -> None:
    """Drop the cached JWKS — used by tests."""
    global _JWKS_CLIENT, _JWKS_FETCHED_AT
    _JWKS_CLIENT = None
    _JWKS_FETCHED_AT = 0.0


def _scopes_from_claims(claims: dict) -> frozenset[Scope]:
    raw: list[str] = []
    if (s := claims.get(settings.oidc_scope_claim)) is not None:
        if isinstance(s, str):
            raw = s.split()
        elif isinstance(s, list):
            raw = list(s)
    elif (s := claims.get("scopes")) is not None and isinstance(s, list):
        raw = list(s)
    out: set[Scope] = set()
    for r in raw:
        try:
            out.add(Scope(r))
        except ValueError:
            log.debug("oidc-scope-unknown", scope=r)
    return frozenset(out)


def verify(token: str) -> Principal:
    """Validate a JWT and return a Principal. Raises OidcError on any failure."""
    if not settings.oidc_issuer:
        raise OidcError("OIDC issuer not configured")
    try:
        signing_key = _client().get_signing_key_from_jwt(token).key
    except (PyJWKClientError, httpx.HTTPError) as e:
        raise OidcError(f"jwks lookup failed: {e}") from e

    options = {"require": ["exp", "iss"]}
    audience = settings.oidc_audience
    try:
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256", "RS384", "RS512", "ES256", "ES384"],
            issuer=settings.oidc_issuer,
            audience=audience,
            options=options,
        )
    except jwt.PyJWTError as e:
        raise OidcError(f"jwt invalid: {e}") from e

    sub = str(claims.get("sub") or "")
    if not sub:
        raise OidcError("jwt missing sub")

    iat = claims.get("iat")
    exp = claims.get("exp")
    return Principal(
        kind=PrincipalKind.OIDC,
        subject=sub,
        display_name=claims.get("name") or claims.get("preferred_username") or sub,
        scopes=_scopes_from_claims(claims),
        issuer=str(claims.get("iss") or ""),
        issued_at=datetime.fromtimestamp(iat, tz=timezone.utc) if iat else None,
        expires_at=datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None,
    )
