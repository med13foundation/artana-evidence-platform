from collections.abc import Generator
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.database.engine_config import build_engine_kwargs
from src.database.url_resolver import resolve_sync_database_url

DATABASE_URL = resolve_sync_database_url()

ENGINE_KWARGS: dict[str, object] = {"future": True, **build_engine_kwargs(DATABASE_URL)}

engine = create_engine(DATABASE_URL, **ENGINE_KWARGS)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def _bool_setting(*, value: bool) -> str:
    return "true" if value else "false"


def set_session_rls_context(
    session: Session,
    *,
    current_user_id: UUID | str | None = None,
    has_phi_access: bool = False,
    is_admin: bool = False,
    bypass_rls: bool = False,
) -> None:
    """
    Set PostgreSQL session settings used by row-level security policies.

    This is a no-op for non-PostgreSQL dialects.
    """
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return

    user_setting = str(current_user_id) if current_user_id is not None else ""
    session.execute(
        text("SELECT set_config('app.current_user_id', :value, false)"),
        {"value": user_setting},
    )
    session.execute(
        text("SELECT set_config('app.has_phi_access', :value, false)"),
        {"value": _bool_setting(value=has_phi_access)},
    )
    session.execute(
        text("SELECT set_config('app.is_admin', :value, false)"),
        {"value": _bool_setting(value=is_admin)},
    )
    session.execute(
        text("SELECT set_config('app.bypass_rls', :value, false)"),
        {"value": _bool_setting(value=bypass_rls)},
    )


def get_session() -> Generator[Session]:
    """Provide a SQLAlchemy session scoped to the request."""
    db = SessionLocal()
    try:
        # Request-scoped sessions are never allowed to bypass RLS by default.
        set_session_rls_context(db, bypass_rls=False)
        yield db
    finally:
        db.close()
