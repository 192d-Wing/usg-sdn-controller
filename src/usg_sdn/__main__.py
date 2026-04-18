"""Entry point for `python -m usg_sdn` and the `usg-sdn` script: starts the API."""
from __future__ import annotations

import uvicorn

from .config import settings
from .logging import configure_logging


def main() -> None:
    configure_logging()
    uvicorn.run(
        "usg_sdn.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        log_config=None,
    )


if __name__ == "__main__":
    main()
