"""Plugin-backed compatibility helpers for evidence-selection review staging."""

from __future__ import annotations

from dataclasses import dataclass

from artana_evidence_api.source_plugins.registry import source_plugin
from artana_evidence_api.types.common import JSONObject


@dataclass(frozen=True, slots=True)
class EvidenceSelectionExtractionPolicy:
    """Compatibility facade for plugin-owned extraction/review policy."""

    source_key: str
    proposal_type: str
    review_type: str
    evidence_role: str
    limitations: tuple[str, ...]
    normalized_fields: tuple[str, ...]


def adapter_extraction_policy_for_source(
    source_key: str,
) -> EvidenceSelectionExtractionPolicy:
    """Return the plugin-backed staging policy for a selected source record."""

    plugin = source_plugin(source_key)
    if plugin is None:
        msg = f"No evidence-selection extraction policy is defined for '{source_key}'."
        raise KeyError(msg)
    policy = plugin.review_policy
    return EvidenceSelectionExtractionPolicy(
        source_key=policy.source_key,
        proposal_type=policy.proposal_type,
        review_type=policy.review_type,
        evidence_role=policy.evidence_role,
        limitations=policy.limitations,
        normalized_fields=policy.normalized_fields,
    )


def adapter_normalized_extraction_payload(
    *,
    source_key: str,
    record: JSONObject,
) -> JSONObject:
    """Return source-specific normalized fields for reviewer-facing extraction."""

    plugin = source_plugin(source_key)
    if plugin is None:
        msg = f"No evidence-selection extraction policy is defined for '{source_key}'."
        raise KeyError(msg)
    return plugin.normalized_extraction_payload(record)


def adapter_proposal_summary(*, source_key: str, selection_reason: str) -> str:
    """Return a source-specific proposal summary."""

    plugin = source_plugin(source_key)
    if plugin is None:
        msg = f"No evidence-selection extraction policy is defined for '{source_key}'."
        raise KeyError(msg)
    return plugin.proposal_summary(selection_reason)


def adapter_review_item_summary(*, source_key: str, selection_reason: str) -> str:
    """Return a source-specific review item summary."""

    plugin = source_plugin(source_key)
    if plugin is None:
        msg = f"No evidence-selection extraction policy is defined for '{source_key}'."
        raise KeyError(msg)
    return plugin.review_item_summary(selection_reason)


__all__ = [
    "EvidenceSelectionExtractionPolicy",
    "adapter_extraction_policy_for_source",
    "adapter_normalized_extraction_payload",
    "adapter_proposal_summary",
    "adapter_review_item_summary",
]
