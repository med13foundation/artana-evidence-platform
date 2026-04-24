"""Qualitative confidence helpers for graph-write requests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from artana_evidence_api.types.common import JSONObject, JSONValue
from artana_evidence_api.types.graph_fact_assessment import (
    FactAssessment,
    GroundingLevel,
    MappingStatus,
    SpeculationLevel,
    SupportBand,
    assessment_confidence,
)


class HarnessProposalAssessmentSource(Protocol):
    """Minimal proposal surface needed to derive a graph-write assessment."""

    @property
    def source_kind(self) -> str: ...

    @property
    def source_key(self) -> str: ...

    @property
    def title(self) -> str: ...

    @property
    def summary(self) -> str: ...

    @property
    def reasoning_path(self) -> JSONObject: ...

    @property
    def evidence_bundle(self) -> list[JSONObject]: ...

    @property
    def payload(self) -> JSONObject: ...

    @property
    def metadata(self) -> JSONObject: ...


_FACTUAL_SUPPORT_BANDS: dict[str, SupportBand] = {
    "strong": SupportBand.STRONG,
    "moderate": SupportBand.SUPPORTED,
    "tentative": SupportBand.TENTATIVE,
    "unsupported": SupportBand.INSUFFICIENT,
}

_STRUCTURED_SOURCE_KINDS = frozenset(
    {
        "clinvar_enrichment",
        "clinicaltrials_enrichment",
        "marrvel_enrichment",
        "mgi_enrichment",
        "zfin_enrichment",
        "research_bootstrap",
    },
)

_INFERENCE_SOURCE_KINDS = frozenset(
    {
        "chat_graph_write",
        "continuous_learning",
        "hypothesis_generation",
        "mechanism_discovery",
    },
)
_MIN_STRONG_CHAT_EVIDENCE_COUNT = 2


def assessment_confidence_metadata(assessment: FactAssessment) -> JSONObject:
    """Return stable metadata explaining how confidence was derived."""
    derived_confidence = assessment_confidence(assessment)
    return {
        "assessment": fact_assessment_payload(assessment),
        "confidence_derivation": {
            "method": "qualitative_assessment_v1",
            "derived_confidence": derived_confidence,
        },
    }


def fact_assessment_payload(assessment: FactAssessment) -> JSONObject:
    """Serialize a fact assessment without relying on untyped model_dump output."""
    return {
        "support_band": str(assessment.support_band),
        "grounding_level": str(assessment.grounding_level),
        "mapping_status": str(assessment.mapping_status),
        "speculation_level": str(assessment.speculation_level),
        "confidence_rationale": assessment.confidence_rationale,
    }


def proposal_fact_assessment(
    proposal: HarnessProposalAssessmentSource,
) -> FactAssessment:
    """Derive the graph-write assessment for a staged proposal."""
    explicit_assessment = _coerce_fact_assessment(proposal.metadata.get("assessment"))
    if explicit_assessment is not None:
        return explicit_assessment

    explicit_assessment = _coerce_fact_assessment(
        proposal.reasoning_path.get("assessment"),
    )
    if explicit_assessment is not None:
        return explicit_assessment

    proposal_review = proposal.metadata.get("proposal_review")
    if isinstance(proposal_review, Mapping):
        review_assessment = _assessment_from_proposal_review(
            proposal=proposal,
            proposal_review=proposal_review,
        )
        if review_assessment is not None:
            return review_assessment

    return _assessment_from_proposal_source_kind(proposal)


def chat_graph_write_fact_assessment(
    *,
    selected_evidence_count: int,
    rationale: str,
) -> FactAssessment:
    """Build the qualitative assessment for chat-derived graph writes."""
    support_band = (
        SupportBand.STRONG
        if selected_evidence_count >= _MIN_STRONG_CHAT_EVIDENCE_COUNT
        else SupportBand.SUPPORTED
    )
    return FactAssessment(
        support_band=support_band,
        grounding_level=GroundingLevel.GRAPH_INFERENCE,
        mapping_status=MappingStatus.RESOLVED,
        speculation_level=SpeculationLevel.DIRECT,
        confidence_rationale=(
            rationale.strip()
            if rationale.strip()
            else "Selected graph-chat evidence directly supports this graph write."
        ),
    )


def _assessment_from_proposal_review(
    *,
    proposal: HarnessProposalAssessmentSource,
    proposal_review: Mapping[str, object],
) -> FactAssessment | None:
    factual_support = _string_mapping_value(proposal_review, "factual_support")
    if factual_support is None:
        return None
    support_band = _FACTUAL_SUPPORT_BANDS.get(factual_support.strip().lower())
    if support_band is None:
        return None
    factual_rationale = _string_mapping_value(proposal_review, "factual_rationale")
    review_rationale = _string_mapping_value(proposal_review, "rationale")
    return FactAssessment(
        support_band=support_band,
        grounding_level=GroundingLevel.SPAN,
        mapping_status=_proposal_mapping_status(proposal),
        speculation_level=_proposal_speculation_level(proposal),
        confidence_rationale=(
            factual_rationale
            or review_rationale
            or "Document proposal review supplied qualitative factual support."
        ),
    )


def _assessment_from_proposal_source_kind(
    proposal: HarnessProposalAssessmentSource,
) -> FactAssessment:
    source_kind = proposal.source_kind.strip().lower()
    if source_kind in _STRUCTURED_SOURCE_KINDS:
        support_band = _structured_source_support_band(proposal)
        grounding_level = GroundingLevel.SPAN
        speculation_level = SpeculationLevel.DIRECT
        rationale = (
            "Structured source evidence supplied a categorical assertion for this "
            "proposal."
        )
    elif source_kind in _INFERENCE_SOURCE_KINDS:
        support_band = SupportBand.TENTATIVE
        grounding_level = GroundingLevel.GRAPH_INFERENCE
        speculation_level = SpeculationLevel.HEDGED
        rationale = (
            "Graph-inference proposal requires curator review before it is treated "
            "as directly supported."
        )
    else:
        support_band = SupportBand.TENTATIVE
        grounding_level = (
            GroundingLevel.SPAN if proposal.evidence_bundle else GroundingLevel.DOCUMENT
        )
        speculation_level = SpeculationLevel.HEDGED
        rationale = "Proposal did not include a source-specific qualitative review."

    return FactAssessment(
        support_band=support_band,
        grounding_level=grounding_level,
        mapping_status=_proposal_mapping_status(proposal),
        speculation_level=speculation_level,
        confidence_rationale=rationale,
    )


def _structured_source_support_band(
    proposal: HarnessProposalAssessmentSource,
) -> SupportBand:
    clinical_significance = _string_mapping_value(
        proposal.metadata,
        "clinical_significance",
    ) or _string_mapping_value(proposal.payload, "clinical_significance")
    if clinical_significance is not None:
        normalized = clinical_significance.lower()
        if "pathogenic" in normalized and "likely" not in normalized:
            return SupportBand.STRONG
        if "likely pathogenic" in normalized:
            return SupportBand.SUPPORTED
        if "uncertain" in normalized or "vus" in normalized:
            return SupportBand.TENTATIVE
    return SupportBand.SUPPORTED


def _proposal_mapping_status(
    proposal: HarnessProposalAssessmentSource,
) -> MappingStatus:
    subject_resolved = proposal.metadata.get("subject_resolved")
    object_resolved = proposal.metadata.get("object_resolved")
    if subject_resolved is False or object_resolved is False:
        return MappingStatus.AMBIGUOUS
    return MappingStatus.RESOLVED


def _proposal_speculation_level(
    proposal: HarnessProposalAssessmentSource,
) -> SpeculationLevel:
    relation_type = _string_mapping_value(proposal.payload, "proposed_claim_type")
    source_kind = proposal.source_kind.strip().lower()
    if source_kind in _INFERENCE_SOURCE_KINDS:
        return SpeculationLevel.HEDGED
    if relation_type is not None and "HYPOTH" in relation_type.upper():
        return SpeculationLevel.HYPOTHETICAL
    return SpeculationLevel.DIRECT


def _coerce_fact_assessment(raw_value: object) -> FactAssessment | None:
    if isinstance(raw_value, FactAssessment):
        return raw_value
    if not isinstance(raw_value, Mapping):
        return None
    payload = _normalize_mapping(raw_value)
    try:
        return FactAssessment.model_validate(payload)
    except ValueError:
        return None


def _normalize_mapping(raw_value: Mapping[object, object]) -> JSONObject:
    payload: JSONObject = {}
    for key, value in raw_value.items():
        if isinstance(key, str):
            payload[key] = _normalize_json_value(value)
    return payload


def _normalize_json_value(value: object) -> JSONValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return _normalize_mapping(value)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_normalize_json_value(item) for item in value]
    return str(value)


def _string_mapping_value(
    payload: Mapping[str, object],
    field_name: str,
) -> str | None:
    value = payload.get(field_name)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


__all__ = [
    "assessment_confidence_metadata",
    "chat_graph_write_fact_assessment",
    "fact_assessment_payload",
    "proposal_fact_assessment",
]
