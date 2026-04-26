"""Shared SQLAlchemy transaction helpers for coordinated Evidence API writes."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Final

from sqlalchemy.orm import Session

_DEPTH_KEY: Final[str] = "artana_evidence_api.unit_of_work_depth"
_AFTER_COMMIT_KEY: Final[str] = "artana_evidence_api.after_commit_callbacks"
_LOGGER = logging.getLogger(__name__)


def in_unit_of_work(session: Session) -> bool:
    """Return whether the session is inside an explicit service transaction."""

    depth = session.info.get(_DEPTH_KEY, 0)
    return isinstance(depth, int) and depth > 0


def commit_or_flush(session: Session) -> None:
    """Flush inside an explicit unit of work, otherwise preserve legacy commits."""

    if in_unit_of_work(session):
        session.flush()
    else:
        session.commit()


def run_after_commit_or_now(session: Session, callback: Callable[[], None]) -> None:
    """Defer side effects until the current unit of work commits."""

    if not in_unit_of_work(session):
        callback()
        return

    callbacks = session.info.setdefault(_AFTER_COMMIT_KEY, [])
    if isinstance(callbacks, list):
        callbacks.append(callback)


@contextmanager
def session_unit_of_work(session: Session) -> Iterator[None]:  # noqa: PLR0912
    """Own one SQLAlchemy transaction and run deferred callbacks after commit."""

    current_depth = session.info.get(_DEPTH_KEY, 0)
    depth = current_depth if isinstance(current_depth, int) else 0
    outermost = depth == 0
    started_transaction = outermost and not session.in_transaction()
    if started_transaction:
        session.begin()
    session.info[_DEPTH_KEY] = depth + 1
    if outermost:
        session.info[_AFTER_COMMIT_KEY] = []
    try:
        yield
    except Exception:
        if outermost:
            session.rollback()
            session.info.pop(_AFTER_COMMIT_KEY, None)
        raise
    else:
        if outermost:
            callbacks = session.info.pop(_AFTER_COMMIT_KEY, [])
            try:
                session.commit()
            except Exception:
                session.rollback()
                raise
            if isinstance(callbacks, list):
                for callback in callbacks:
                    try:
                        callback()
                    except Exception:
                        _LOGGER.exception(
                            "Deferred unit-of-work callback failed after commit.",
                        )
    finally:
        next_depth = session.info.get(_DEPTH_KEY, 1)
        if isinstance(next_depth, int) and next_depth > 1:
            session.info[_DEPTH_KEY] = next_depth - 1
        else:
            session.info.pop(_DEPTH_KEY, None)
