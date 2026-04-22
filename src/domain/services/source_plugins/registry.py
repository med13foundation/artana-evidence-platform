from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.entities.user_data_source import SourceType  # noqa: TC001

from .base import SourcePlugin  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import Iterable


class SourcePluginRegistry:
    """In-memory registry for data source plugins."""

    def __init__(self) -> None:
        self._plugins: dict[SourceType, SourcePlugin] = {}

    def register(self, plugin: SourcePlugin, *, override: bool = False) -> None:
        if not override and plugin.source_type in self._plugins:
            msg = f"Plugin for {plugin.source_type.value} already registered"
            raise ValueError(msg)
        self._plugins[plugin.source_type] = plugin

    def register_many(
        self,
        plugins: Iterable[SourcePlugin],
        *,
        override: bool = False,
    ) -> None:
        for plugin in plugins:
            self.register(plugin, override=override)

    def get(self, source_type: SourceType) -> SourcePlugin | None:
        return self._plugins.get(source_type)

    def list_plugins(self) -> list[SourcePlugin]:
        return list(self._plugins.values())


default_registry = SourcePluginRegistry()


__all__ = ["SourcePluginRegistry", "default_registry"]
