"""/auth endpoints: principal introspection + API-token management."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import Principal, Scope, current_principal, require_scopes
from ...auth.models import ApiTokenCreate, ApiTokenInfo, ApiTokenIssued, role_scopes
from ...auth.tokens import mint
from ...store import AuthRepo, get_session

router = APIRouter()


@router.get("/me", response_model=Principal)
async def me(principal: Principal = Depends(current_principal)) -> Principal:
    return principal


def _row_to_info(row) -> ApiTokenInfo:
    return ApiTokenInfo(
        id=row.id,
        name=row.name,
        prefix=row.prefix,
        scopes=[Scope(s) for s in (row.scopes or [])],
        created_at=row.created_at,
        last_used_at=row.last_used_at,
    )


@router.get(
    "/tokens",
    response_model=list[ApiTokenInfo],
    dependencies=[Depends(require_scopes(Scope.AUTH_READ))],
)
async def list_tokens(session: AsyncSession = Depends(get_session)) -> list[ApiTokenInfo]:
    rows = await AuthRepo(session).list()
    return [_row_to_info(r) for r in rows]


@router.post(
    "/tokens",
    response_model=ApiTokenIssued,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_scopes(Scope.AUTH_WRITE))],
)
async def create_token(
    body: ApiTokenCreate,
    session: AsyncSession = Depends(get_session),
) -> ApiTokenIssued:
    requested = set(body.scopes)
    if body.role:
        try:
            requested |= set(role_scopes(body.role))
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    if not requested:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no scopes requested")
    minted = mint()
    row = await AuthRepo(session).create(
        token_id=minted.id,
        name=body.name,
        secret_hash=minted.secret_hash,
        prefix=minted.prefix,
        scopes=sorted(s.value for s in requested),
    )
    info = _row_to_info(row)
    return ApiTokenIssued(token=minted.plaintext, **info.model_dump())


@router.delete(
    "/tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_scopes(Scope.AUTH_WRITE))],
)
async def revoke_token(
    token_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    ok = await AuthRepo(session).revoke(token_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such token (or already revoked)")
    return None
