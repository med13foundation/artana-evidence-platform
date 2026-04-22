"""
Registry for storage provider plugins.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.type_definitions.storage import StorageProviderName  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .base import StorageProviderPlugin


class StoragePluginRegistry:
    """In-memory registry for storage provider plugins."""

    def __init__(self) -> None:
        self._plugins: dict[StorageProviderName, StorageProviderPlugin] = {}

    def register(
        self,
        plugin: StorageProviderPlugin,
        *,
        override: bool = False,
    ) -> None:
        if not override and plugin.provider_name in self._plugins:
            msg = f"Storage plugin for {plugin.provider_name.value} already registered"
            raise ValueError(msg)
        self._plugins[plugin.provider_name] = plugin

    def register_many(
        self,
        plugins: Iterable[StorageProviderPlugin],
        *,
        override: bool = False,
    ) -> None:
        for plugin in plugins:
            self.register(plugin, override=override)

    def get(self, provider: StorageProviderName) -> StorageProviderPlugin | None:
        return self._plugins.get(provider)

    def all(self) -> list[StorageProviderPlugin]:
        return list(self._plugins.values())


default_storage_registry = StoragePluginRegistry()


__all__ = ["StoragePluginRegistry", "default_storage_registry"]
