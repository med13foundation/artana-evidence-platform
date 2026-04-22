"""ASGI entrypoint for the standalone harness service."""

from __future__ import annotations

from .app import create_app

app = create_app()

__all__ = ["app", "create_app"]
