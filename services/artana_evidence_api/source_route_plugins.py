"""Registry for public direct-source route plugins."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from uuid import UUID

from artana_evidence_api.source_registry import (
    direct_search_source_keys,
    normalize_source_key,
)
from artana_evidence_api.source_route_alphafold import alphafold_typed_route_plugin
from artana_evidence_api.source_route_clinical_trials import (
    clinical_trials_typed_route_plugin,
)
from artana_evidence_api.source_route_clinvar import clinvar_typed_route_plugin
from artana_evidence_api.source_route_contracts import (
    DirectSourceRouteDependencies,
    DirectSourceRoutePlugin,
    RouteEndpoint,
)
from artana_evidence_api.source_route_drugbank import drugbank_typed_route_plugin
from artana_evidence_api.source_route_marrvel import marrvel_typed_route_plugin
from artana_evidence_api.source_route_mgi import mgi_typed_route_plugin
from artana_evidence_api.source_route_pubmed import pubmed_typed_route_plugin
from artana_evidence_api.source_route_uniprot import uniprot_typed_route_plugin
from artana_evidence_api.source_route_zfin import zfin_typed_route_plugin
from artana_evidence_api.source_routes.gnomad import gnomad_typed_route_plugin
from artana_evidence_api.source_routes.orphanet import orphanet_typed_route_plugin
from artana_evidence_api.types.common import JSONObject
from fastapi import APIRouter

RouteKey = tuple[str, str]
RouteEndpointMap = Mapping[RouteKey, RouteEndpoint]


class DirectSourceRoutePluginRegistryError(LookupError):
    """Raised when no public route plugin exists for a direct-search source."""


_DIRECT_SOURCE_ROUTE_PLUGINS = (
    pubmed_typed_route_plugin(),
    marrvel_typed_route_plugin(),
    clinvar_typed_route_plugin(),
    drugbank_typed_route_plugin(),
    alphafold_typed_route_plugin(),
    gnomad_typed_route_plugin(),
    uniprot_typed_route_plugin(),
    clinical_trials_typed_route_plugin(),
    mgi_typed_route_plugin(),
    zfin_typed_route_plugin(),
    orphanet_typed_route_plugin(),
)


def direct_source_route_plugins() -> tuple[DirectSourceRoutePlugin, ...]:
    """Return public route plugins for direct-search sources."""

    validate_direct_source_route_plugins()
    return _DIRECT_SOURCE_ROUTE_PLUGINS


def direct_source_route_plugin_keys() -> tuple[str, ...]:
    """Return source keys supported by the public source-route plugin layer."""

    return tuple(plugin.source_key for plugin in direct_source_route_plugins())


def require_direct_source_route_plugin(source_key: str) -> DirectSourceRoutePlugin:
    """Return the public route plugin for a direct-search source key."""

    validate_direct_source_route_plugins()
    normalized_source_key = normalize_source_key(source_key)
    for plugin in _DIRECT_SOURCE_ROUTE_PLUGINS:
        if plugin.source_key == normalized_source_key:
            return plugin
    msg = f"Direct source route plugin is not registered for '{source_key}'."
    raise DirectSourceRoutePluginRegistryError(msg)


async def create_direct_source_search_payload(
    *,
    source_key: str,
    space_id: UUID,
    request_payload: JSONObject,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Create one direct-source search through the registered route plugin."""

    plugin = require_direct_source_route_plugin(source_key)
    return await plugin.create(
        space_id=space_id,
        request_payload=request_payload,
        dependencies=dependencies,
    )


def get_direct_source_search_payload(
    *,
    source_key: str,
    space_id: UUID,
    search_id: UUID,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Return one direct-source search through the registered route plugin."""

    plugin = require_direct_source_route_plugin(source_key)
    return plugin.get(
        space_id=space_id,
        search_id=search_id,
        dependencies=dependencies,
    )


def direct_source_typed_route_endpoint_map() -> RouteEndpointMap:
    """Return typed direct-source route endpoint expectations for tests."""

    endpoints: dict[RouteKey, RouteEndpoint] = {}
    for plugin in direct_source_route_plugins():
        for route in plugin.routes:
            endpoints[(route.path, route.method)] = route.endpoint
    return MappingProxyType(endpoints)


def register_direct_source_typed_routes(router: APIRouter) -> None:
    """Register typed public routes for all direct-search sources."""

    for plugin in direct_source_route_plugins():
        plugin.register(router)


def validate_direct_source_route_plugins() -> None:
    """Fail when direct-source route plugins drift from source registry order."""

    # The order is load-bearing for readable OpenAPI output and keeps typed
    # source routes registered before their generic source-key fallback.
    plugin_keys = tuple(plugin.source_key for plugin in _DIRECT_SOURCE_ROUTE_PLUGINS)
    source_keys = direct_search_source_keys()
    if plugin_keys == source_keys:
        return
    msg = "Direct source route plugins do not match direct-search source order."
    raise RuntimeError(msg)


__all__ = [
    "DirectSourceRoutePluginRegistryError",
    "create_direct_source_search_payload",
    "direct_source_route_plugin_keys",
    "direct_source_route_plugins",
    "direct_source_typed_route_endpoint_map",
    "get_direct_source_search_payload",
    "register_direct_source_typed_routes",
    "require_direct_source_route_plugin",
    "validate_direct_source_route_plugins",
]
