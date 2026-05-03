"""FastAPI dependencies that resolve a Principal and enforce scopes."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..logging import log
from ..store import get_session
from ..store.models_sql import ApiTokenRow
from . import oidc, tokens
from .models import ALL_SCOPES, Principal, PrincipalKind, Scope


_ANONYMOUS = Principal(
    kind=PrincipalKind.ANONYMOUS,
    subject="anonymous",
    display_name="anonymous (auth disabled)",
    scopes=frozenset(ALL_SCOPES),
)


def _bearer(auth_header: str | None) -> str | None:
    if not auth_header:
        return None
    scheme, _, value = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return None
    return value.strip()


async def _resolve_api_token(token: str, session: AsyncSession) -> Principal | None:
    parsed = tokens.parse(token)
    if parsed is None:
        return None
    token_id, secret = parsed
    row = await session.get(ApiTokenRow, token_id)
    if row is None or row.revoked_at is not None:
        return None
    if not tokens.verify_secret(secret, row.secret_hash):
        return None
    row.last_used_at = datetime.now(timezone.utc)
    await session.commit()
    return Principal(
        kind=PrincipalKind.API_TOKEN,
        subject=row.id,
        display_name=row.name,
        scopes=frozenset(Scope(s) for s in (row.scopes or [])),
        issued_at=row.created_at,
    )


async def current_principal(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    """Resolve the caller. 401 on a missing/invalid bearer; never 403 here."""
    if not settings.auth_enabled:
        return _ANONYMOUS

    token = _bearer(authorization)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if token.startswith(settings.api_token_prefix):
        principal = await _resolve_api_token(token, session)
        if principal is not None:
            return principal
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid api token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if settings.oidc_issuer:
        try:
            return oidc.verify(token)
        except oidc.OidcError as e:
            log.info("oidc-rejected", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"jwt rejected: {e}",
                headers={"WWW-Authenticate": "Bearer"},
            ) from e

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="unrecognised credential",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_scopes(*required: Scope):
    """Dependency factory: enforces that the resolved principal carries all
    of ``required``. Returns the Principal so the route can use it."""
    needed = frozenset(required)

    async def _dep(principal: Principal = Depends(current_principal)) -> Principal:
        if not principal.has_all(needed):
            missing = sorted(s.value for s in needed - principal.scopes)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "insufficient_scope", "missing": missing},
            )
        return principal

    return _dep
