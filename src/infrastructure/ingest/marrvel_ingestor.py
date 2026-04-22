"""
MARRVEL API client for Artana Resource Library.
Fetches gene-centric variant and phenotype data from MARRVEL.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.infrastructure.ingest import marrvel_ingestor_helpers as helpers
from src.infrastructure.ingest.base_ingestor import BaseIngestor

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from src.type_definitions.common import JSONValue, RawRecord


class MarrvelIngestor(BaseIngestor):
    """MARRVEL API client for fetching gene-centric data."""

    def __init__(self) -> None:
        super().__init__(
            source_name="marrvel",
            base_url="http://api.marrvel.org/data",
            requests_per_minute=120,
            timeout_seconds=30,
        )

    async def fetch_data(self, **kwargs: JSONValue) -> list[RawRecord]:
        return await helpers.fetch_data(self, **kwargs)

    def __getattr__(self, name: str) -> Callable[..., Awaitable[object]]:
        lookup_name = name.removeprefix("_")
        handler_fn = helpers.MARRVEL_FETCH_DISPATCH.get(lookup_name)
        if handler_fn is None:
            msg = f"{type(self).__name__!s} object has no attribute {name!r}"
            raise AttributeError(msg)

        def _bound(*args: object, **kwargs: object) -> Awaitable[object]:
            return handler_fn(self, *args, **kwargs)

        return _bound


__all__ = ["MarrvelIngestor"]
