"""Plugin-backed compatibility helpers for evidence-selection query planning."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from artana_evidence_api.source_plugins.contracts import (
    EvidenceSourcePlugin,
    SourcePluginPlanningError,
)
from artana_evidence_api.source_plugins.registry import source_plugin, source_plugins
from artana_evidence_api.source_registry import normalize_source_key
from artana_evidence_api.types.common import JSONObject


class SourceQueryPlanningError(ValueError):
    """Raised when a source playbook cannot build a valid query payload."""


class SourceQueryIntent(Protocol):
    """Normalized intent fields consumed by source-query playbooks."""

    source_key: str
    query: str | None
    gene_symbol: str | None
    variant_hgvs: str | None
    protein_variant: str | None
    uniprot_id: str | None
    drug_name: str | None
    drugbank_id: str | None
    disease: str | None
    phenotype: str | None
    organism: str | None
    taxon_id: int | None
    panels: list[str] | None


@dataclass(frozen=True, slots=True)
class SourceQueryPlaybook:
    """Compatibility facade for plugin-owned query planning."""

    source_key: str
    supported_objective_intents: tuple[str, ...]
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    result_interpretation_hints: tuple[str, ...]
    handoff_eligible: bool
    non_goals: tuple[str, ...]
    build_query_payload: Callable[[SourceQueryIntent], JSONObject]

    def build_payload(self, intent: SourceQueryIntent) -> JSONObject:
        """Build and validate the direct-source query payload for one intent."""

        return self.build_query_payload(intent)


def adapter_source_query_playbook(source_key: str) -> SourceQueryPlaybook | None:
    """Return the plugin-backed source-query playbook for a source key."""

    plugin = source_plugin(normalize_source_key(source_key))
    if plugin is None:
        return None
    return _playbook_from_plugin(plugin)


def adapter_source_query_playbooks() -> tuple[SourceQueryPlaybook, ...]:
    """Return plugin-backed source-query playbooks in registry order."""

    return tuple(_playbook_from_plugin(plugin) for plugin in source_plugins())


def adapter_query_payload_for_intent(intent: SourceQueryIntent) -> JSONObject:
    """Build an executable direct-source query payload for a normalized intent."""

    playbook = adapter_source_query_playbook(intent.source_key)
    if playbook is None:
        source_key = normalize_source_key(intent.source_key)
        msg = f"Model planner cannot build query payload for source '{source_key}'."
        raise SourceQueryPlanningError(msg)
    try:
        return playbook.build_payload(intent)
    except SourcePluginPlanningError as exc:
        raise SourceQueryPlanningError(str(exc)) from exc


def _playbook_from_plugin(plugin: EvidenceSourcePlugin) -> SourceQueryPlaybook:
    return SourceQueryPlaybook(
        source_key=plugin.source_key,
        supported_objective_intents=plugin.supported_objective_intents,
        required_fields=(),
        optional_fields=(),
        result_interpretation_hints=plugin.result_interpretation_hints,
        handoff_eligible=plugin.handoff_eligible,
        non_goals=plugin.non_goals,
        build_query_payload=plugin.build_query_payload,
    )


__all__ = [
    "SourceQueryIntent",
    "SourceQueryPlaybook",
    "SourceQueryPlanningError",
    "adapter_query_payload_for_intent",
    "adapter_source_query_playbook",
    "adapter_source_query_playbooks",
]
