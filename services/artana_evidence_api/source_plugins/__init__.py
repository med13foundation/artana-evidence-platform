"""Datasource plugin package.

Keep this package initializer intentionally small. Plugins are discovered
through ``source_plugins.registry`` so import side effects do not become the
registration mechanism.
"""

__all__: list[str] = []
