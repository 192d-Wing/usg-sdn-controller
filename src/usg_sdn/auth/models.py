"""Auth domain types: Principal + scope catalogue."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Scope(StrEnum):
    INTENT_READ = "intent:read"
    INTENT_WRITE = "intent:write"
    DEVICES_READ = "devices:read"
    DEVICES_WRITE = "devices:write"
    OPERATIONS_READ = "operations:read"
    OPERATIONS_RECONCILE = "operations:reconcile"
    OPERATIONS_PUSH = "operations:push"
    AUTH_READ = "auth:read"
    AUTH_WRITE = "auth:write"


ALL_SCOPES: frozenset[Scope] = frozenset(Scope)


_VIEWER = frozenset({Scope.INTENT_READ, Scope.DEVICES_READ, Scope.OPERATIONS_READ, Scope.AUTH_READ})
_OPERATOR = _VIEWER | {Scope.INTENT_WRITE, Scope.DEVICES_WRITE, Scope.OPERATIONS_RECONCILE}
_ADMIN = _OPERATOR | {Scope.OPERATIONS_PUSH, Scope.AUTH_WRITE}


def role_scopes(role: str) -> frozenset[Scope]:
    """Resolve a role name to the union of scopes it carries."""
    role = role.lower()
    if role == "viewer":
        return _VIEWER
    if role == "operator":
        return _OPERATOR
    if role == "admin":
        return _ADMIN
    raise ValueError(f"unknown role: {role!r}")


class PrincipalKind(StrEnum):
    ANONYMOUS = "anonymous"  # auth_enabled=False — full scopes for dev
    API_TOKEN = "api-token"
    OIDC = "oidc"


class Principal(BaseModel):
    """Resolved caller identity attached to each request."""

    model_config = ConfigDict(frozen=True)

    kind: PrincipalKind
    subject: str = Field(description="Token id, JWT sub, or 'anonymous'.")
    display_name: str | None = None
    scopes: frozenset[Scope] = Field(default_factory=frozenset)
    issuer: str | None = None
    issued_at: datetime | None = None
    expires_at: datetime | None = None

    def has(self, scope: Scope) -> bool:
        return scope in self.scopes

    def has_all(self, required: frozenset[Scope]) -> bool:
        return required.issubset(self.scopes)


# --- API token wire models -------------------------------------------------


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    scopes: list[Scope] = Field(default_factory=list)
    role: str | None = Field(
        default=None,
        description="Optional role bundle (viewer / operator / admin). "
        "If set, its scopes are unioned with `scopes`.",
    )


class ApiTokenInfo(BaseModel):
    """Listing/inspection view (never includes the secret)."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    prefix: str
    scopes: list[Scope]
    created_at: datetime
    last_used_at: datetime | None = None


class ApiTokenIssued(ApiTokenInfo):
    """Returned exactly once when a token is created.

    The plaintext ``token`` is never persisted and never shown again.
    """

    token: str
