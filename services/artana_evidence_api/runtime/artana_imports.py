"""Optional artana-kernel imports used by runtime support."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, cast

if TYPE_CHECKING:
    from artana.store import EventStore

_ARTANA_IMPORT_ERROR: Exception | None = None
_ARTANA_MODEL_IMPORT_ERROR: Exception | None = None
SingleStepModelClient: Any = None
ArtanaKernel: Any = None
TenantContext: Any = None
LiteLLMAdapter: Any = None


class PostgresStoreFactory(Protocol):
    def __call__(
        self,
        dsn: str,
        *,
        min_pool_size: int,
        max_pool_size: int,
        command_timeout_seconds: float,
    ) -> EventStore: ...


def _missing_postgres_store(
    dsn: str,
    *,
    min_pool_size: int,
    max_pool_size: int,
    command_timeout_seconds: float,
) -> EventStore:
    del dsn, min_pool_size, max_pool_size, command_timeout_seconds
    raise RuntimeError("artana-kernel is required for Artana state storage.")


PostgresStore: PostgresStoreFactory = _missing_postgres_store

try:
    from artana.store import PostgresStore as _ImportedPostgresStore

    PostgresStore = cast("PostgresStoreFactory", _ImportedPostgresStore)
except ImportError as exc:  # pragma: no cover - environment dependent
    _ARTANA_IMPORT_ERROR = exc

try:
    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
    from artana.ports.model import LiteLLMAdapter
except ImportError as exc:  # pragma: no cover - environment dependent
    _ARTANA_MODEL_IMPORT_ERROR = exc

__all__ = [
    "ArtanaKernel",
    "LiteLLMAdapter",
    "PostgresStore",
    "PostgresStoreFactory",
    "SingleStepModelClient",
    "TenantContext",
    "_ARTANA_IMPORT_ERROR",
    "_ARTANA_MODEL_IMPORT_ERROR",
]
