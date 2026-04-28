"""HGNC authority-source plugin."""

from __future__ import annotations

from dataclasses import dataclass

from artana_evidence_api.source_plugins.authority.base import (
    AuthoritySourceConfig,
    StaticAuthoritySourcePlugin,
)
from artana_evidence_api.source_registry import SourceCapability, SourceDefinition

_SOURCE_DEFINITION = SourceDefinition(
    source_key="hgnc",
    display_name="HGNC",
    description="Gene nomenclature and alias grounding.",
    source_family="ontology",
    capabilities=(SourceCapability.ENRICHMENT, SourceCapability.RESEARCH_PLAN),
    direct_search_enabled=False,
    research_plan_enabled=True,
    default_research_plan_enabled=False,
    live_network_required=True,
    requires_credentials=False,
    result_capture="HGNC aliases enrich gene source context.",
    proposal_flow="Gene alias grounding supports later extraction and review.",
)

_CONFIG = AuthoritySourceConfig(
    definition=_SOURCE_DEFINITION,
    entity_kind="gene",
    id_fields=("hgnc_id", "hgnc_curie", "id", "normalized_id"),
    alias_fields=("aliases", "alias_symbols", "previous_symbols"),
    label_fields=("symbol", "label", "name", "gene_symbol"),
    unresolved_limitation=(
        "Unresolved HGNC symbols must not be treated as grounded gene evidence."
    ),
    ambiguous_limitation="Ambiguous HGNC symbols require review before use.",
    resolved_limitation=(
        "HGNC grounding normalizes gene identity but is not functional evidence "
        "by itself."
    ),
)


@dataclass(frozen=True, slots=True)
class HgncAuthorityPlugin(StaticAuthoritySourcePlugin):
    """Source-owned behavior for HGNC grounding."""

    config: AuthoritySourceConfig = _CONFIG

    def normalize_identifier(self, identifier: str) -> str:
        """Return a normalized HGNC CURIE or gene symbol."""

        normalized = StaticAuthoritySourcePlugin.normalize_identifier(
            self,
            identifier,
        ).replace("_", ":")
        if normalized.casefold().startswith("hgnc:"):
            prefix, value = normalized.split(":", 1)
            return f"{prefix.upper()}:{value}"
        if normalized.isdigit():
            return f"HGNC:{normalized}"
        return normalized.upper()


HGNC_AUTHORITY_PLUGIN = HgncAuthorityPlugin()

__all__ = ["HGNC_AUTHORITY_PLUGIN", "HgncAuthorityPlugin"]
