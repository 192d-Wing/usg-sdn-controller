"""AuthN + AuthZ for the controller API.

Two principal kinds:
  * **api-token** — opaque bearer token, hashed in the ``api_token`` table.
    Issued via ``sdnctl token create`` or ``POST /auth/tokens``.
  * **oidc** — externally-issued JWT, validated against an OIDC issuer's
    JWKS. The controller is a resource server — it does NOT run OAuth
    flows.

Authorization is **scope-based**. Every protected route declares the
scopes it requires; a principal must hold every required scope.

Built-in scopes:
    intent:read           GET  /intent
    intent:write          PUT  /intent
    devices:read          GET  /devices, GET /devices/{name}
    devices:write         PUT  /devices/{name}
    operations:read       /operations/render, /operations/diff, /pool-status
    operations:reconcile  POST /operations/reconcile
    operations:push       POST /operations/push           ⚠️ device-mutating
    auth:read             GET  /auth/me, GET /auth/tokens
    auth:write            POST /auth/tokens, DELETE /auth/tokens/{id}

Convenience role bundles (computed, not stored):
    viewer    = {intent:read, devices:read, operations:read, auth:read}
    operator  = viewer ∪ {intent:write, devices:write, operations:reconcile}
    admin     = operator ∪ {operations:push, auth:write}
"""
from .deps import current_principal, require_scopes
from .models import ALL_SCOPES, Principal, PrincipalKind, Scope, role_scopes

__all__ = [
    "ALL_SCOPES",
    "Principal",
    "PrincipalKind",
    "Scope",
    "current_principal",
    "require_scopes",
    "role_scopes",
]
