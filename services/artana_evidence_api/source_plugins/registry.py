"""Explicit datasource plugin registry."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from functools import lru_cache

from artana_evidence_api.pubmed_discovery import PubMedDiscoveryService
from artana_evidence_api.source_enrichment_bridges import (
    MarrvelDiscoveryServiceProtocol,
)
from artana_evidence_api.source_plugins.alphafold import ALPHAFOLD_PLUGIN
from artana_evidence_api.source_plugins.authority.hgnc import HGNC_AUTHORITY_PLUGIN
from artana_evidence_api.source_plugins.authority.mondo import MONDO_AUTHORITY_PLUGIN
from artana_evidence_api.source_plugins.clinical_trials import CLINICAL_TRIALS_PLUGIN
from artana_evidence_api.source_plugins.clinvar import CLINVAR_PLUGIN
from artana_evidence_api.source_plugins.contracts import (
    AuthoritySourcePlugin,
    DocumentIngestionSourcePlugin,
    EvidenceSourcePlugin,
)
from artana_evidence_api.source_plugins.drugbank import DRUGBANK_PLUGIN
from artana_evidence_api.source_plugins.ingestion.pdf import PDF_INGESTION_PLUGIN
from artana_evidence_api.source_plugins.ingestion.text import TEXT_INGESTION_PLUGIN
from artana_evidence_api.source_plugins.marrvel import (
    MARRVEL_PLUGIN,
    build_marrvel_execution_plugin,
)
from artana_evidence_api.source_plugins.mgi import MGI_PLUGIN
from artana_evidence_api.source_plugins.pubmed import (
    PUBMED_PLUGIN,
    build_pubmed_execution_plugin,
)
from artana_evidence_api.source_plugins.uniprot import UNIPROT_PLUGIN
from artana_evidence_api.source_plugins.zfin import ZFIN_PLUGIN
from artana_evidence_api.source_registry import (
    SourceDefinition,
    normalize_source_key,
)

_SOURCE_PLUGINS: tuple[EvidenceSourcePlugin, ...] = (
    PUBMED_PLUGIN,
    MARRVEL_PLUGIN,
    CLINVAR_PLUGIN,
    DRUGBANK_PLUGIN,
    ALPHAFOLD_PLUGIN,
    UNIPROT_PLUGIN,
    CLINICAL_TRIALS_PLUGIN,
    MGI_PLUGIN,
    ZFIN_PLUGIN,
)

_AUTHORITY_SOURCE_PLUGINS: tuple[AuthoritySourcePlugin, ...] = (
    MONDO_AUTHORITY_PLUGIN,
    HGNC_AUTHORITY_PLUGIN,
)

_DOCUMENT_INGESTION_SOURCE_PLUGINS: tuple[DocumentIngestionSourcePlugin, ...] = (
    PDF_INGESTION_PLUGIN,
    TEXT_INGESTION_PLUGIN,
)

_PUBLIC_SOURCE_PLUGINS: tuple[
    EvidenceSourcePlugin | AuthoritySourcePlugin | DocumentIngestionSourcePlugin,
    ...,
] = (
    PUBMED_PLUGIN,
    MARRVEL_PLUGIN,
    CLINVAR_PLUGIN,
    MONDO_AUTHORITY_PLUGIN,
    PDF_INGESTION_PLUGIN,
    TEXT_INGESTION_PLUGIN,
    DRUGBANK_PLUGIN,
    ALPHAFOLD_PLUGIN,
    UNIPROT_PLUGIN,
    HGNC_AUTHORITY_PLUGIN,
    CLINICAL_TRIALS_PLUGIN,
    MGI_PLUGIN,
    ZFIN_PLUGIN,
)


SourceExecutionPluginBuilder = Callable[
    [
        Callable[[], AbstractContextManager[PubMedDiscoveryService]] | None,
        Callable[[], MarrvelDiscoveryServiceProtocol | None] | None,
    ],
    EvidenceSourcePlugin,
]

_SOURCE_EXECUTION_PLUGIN_FACTORIES = (
    (PUBMED_PLUGIN.source_key, build_pubmed_execution_plugin),
    (MARRVEL_PLUGIN.source_key, build_marrvel_execution_plugin),
)


def source_plugin(source_key: str) -> EvidenceSourcePlugin | None:
    """Return one source plugin by public or canonical source key."""

    return _source_plugins_by_key().get(normalize_source_key(source_key))


def require_source_plugin(source_key: str) -> EvidenceSourcePlugin:
    """Return one source plugin or raise a registry error."""

    plugin = source_plugin(source_key)
    if plugin is not None:
        return plugin
    msg = f"No source plugin is registered for '{source_key}'."
    raise KeyError(msg)


def source_plugins() -> tuple[EvidenceSourcePlugin, ...]:
    """Return explicitly registered source plugins in registry order."""

    return _validated_source_plugins()


def authority_source_plugin(source_key: str) -> AuthoritySourcePlugin | None:
    """Return one authority/grounding source plugin by public or canonical key."""

    return _authority_source_plugins_by_key().get(normalize_source_key(source_key))


def authority_source_plugins() -> tuple[AuthoritySourcePlugin, ...]:
    """Return authority/grounding source plugins in registry order."""

    return _validated_authority_source_plugins()


def authority_source_plugin_keys() -> tuple[str, ...]:
    """Return canonical source keys with authority/grounding plugins."""

    return tuple(plugin.source_key for plugin in _AUTHORITY_SOURCE_PLUGINS)


def document_ingestion_source_plugin(
    source_key: str,
) -> DocumentIngestionSourcePlugin | None:
    """Return one document-ingestion source plugin by public or canonical key."""

    return _document_ingestion_source_plugins_by_key().get(
        normalize_source_key(source_key),
    )


def document_ingestion_source_plugins() -> tuple[DocumentIngestionSourcePlugin, ...]:
    """Return document-ingestion source plugins in registry order."""

    return _validated_document_ingestion_source_plugins()


def document_ingestion_source_plugin_keys() -> tuple[str, ...]:
    """Return canonical source keys with document-ingestion plugins."""

    return tuple(plugin.source_key for plugin in _DOCUMENT_INGESTION_SOURCE_PLUGINS)


def evidence_source_plugin_keys() -> tuple[str, ...]:
    """Return all evidence-source plugin keys in public source-registry order."""

    return tuple(plugin.source_key for plugin in _PUBLIC_SOURCE_PLUGINS)


def public_source_definitions() -> tuple[SourceDefinition, ...]:
    """Return plugin-owned source definitions in public source-registry order."""

    validate_source_plugin_registry()
    return tuple(plugin.source_definition() for plugin in _PUBLIC_SOURCE_PLUGINS)


def source_plugin_for_execution(
    source_key: str,
    *,
    pubmed_discovery_service_factory: (
        Callable[[], AbstractContextManager[PubMedDiscoveryService]] | None
    ) = None,
    marrvel_discovery_service_factory: (
        Callable[[], MarrvelDiscoveryServiceProtocol | None] | None
    ) = None,
) -> EvidenceSourcePlugin | None:
    """Return a source plugin with runner-scoped execution dependencies."""

    normalized_source_key = normalize_source_key(source_key)
    for factory_source_key, build_execution_plugin in _SOURCE_EXECUTION_PLUGIN_FACTORIES:
        if factory_source_key == normalized_source_key:
            return build_execution_plugin(
                pubmed_discovery_service_factory,
                marrvel_discovery_service_factory,
            )
    return source_plugin(normalized_source_key)


def source_plugin_keys() -> tuple[str, ...]:
    """Return canonical source keys with source plugins."""

    return tuple(plugin.source_key for plugin in _SOURCE_PLUGINS)


def validate_source_plugin_registry() -> None:
    """Fail closed when plugin registration drifts internally."""

    _validate_plugin_group(
        plugins=_SOURCE_PLUGINS,
        group_name="direct-search",
        direct_search_expected=True,
    )
    _validate_plugin_group(
        plugins=_AUTHORITY_SOURCE_PLUGINS,
        group_name="authority",
        direct_search_expected=False,
    )
    _validate_plugin_group(
        plugins=_DOCUMENT_INGESTION_SOURCE_PLUGINS,
        group_name="document-ingestion",
        direct_search_expected=False,
    )
    _validate_research_plan_plugin_coverage()


def _validate_plugin_group(
    *,
    plugins: tuple[
        EvidenceSourcePlugin | AuthoritySourcePlugin | DocumentIngestionSourcePlugin,
        ...,
    ],
    group_name: str,
    direct_search_expected: bool,
) -> None:
    keys = tuple(plugin.source_key for plugin in plugins)
    if len(keys) != len(set(keys)):
        msg = f"{group_name} source plugin registry contains duplicate source keys."
        raise RuntimeError(msg)
    definition_keys = tuple(plugin.source_definition().source_key for plugin in plugins)
    if keys != definition_keys:
        msg = f"{group_name} source plugin registry keys do not match plugin definitions."
        raise RuntimeError(msg)
    metadata_keys = tuple(plugin.metadata.source_key for plugin in plugins)
    if keys != metadata_keys:
        msg = f"{group_name} source plugin registry keys do not match plugin metadata."
        raise RuntimeError(msg)
    for plugin in plugins:
        definition = plugin.source_definition()
        _validate_plugin_metadata(plugin=plugin, definition=definition)
        if plugin.direct_search_supported is not direct_search_expected:
            msg = (
                f"{group_name} plugin '{plugin.source_key}' direct-search support "
                "does not match registry group."
            )
            raise RuntimeError(msg)


def _validate_plugin_metadata(
    *,
    plugin: EvidenceSourcePlugin | AuthoritySourcePlugin | DocumentIngestionSourcePlugin,
    definition: SourceDefinition,
) -> None:
    expected = {
        "source_key": definition.source_key,
        "display_name": definition.display_name,
        "description": definition.description,
        "source_family": definition.source_family,
        "capabilities": tuple(capability.value for capability in definition.capabilities),
        "direct_search_supported": definition.direct_search_enabled,
        "research_plan_supported": definition.research_plan_enabled,
        "default_research_plan_enabled": definition.default_research_plan_enabled,
        "live_network_required": definition.live_network_required,
        "requires_credentials": definition.requires_credentials,
        "credential_names": definition.credential_names,
        "request_schema_ref": definition.request_schema_ref,
        "result_schema_ref": definition.result_schema_ref,
        "result_capture": definition.result_capture,
        "proposal_flow": definition.proposal_flow,
    }
    metadata = plugin.metadata
    for field_name, expected_value in expected.items():
        if getattr(metadata, field_name) == expected_value:
            continue
        msg = (
            f"Plugin metadata field '{field_name}' drifted for "
            f"'{plugin.source_key}'."
        )
        raise RuntimeError(msg)


def _validate_research_plan_plugin_coverage() -> None:
    registered_keys = (
        source_plugin_keys()
        + authority_source_plugin_keys()
        + document_ingestion_source_plugin_keys()
    )
    public_keys = tuple(plugin.source_key for plugin in _PUBLIC_SOURCE_PLUGINS)
    if set(public_keys) != set(registered_keys):
        msg = (
            "Public source plugin registry must contain exactly the registered "
            f"evidence-source plugins; expected {registered_keys}, got {public_keys}."
        )
        raise RuntimeError(msg)
    research_plan_keys = tuple(
        plugin.source_key
        for plugin in _PUBLIC_SOURCE_PLUGINS
        if plugin.source_definition().research_plan_enabled
    )
    if research_plan_keys == public_keys:
        return
    msg = (
        "Every public source plugin must support research-plan source "
        f"preferences; got {research_plan_keys} from {public_keys}."
    )
    raise RuntimeError(msg)


@lru_cache(maxsize=1)
def _validated_source_plugins() -> tuple[EvidenceSourcePlugin, ...]:
    validate_source_plugin_registry()
    return _SOURCE_PLUGINS


@lru_cache(maxsize=1)
def _validated_authority_source_plugins() -> tuple[AuthoritySourcePlugin, ...]:
    validate_source_plugin_registry()
    return _AUTHORITY_SOURCE_PLUGINS


@lru_cache(maxsize=1)
def _validated_document_ingestion_source_plugins() -> tuple[
    DocumentIngestionSourcePlugin,
    ...,
]:
    validate_source_plugin_registry()
    return _DOCUMENT_INGESTION_SOURCE_PLUGINS


@lru_cache(maxsize=1)
def _source_plugins_by_key() -> dict[str, EvidenceSourcePlugin]:
    return {plugin.source_key: plugin for plugin in _validated_source_plugins()}


@lru_cache(maxsize=1)
def _authority_source_plugins_by_key() -> dict[str, AuthoritySourcePlugin]:
    return {
        plugin.source_key: plugin
        for plugin in _validated_authority_source_plugins()
    }


@lru_cache(maxsize=1)
def _document_ingestion_source_plugins_by_key() -> dict[
    str,
    DocumentIngestionSourcePlugin,
]:
    return {
        plugin.source_key: plugin
        for plugin in _validated_document_ingestion_source_plugins()
    }


__all__ = [
    "authority_source_plugin",
    "authority_source_plugin_keys",
    "authority_source_plugins",
    "document_ingestion_source_plugin",
    "document_ingestion_source_plugin_keys",
    "document_ingestion_source_plugins",
    "evidence_source_plugin_keys",
    "public_source_definitions",
    "require_source_plugin",
    "source_plugin",
    "source_plugin_for_execution",
    "source_plugin_keys",
    "source_plugins",
    "validate_source_plugin_registry",
]
