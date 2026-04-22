"""Module entrypoint for running the standalone graph API service."""

from __future__ import annotations

import uvicorn

from .config import get_settings


def main() -> None:
    """Run the standalone graph API service with service-local settings."""
    settings = get_settings()
    uvicorn.run(
        "artana_evidence_db.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )


if __name__ == "__main__":
    main()
