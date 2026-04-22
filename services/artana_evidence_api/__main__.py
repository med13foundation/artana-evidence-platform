"""Run the standalone harness API service."""

from __future__ import annotations

import uvicorn

from .config import get_settings


def main() -> None:
    """Launch the harness API service with local runtime settings."""
    settings = get_settings()
    # When reload is active uvicorn ignores the workers parameter, so
    # multi-worker mode only applies to non-reload (production) runs.
    uvicorn.run(
        "artana_evidence_api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        workers=settings.workers if not settings.reload else 1,
    )


if __name__ == "__main__":
    main()
