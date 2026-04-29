"""MONDO authority-source plugin."""

from __future__ import annotations

from dataclasses import dataclass

from artana_evidence_api.source_plugins.authority.base import (
    AuthoritySourceConfig,
    StaticAuthoritySourcePlugin,
)
from artana_evidence_api.source_registry import SourceCapability, SourceDefinition

_SOURCE_DEFINITION = SourceDefinition(
    source_key="mondo",
    display_name="MONDO",
    description="Disease ontology grounding and concept expansion.",
    source_family="ontology",
    capabilities=(SourceCapability.ENRICHMENT, SourceCapability.RESEARCH_PLAN),
    direct_search_enabled=False,
    research_plan_enabled=True,
    default_research_plan_enabled=True,
    live_network_required=True,
    requires_credentials=False,
    result_capture="Ontology matches enrich source context and research state.",
    proposal_flow="Ontology-grounded concepts support later proposal review.",
)

_CONFIG = AuthoritySourceConfig(
    definition=_SOURCE_DEFINITION,
    entity_kind="disease",
    id_fields=("mondo_id", "mondo_curie", "id", "normalized_id"),
    alias_fields=("aliases", "synonyms", "exact_synonyms"),
    label_fields=("label", "name", "disease"),
    unresolved_limitation=(
        "Unresolved MONDO terms must not be treated as grounded disease evidence."
    ),
    ambiguous_limitation="Ambiguous MONDO matches require review before use.",
    resolved_limitation=(
        "MONDO grounding normalizes disease identity but is not clinical evidence "
        "by itself."
    ),
)


@dataclass(frozen=True, slots=True)
class MondoAuthorityPlugin(StaticAuthoritySourcePlugin):
    """Source-owned behavior for MONDO grounding."""

    config: AuthoritySourceConfig = _CONFIG

    def normalize_identifier(self, identifier: str) -> str:
        """Return a normalized MONDO CURIE."""

        normalized = StaticAuthoritySourcePlugin.normalize_identifier(
            self,
            identifier,
        ).replace("_", ":")
        if normalized.casefold().startswith("mondo:"):
            prefix, value = normalized.split(":", 1)
            return f"{prefix.upper()}:{value}"
        if normalized.isdigit():
            return f"MONDO:{normalized.zfill(7)}"
        return normalized


MONDO_AUTHORITY_PLUGIN = MondoAuthorityPlugin()

__all__ = ["MONDO_AUTHORITY_PLUGIN", "MondoAuthorityPlugin"]
