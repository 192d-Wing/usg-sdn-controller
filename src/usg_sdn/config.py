"""Runtime settings loaded from env / .env."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="USG_SDN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_url: str = "sqlite+aiosqlite:///./usg-sdn.db"
    log_level: str = "INFO"

    api_host: str = "::"
    api_port: int = 8080

    reconcile_interval_sec: int = 60
    reconcile_enabled: bool = True

    link_pool_warn_threshold: float = 0.75
    link_pool_gc: bool = True

    # --- auth -----------------------------------------------------------
    auth_enabled: bool = False
    """Master switch. When False, every request gets a synthetic
    'anonymous' principal with all scopes — convenient for dev, NOT for prod."""

    api_token_prefix: str = "usgsdn_pat_"
    """Constant prefix on every minted API token; helps secret-scanners
    recognise leaked tokens."""

    oidc_issuer: str | None = None
    """Expected ``iss`` claim. If unset, OIDC validation is disabled and
    only API tokens are accepted."""

    oidc_audience: str | None = None
    """Expected ``aud`` claim."""

    oidc_jwks_url: str | None = None
    """JWKS endpoint — usually ``{issuer}/.well-known/jwks.json``. If unset
    and ``oidc_issuer`` is set, derived from the issuer."""

    oidc_jwks_cache_sec: int = 3600
    """How long to cache fetched JWKS keys before re-fetching."""

    oidc_scope_claim: str = "scope"
    """Claim that carries scopes — ``scope`` (RFC 8693, space-separated)
    or ``scopes`` (array). Both forms are accepted regardless."""

    device_ssh_user: str = "sdn"
    device_ssh_key: Path = Field(default=Path("~/.ssh/id_ed25519"))
    device_ssh_timeout_sec: int = 30

    aoscx_user: str = "admin"
    aoscx_password: str = "changeme"
    aoscx_verify_tls: bool = False

    template_dir: Path = Field(
        default=Path(__file__).parent / "templates",
        description="Root directory for vendor Jinja2 templates.",
    )


settings = Settings()
