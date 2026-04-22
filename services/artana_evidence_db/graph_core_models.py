"""Service-local core graph domain entities."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from artana_evidence_db.common_types import JSONObject, JSONValue
from pydantic import BaseModel, ConfigDict, Field


class KernelEntity(BaseModel):
    """Domain representation of a kernel entity (graph node)."""

    model_config = ConfigDict(
        from_attributes=True,
        frozen=True,
        populate_by_name=True,
    )

    id: UUID
    research_space_id: UUID
    entity_type: str = Field(..., min_length=1, max_length=64)
    display_label: str | None = Field(None, max_length=512)
    aliases: list[str] = Field(default_factory=list)
    metadata: JSONObject = Field(default_factory=dict, alias="metadata_payload")
    created_at: datetime
    updated_at: datetime


class KernelEntityAlias(BaseModel):
    """Domain representation of one normalized alias attached to an entity."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: int
    entity_id: UUID
    research_space_id: UUID
    entity_type: str = Field(..., min_length=1, max_length=64)
    alias_label: str = Field(..., min_length=1, max_length=512)
    alias_normalized: str = Field(..., min_length=1, max_length=512)
    source: str | None = Field(None, max_length=64)
    review_status: str = Field(..., min_length=1, max_length=32)
    is_active: bool
    created_at: datetime
    updated_at: datetime


class KernelEntityIdentifier(BaseModel):
    """Domain representation of an identifier attached to a kernel entity."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: int
    entity_id: UUID
    namespace: str = Field(..., min_length=1, max_length=64)
    identifier_value: str = Field(..., min_length=1, max_length=512)
    identifier_blind_index: str | None = Field(None, max_length=64)
    encryption_key_version: str | None = Field(None, max_length=32)
    blind_index_version: str | None = Field(None, max_length=32)
    sensitivity: str = Field(..., min_length=1, max_length=32)
    created_at: datetime
    updated_at: datetime


class KernelObservation(BaseModel):
    """Domain representation of a kernel observation (typed fact)."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    research_space_id: UUID
    subject_id: UUID
    variable_id: str = Field(..., min_length=1, max_length=64)
    value_numeric: float | None = None
    value_text: str | None = None
    value_date: datetime | None = None
    value_coded: str | None = None
    value_boolean: bool | None = None
    value_json: JSONValue | None = None
    unit: str | None = Field(None, max_length=64)
    observed_at: datetime | None = None
    provenance_id: UUID | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime
    updated_at: datetime


class KernelProvenanceRecord(BaseModel):
    """Domain representation of a kernel provenance record."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    research_space_id: UUID
    source_type: str = Field(..., min_length=1, max_length=64)
    source_ref: str | None = Field(None, max_length=1024)
    extraction_run_id: str | None = Field(default=None, max_length=255)
    mapping_method: str | None = Field(None, max_length=64)
    mapping_confidence: float | None = Field(None, ge=0.0, le=1.0)
    agent_model: str | None = Field(None, max_length=128)
    raw_input: JSONObject | None = None
    created_at: datetime
    updated_at: datetime | None = None


EvidenceSentenceSource = Literal["verbatim_span", "artana_generated"]
EvidenceSentenceConfidence = Literal["low", "medium", "high"]
EvidenceSentenceHarnessOutcome = Literal["generated", "failed"]


class KernelRelation(BaseModel):
    """Domain representation of a kernel relation (graph edge)."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    research_space_id: UUID
    source_id: UUID
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_id: UUID
    aggregate_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_count: int = Field(default=0, ge=0)
    highest_evidence_tier: str | None = Field(None, max_length=32)
    support_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    refute_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    distinct_source_family_count: int = Field(default=0, ge=0)
    canonicalization_fingerprint: str = Field(default="", max_length=128)
    curation_status: str = Field(default="DRAFT", min_length=1, max_length=32)
    provenance_id: UUID | None = None
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class KernelReachabilityGap(BaseModel):
    """One pair (seed, target) reachable via multi-hop paths but with no direct edge.

    Surfaced by Phase 4 gap analysis: ``target_entity_id`` is reachable from
    ``seed_entity_id`` via at least one path of length ``min_path_length`` (>= 2),
    but no canonical relation exists directly between them.  Each row also
    carries an optional ``bridge_entity_id`` — a sample intermediate node on
    one of the paths — so the caller can immediately drill into the chain.
    """

    model_config = ConfigDict(frozen=True)

    seed_entity_id: UUID
    target_entity_id: UUID
    min_path_length: int = Field(..., ge=2)
    bridge_entity_id: UUID | None = None


class KernelMechanisticGap(BaseModel):
    """A direct relation that lacks an N-hop bridge through mechanism entities.

    Inverse of :class:`KernelReachabilityGap`: a direct canonical relation
    exists between ``source_entity_id`` and ``target_entity_id``, but no
    path of length 2..``max_hops`` whose intermediate nodes are of an
    "explanatory" type (BIOLOGICAL_PROCESS, SIGNALING_PATHWAY,
    MOLECULAR_FUNCTION, PROTEIN_DOMAIN, ...) connects the endpoints.  These
    rows answer "what gene-disease associations lack a mechanistic
    explanation?".

    The optional ``source_intermediate_count`` and ``target_intermediate_count``
    fields report how many mechanism-typed neighbors each endpoint has —
    useful for ranking gaps where one side has a partial explanation.

    When a bridge path *is* found (mainly for introspection and debugging;
    gaps are defined by the *absence* of a bridge), ``bridge_path`` carries
    the ordered list of intermediate entity IDs walking from source to
    target.  ``bridge_entity_id`` is kept for backward compatibility and
    equals ``bridge_path[0]`` when populated.
    """

    model_config = ConfigDict(frozen=True)

    relation_id: UUID
    source_entity_id: UUID
    target_entity_id: UUID
    relation_type: str = Field(..., min_length=1, max_length=64)
    source_intermediate_count: int = Field(default=0, ge=0)
    target_intermediate_count: int = Field(default=0, ge=0)
    bridge_entity_id: UUID | None = None
    bridge_path: list[UUID] | None = None


class KernelRelationEvidence(BaseModel):
    """Domain representation of one supporting evidence row for a relation."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    relation_id: UUID
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_summary: str | None = None
    evidence_sentence: str | None = None
    evidence_sentence_source: EvidenceSentenceSource | None = None
    evidence_sentence_confidence: EvidenceSentenceConfidence | None = None
    evidence_sentence_rationale: str | None = None
    evidence_tier: str = Field(..., min_length=1, max_length=32)
    provenance_id: UUID | None = None
    source_document_id: UUID | None = None
    source_document_ref: str | None = Field(default=None, max_length=512)
    agent_run_id: str | None = Field(default=None, max_length=255)
    created_at: datetime


class RelationEvidenceWrite(BaseModel):
    """Write payload for one derived canonical relation-evidence cache row."""

    model_config = ConfigDict(frozen=True)

    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_summary: str | None = None
    evidence_sentence: str | None = None
    evidence_sentence_source: EvidenceSentenceSource | None = None
    evidence_sentence_confidence: EvidenceSentenceConfidence | None = None
    evidence_sentence_rationale: str | None = None
    evidence_tier: str = Field(default="COMPUTATIONAL", min_length=1, max_length=32)
    provenance_id: UUID | None = None
    source_document_id: UUID | None = None
    source_document_ref: str | None = Field(default=None, max_length=512)
    agent_run_id: str | None = Field(default=None, max_length=255)


class EvidenceSentenceGenerationRequest(BaseModel):
    """Input payload for optional AI evidence-sentence generation."""

    model_config = ConfigDict(frozen=True)

    research_space_id: str = Field(..., min_length=1)
    source_type: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=128)
    source_label: str | None = None
    target_label: str | None = None
    evidence_summary: str = Field(..., min_length=1, max_length=2000)
    evidence_excerpt: str | None = None
    evidence_locator: str | None = None
    document_text: str | None = None
    document_id: str | None = None
    run_id: str | None = None
    metadata: JSONObject = Field(default_factory=dict)


class EvidenceSentenceGenerationResult(BaseModel):
    """Normalized result for evidence-sentence generation harness."""

    model_config = ConfigDict(frozen=True)

    outcome: EvidenceSentenceHarnessOutcome
    sentence: str | None = None
    source: EvidenceSentenceSource | None = None
    confidence: EvidenceSentenceConfidence | None = None
    rationale: str | None = None
    failure_reason: str | None = None
    metadata: JSONObject = Field(default_factory=dict)


__all__ = [
    "EvidenceSentenceConfidence",
    "EvidenceSentenceGenerationRequest",
    "EvidenceSentenceGenerationResult",
    "EvidenceSentenceHarnessOutcome",
    "EvidenceSentenceSource",
    "KernelEntity",
    "KernelEntityAlias",
    "KernelEntityIdentifier",
    "KernelMechanisticGap",
    "KernelObservation",
    "KernelProvenanceRecord",
    "KernelReachabilityGap",
    "KernelRelation",
    "KernelRelationEvidence",
    "RelationEvidenceWrite",
]
