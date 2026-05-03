"""API token minting + verification.

Token format:
    <prefix><id>.<secret>
where ``id`` is a 16-hex-char identifier (visible in DB and logs) and
``secret`` is 48 hex chars of CSPRNG entropy. Only the SHA-256 of the
secret is persisted; the plaintext is shown to the operator exactly once
at creation time.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from ..config import settings


@dataclass(frozen=True)
class MintedToken:
    id: str
    plaintext: str       # full token, including prefix.id.secret — return once
    secret_hash: str     # what we persist
    prefix: str          # token prefix for display (settings.api_token_prefix + id[:6])


def mint() -> MintedToken:
    token_id = secrets.token_hex(8)        # 16 chars
    secret = secrets.token_hex(24)         # 48 chars
    plaintext = f"{settings.api_token_prefix}{token_id}.{secret}"
    return MintedToken(
        id=token_id,
        plaintext=plaintext,
        secret_hash=hashlib.sha256(secret.encode()).hexdigest(),
        prefix=f"{settings.api_token_prefix}{token_id[:6]}…",
    )


def parse(token: str) -> tuple[str, str] | None:
    """Split ``<prefix><id>.<secret>`` into (id, secret). Returns None on
    a malformed token; never raises."""
    prefix = settings.api_token_prefix
    if not token.startswith(prefix):
        return None
    body = token[len(prefix):]
    if "." not in body:
        return None
    token_id, _, secret = body.partition(".")
    if len(token_id) != 16 or len(secret) != 48:
        return None
    return token_id, secret


def verify_secret(secret: str, expected_hash: str) -> bool:
    """Constant-time compare of SHA-256(secret) against the stored hash."""
    actual = hashlib.sha256(secret.encode()).hexdigest()
    return hmac.compare_digest(actual, expected_hash)
