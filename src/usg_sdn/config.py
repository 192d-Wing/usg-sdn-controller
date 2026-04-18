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
