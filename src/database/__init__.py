"""
Database package.

Avoid importing `src.database.session` at package import time to prevent
side-effectful engine creation when importing submodules like
database URL helpers during tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Generator

    from sqlalchemy.orm import Session, sessionmaker

    SessionLocal: sessionmaker[Session]

    def get_session() -> Generator[Session]: ...  # noqa: D401, ANN001


def __getattr__(name: str) -> object:
    if name in {"SessionLocal", "get_session"}:
        from .session import SessionLocal, get_session  # noqa: PLC0415

        return SessionLocal if name == "SessionLocal" else get_session
    raise AttributeError(name)


__all__ = ["SessionLocal", "get_session"]
