"""Declarative tool catalog for graph-harness transparency and execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date  # noqa: TC003
from typing import Literal

from artana_evidence_api.types.common import JSONObject
from artana_evidence_api.types.graph_contracts import DecisionConfidenceAssessment
from artana_evidence_api.types.graph_fact_assessment import FactAssessment
from pydantic import BaseModel, ConfigDict, Field


class GraphDocumentToolArgs(BaseModel):
    """Arguments for deterministic graph document reads."""

    model_config = ConfigDict(strict=True)

    space_id: str = Field(..., min_length=1, max_length=64)
    seed_entity_ids: list[str] = Field(default_factory=list)
    depth: int = Field(default=2, ge=0, le=6)
    top_k: int = Field(default=25, ge=1, le=250)


class ListGraphClaimsToolArgs(BaseModel):
    """Arguments for claim listing."""

    model_config = ConfigDict(strict=True)

    space_id: str = Field(..., min_length=1, max_length=64)
    claim_status: str | None = Field(default=None, max_length=64)
    limit: int = Field(default=50, ge=1, le=500)


class ListGraphHypothesesToolArgs(BaseModel):
    """Arguments for manual/generated hypothesis listing."""

    model_config = ConfigDict(strict=True)

    space_id: str = Field(..., min_length=1, max_length=64)
    limit: int = Field(default=50, ge=1, le=500)


class SuggestRelationsToolArgs(BaseModel):
    """Arguments for relation suggestion."""

    model_config = ConfigDict(strict=True)

    space_id: str = Field(..., min_length=1, max_length=64)
    source_entity_ids: list[str] = Field(..., min_length=1)
    allowed_relation_types: list[str] | None = None
    target_entity_types: list[str] | None = None
    limit_per_source: int = Field(default=5, ge=1, le=25)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class CaptureGraphSnapshotToolArgs(BaseModel):
    """Arguments for graph snapshot capture."""

    model_config = ConfigDict(strict=True)

    space_id: str = Field(..., min_length=1, max_length=64)
    seed_entity_ids: list[str] = Field(default_factory=list)
    depth: int = Field(default=2, ge=0, le=6)
    top_k: int = Field(default=25, ge=1, le=250)


class RunPubMedSearchToolArgs(BaseModel):
    """Arguments for PubMed discovery."""

    model_config = ConfigDict(strict=True)

    search_term: str = Field(..., min_length=1, max_length=4000)
    gene_symbol: str | None = Field(default=None, max_length=255)
    additional_terms: str | None = Field(default=None, max_length=4000)
    date_from: date | None = None
    date_to: date | None = None
    max_results: int = Field(default=25, ge=1, le=200)


class RunMarrvelSearchToolArgs(BaseModel):
    """Arguments for MARRVEL gene discovery."""

    model_config = ConfigDict(strict=True)

    gene_symbol: str = Field(..., min_length=1, max_length=255)
    panels: list[str] | None = Field(
        default=None,
        description=(
            "Subset of MARRVEL panels to query (e.g. ['omim', 'clinvar']). "
            "Defaults to all supported panels."
        ),
    )
    taxon_id: int = Field(default=9606, ge=1)


class ListReasoningPathsToolArgs(BaseModel):
    """Arguments for reasoning-path listing."""

    model_config = ConfigDict(strict=True)

    space_id: str = Field(..., min_length=1, max_length=64)
    start_entity_id: str | None = Field(default=None, max_length=64)
    end_entity_id: str | None = Field(default=None, max_length=64)
    status: str | None = Field(default=None, max_length=64)
    path_kind: str | None = Field(default=None, max_length=64)
    offset: int = Field(default=0, ge=0, le=5000)
    limit: int = Field(default=50, ge=1, le=500)


class GetReasoningPathToolArgs(BaseModel):
    """Arguments for reasoning-path detail reads."""

    model_config = ConfigDict(strict=True)

    space_id: str = Field(..., min_length=1, max_length=64)
    path_id: str = Field(..., min_length=1, max_length=64)


class ListClaimsByEntityToolArgs(BaseModel):
    """Arguments for related-claim listing."""

    model_config = ConfigDict(strict=True)

    space_id: str = Field(..., min_length=1, max_length=64)
    entity_id: str = Field(..., min_length=1, max_length=64)
    offset: int = Field(default=0, ge=0, le=5000)
    limit: int = Field(default=50, ge=1, le=500)


class ListClaimParticipantsToolArgs(BaseModel):
    """Arguments for claim participant reads."""

    model_config = ConfigDict(strict=True)

    space_id: str = Field(..., min_length=1, max_length=64)
    claim_id: str = Field(..., min_length=1, max_length=64)


class ListClaimEvidenceToolArgs(BaseModel):
    """Arguments for claim evidence reads."""

    model_config = ConfigDict(strict=True)

    space_id: str = Field(..., min_length=1, max_length=64)
    claim_id: str = Field(..., min_length=1, max_length=64)


class ListRelationConflictsToolArgs(BaseModel):
    """Arguments for conflict listing."""

    model_config = ConfigDict(strict=True)

    space_id: str = Field(..., min_length=1, max_length=64)
    offset: int = Field(default=0, ge=0, le=5000)
    limit: int = Field(default=50, ge=1, le=500)


class CreateGraphClaimToolArgs(BaseModel):
    """Arguments for governed graph-claim creation."""

    model_config = ConfigDict(strict=True)

    space_id: str = Field(..., min_length=1, max_length=64)
    source_entity_id: str = Field(..., min_length=1, max_length=64)
    target_entity_id: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=128)
    claim_text: str = Field(..., min_length=1, max_length=8000)
    source_document_ref: str = Field(..., min_length=1, max_length=512)
    assessment: FactAssessment
    evidence_summary: str = Field(..., min_length=1, max_length=8000)


class CreateManualHypothesisToolArgs(BaseModel):
    """Arguments for manual hypothesis creation."""

    model_config = ConfigDict(strict=True)

    space_id: str = Field(..., min_length=1, max_length=64)
    statement: str = Field(..., min_length=1, max_length=8000)
    rationale: str = Field(..., min_length=1, max_length=8000)
    seed_entity_ids: list[str] = Field(..., min_length=1)
    source_type: str = Field(..., min_length=1, max_length=128)


class ConceptExternalRefToolArgs(BaseModel):
    """External identifier for an AI Full Mode concept proposal."""

    model_config = ConfigDict(strict=True)

    namespace: str = Field(..., min_length=1, max_length=128)
    identifier: str = Field(..., min_length=1, max_length=255)


class ProposeGraphConceptToolArgs(BaseModel):
    """Arguments for proposing one governed graph concept."""

    model_config = ConfigDict(strict=True)

    space_id: str = Field(..., min_length=1, max_length=64)
    domain_context: str = Field(default="general", min_length=1, max_length=64)
    entity_type: str = Field(..., min_length=1, max_length=64)
    canonical_label: str = Field(..., min_length=1, max_length=255)
    synonyms: list[str] = Field(default_factory=list)
    external_refs: list[ConceptExternalRefToolArgs] = Field(default_factory=list)
    evidence_payload: JSONObject = Field(default_factory=dict)
    rationale: str | None = Field(default=None, max_length=4000)
    source_ref: str | None = Field(default=None, max_length=1024)


class GraphChangeConceptToolArgs(BaseModel):
    """Local concept inside an AI Full Mode graph-change proposal."""

    model_config = ConfigDict(strict=True)

    local_id: str = Field(..., min_length=1, max_length=128)
    domain_context: str = Field(default="general", min_length=1, max_length=64)
    entity_type: str = Field(..., min_length=1, max_length=64)
    canonical_label: str = Field(..., min_length=1, max_length=255)
    synonyms: list[str] = Field(default_factory=list)
    external_refs: list[ConceptExternalRefToolArgs] = Field(default_factory=list)
    evidence_payload: JSONObject = Field(default_factory=dict)
    rationale: str | None = Field(default=None, max_length=4000)


class GraphChangeClaimToolArgs(BaseModel):
    """Local relation claim inside an AI Full Mode graph-change proposal."""

    model_config = ConfigDict(strict=True)

    source_local_id: str = Field(..., min_length=1, max_length=128)
    target_local_id: str = Field(..., min_length=1, max_length=128)
    relation_type: str = Field(..., min_length=1, max_length=64)
    assessment: FactAssessment
    evidence_payload: JSONObject = Field(default_factory=dict)
    claim_text: str | None = Field(default=None, max_length=4000)
    source_document_ref: str | None = Field(default=None, max_length=1024)


class ProposeGraphChangeToolArgs(BaseModel):
    """Arguments for proposing one governed mini-graph bundle."""

    model_config = ConfigDict(strict=True)

    space_id: str = Field(..., min_length=1, max_length=64)
    concepts: list[GraphChangeConceptToolArgs] = Field(..., min_length=1)
    claims: list[GraphChangeClaimToolArgs] = Field(default_factory=list)
    source_ref: str | None = Field(default=None, max_length=1024)


class SubmitAIFullModeDecisionToolArgs(BaseModel):
    """Arguments for submitting one DB-governed AI decision envelope."""

    model_config = ConfigDict(strict=True)

    space_id: str = Field(..., min_length=1, max_length=64)
    target_type: Literal["concept_proposal", "graph_change_proposal"]
    target_id: str = Field(..., min_length=1, max_length=64)
    action: Literal[
        "APPROVE",
        "MERGE",
        "REJECT",
        "REQUEST_CHANGES",
        "APPLY_RESOLUTION_PLAN",
    ]
    ai_principal: str = Field(..., min_length=1, max_length=128)
    confidence_assessment: DecisionConfidenceAssessment
    risk_tier: Literal["low", "medium", "high"]
    input_hash: str = Field(..., min_length=64, max_length=64)
    evidence_payload: JSONObject = Field(default_factory=dict)
    decision_payload: JSONObject = Field(default_factory=dict)


class ProposeConnectorMetadataToolArgs(BaseModel):
    """Arguments for proposing connector metadata and dictionary mappings."""

    model_config = ConfigDict(strict=True)

    space_id: str = Field(..., min_length=1, max_length=64)
    connector_slug: str = Field(..., min_length=1, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=255)
    connector_kind: str = Field(..., min_length=1, max_length=64)
    domain_context: str = Field(..., min_length=1, max_length=64)
    metadata_payload: JSONObject = Field(default_factory=dict)
    mapping_payload: JSONObject = Field(default_factory=dict)
    evidence_payload: JSONObject = Field(default_factory=dict)
    rationale: str | None = Field(default=None, max_length=4000)
    source_ref: str | None = Field(default=None, max_length=1024)


ToolApprovalMode = Literal["none", "approval_gated"]


@dataclass(frozen=True, slots=True)
class GraphHarnessToolSpec:
    """One declared graph-harness tool capability."""

    name: str
    display_name: str
    description: str
    tool_groups: tuple[str, ...]
    harness_ids: tuple[str, ...]
    input_model: type[BaseModel]
    output_summary: str
    side_effect: bool
    risk_level: Literal["low", "medium", "high"]
    approval_mode: ToolApprovalMode
    required_capability: str | None = None
    idempotency_policy: str = "artana_replay"
    schema_version: str = "1"
    tool_version: str = "1.0.0"


_TOOL_SPECS: tuple[GraphHarnessToolSpec, ...] = (
    GraphHarnessToolSpec(
        name="get_graph_document",
        display_name="Graph Document Read",
        description="Fetch one deterministic graph document for seeded grounding.",
        tool_groups=("graph-read", "graph-document"),
        harness_ids=(
            "graph-search",
            "graph-connections",
            "hypotheses",
            "full-ai-orchestrator",
            "research-init",
            "research-bootstrap",
            "graph-chat",
            "continuous-learning",
            "supervisor",
        ),
        input_model=GraphDocumentToolArgs,
        output_summary="Kernel graph document with nodes, edges, counts, and meta.",
        side_effect=False,
        risk_level="low",
        approval_mode="none",
    ),
    GraphHarnessToolSpec(
        name="list_graph_claims",
        display_name="Graph Claim List",
        description="List graph claims for one research space.",
        tool_groups=("graph-read", "claim-evidence-read"),
        harness_ids=(
            "graph-search",
            "graph-connections",
            "hypotheses",
            "full-ai-orchestrator",
            "research-init",
            "research-bootstrap",
            "graph-chat",
            "continuous-learning",
            "supervisor",
        ),
        input_model=ListGraphClaimsToolArgs,
        output_summary="Paged graph claim list response.",
        side_effect=False,
        risk_level="low",
        approval_mode="none",
    ),
    GraphHarnessToolSpec(
        name="list_graph_hypotheses",
        display_name="Graph Hypothesis List",
        description="List graph hypotheses for one research space.",
        tool_groups=("graph-read", "hypothesis-read"),
        harness_ids=(
            "graph-search",
            "graph-connections",
            "hypotheses",
            "full-ai-orchestrator",
            "research-init",
            "research-bootstrap",
            "graph-chat",
            "continuous-learning",
            "supervisor",
        ),
        input_model=ListGraphHypothesesToolArgs,
        output_summary="Paged hypothesis list response.",
        side_effect=False,
        risk_level="low",
        approval_mode="none",
    ),
    GraphHarnessToolSpec(
        name="suggest_relations",
        display_name="Relation Suggestion",
        description="Suggest dictionary-constrained relations for source entities.",
        tool_groups=("graph-read", "graph-suggestion"),
        harness_ids=(
            "graph-connections",
            "hypotheses",
            "full-ai-orchestrator",
            "research-init",
            "research-bootstrap",
            "graph-chat",
            "continuous-learning",
            "mechanism-discovery",
            "supervisor",
        ),
        input_model=SuggestRelationsToolArgs,
        output_summary="Ranked relation suggestion list.",
        side_effect=False,
        risk_level="low",
        approval_mode="none",
    ),
    GraphHarnessToolSpec(
        name="capture_graph_snapshot",
        display_name="Graph Snapshot Capture",
        description="Capture one graph snapshot payload with a stable snapshot hash.",
        tool_groups=("graph-read", "graph-snapshot"),
        harness_ids=(
            "full-ai-orchestrator",
            "research-init",
            "research-bootstrap",
            "continuous-learning",
            "supervisor",
        ),
        input_model=CaptureGraphSnapshotToolArgs,
        output_summary="Graph snapshot payload for artifact persistence.",
        side_effect=False,
        risk_level="low",
        approval_mode="none",
    ),
    GraphHarnessToolSpec(
        name="run_pubmed_search",
        display_name="PubMed Search",
        description="Run a scoped PubMed discovery query and return the persisted job.",
        tool_groups=("literature-search", "source-discovery"),
        harness_ids=(
            "full-ai-orchestrator",
            "research-init",
            "research-bootstrap",
            "graph-chat",
            "continuous-learning",
            "supervisor",
        ),
        input_model=RunPubMedSearchToolArgs,
        output_summary="Discovery search job payload with preview results.",
        side_effect=True,
        risk_level="medium",
        approval_mode="none",
    ),
    GraphHarnessToolSpec(
        name="run_marrvel_search",
        display_name="MARRVEL Search",
        description=(
            "Run a MARRVEL gene discovery query and return panel data "
            "(OMIM, ClinVar, gnomAD, GTEx, and more)."
        ),
        tool_groups=("literature-search", "source-discovery"),
        harness_ids=(
            "full-ai-orchestrator",
            "research-init",
            "research-bootstrap",
            "graph-chat",
            "continuous-learning",
            "supervisor",
        ),
        input_model=RunMarrvelSearchToolArgs,
        output_summary="MARRVEL discovery result with gene info and panel data.",
        side_effect=True,
        risk_level="medium",
        approval_mode="none",
    ),
    GraphHarnessToolSpec(
        name="list_reasoning_paths",
        display_name="Reasoning Path List",
        description="List reasoning paths for one space and entity pair.",
        tool_groups=("reasoning-read",),
        harness_ids=("mechanism-discovery", "supervisor"),
        input_model=ListReasoningPathsToolArgs,
        output_summary="Paged reasoning path list response.",
        side_effect=False,
        risk_level="low",
        approval_mode="none",
    ),
    GraphHarnessToolSpec(
        name="get_reasoning_path",
        display_name="Reasoning Path Detail",
        description="Fetch one reasoning path detail payload.",
        tool_groups=("reasoning-read",),
        harness_ids=("mechanism-discovery", "supervisor"),
        input_model=GetReasoningPathToolArgs,
        output_summary="Detailed reasoning path with ordered steps.",
        side_effect=False,
        risk_level="low",
        approval_mode="none",
    ),
    GraphHarnessToolSpec(
        name="list_claims_by_entity",
        display_name="Claims By Entity",
        description="List claims connected to one entity.",
        tool_groups=("claim-validation", "claim-evidence-read"),
        harness_ids=("claim-curation", "mechanism-discovery", "supervisor"),
        input_model=ListClaimsByEntityToolArgs,
        output_summary="Paged claim list for one entity.",
        side_effect=False,
        risk_level="low",
        approval_mode="none",
    ),
    GraphHarnessToolSpec(
        name="list_claim_participants",
        display_name="Claim Participants",
        description="List structured participants for one graph claim.",
        tool_groups=("claim-validation", "claim-evidence-read"),
        harness_ids=("claim-curation", "supervisor"),
        input_model=ListClaimParticipantsToolArgs,
        output_summary="Claim participant list response.",
        side_effect=False,
        risk_level="low",
        approval_mode="none",
    ),
    GraphHarnessToolSpec(
        name="list_claim_evidence",
        display_name="Claim Evidence",
        description="List evidence rows for one graph claim.",
        tool_groups=("claim-validation", "claim-evidence-read"),
        harness_ids=("claim-curation", "supervisor"),
        input_model=ListClaimEvidenceToolArgs,
        output_summary="Claim evidence list response with total count.",
        side_effect=False,
        risk_level="low",
        approval_mode="none",
    ),
    GraphHarnessToolSpec(
        name="list_relation_conflicts",
        display_name="Relation Conflicts",
        description="List mixed-polarity canonical relation conflicts.",
        tool_groups=("claim-validation", "graph-read"),
        harness_ids=("claim-curation", "supervisor"),
        input_model=ListRelationConflictsToolArgs,
        output_summary="Paged relation conflict list response.",
        side_effect=False,
        risk_level="low",
        approval_mode="none",
    ),
    GraphHarnessToolSpec(
        name="create_graph_claim",
        display_name="Create Graph Claim",
        description="Create one unresolved graph claim through the governed graph-service path.",
        tool_groups=("graph-write", "approval-gated-write"),
        harness_ids=("claim-curation", "supervisor"),
        input_model=CreateGraphClaimToolArgs,
        output_summary="Created graph claim payload.",
        side_effect=True,
        risk_level="high",
        approval_mode="approval_gated",
    ),
    GraphHarnessToolSpec(
        name="create_manual_hypothesis",
        display_name="Create Manual Hypothesis",
        description="Create one manual graph hypothesis through the graph service.",
        tool_groups=("graph-write", "approval-gated-write"),
        harness_ids=("claim-curation", "mechanism-discovery", "supervisor"),
        input_model=CreateManualHypothesisToolArgs,
        output_summary="Created manual hypothesis payload.",
        side_effect=True,
        risk_level="high",
        approval_mode="approval_gated",
    ),
    GraphHarnessToolSpec(
        name="propose_graph_concept",
        display_name="Propose Graph Concept",
        description=(
            "Submit a governed AI Full Mode concept proposal without mutating "
            "official concept state."
        ),
        tool_groups=("ai-full-mode", "graph-proposal-write"),
        harness_ids=("full-ai-orchestrator", "continuous-learning", "supervisor"),
        input_model=ProposeGraphConceptToolArgs,
        output_summary="Governed concept proposal with duplicate checks and proposal hash.",
        side_effect=True,
        risk_level="medium",
        approval_mode="none",
    ),
    GraphHarnessToolSpec(
        name="propose_graph_change",
        display_name="Propose Graph Change",
        description=(
            "Submit a governed AI Full Mode mini-graph proposal containing "
            "concepts, synonyms, evidence, and claims."
        ),
        tool_groups=("ai-full-mode", "graph-proposal-write"),
        harness_ids=("full-ai-orchestrator", "continuous-learning", "supervisor"),
        input_model=ProposeGraphChangeToolArgs,
        output_summary="Graph-change proposal with deterministic resolution plan.",
        side_effect=True,
        risk_level="medium",
        approval_mode="none",
    ),
    GraphHarnessToolSpec(
        name="submit_ai_full_mode_decision",
        display_name="Submit AI Full Mode Decision",
        description=(
            "Submit an auditable AI decision envelope; the graph DB policy "
            "decides whether it may apply official changes."
        ),
        tool_groups=("ai-full-mode", "graph-policy-decision"),
        harness_ids=("full-ai-orchestrator", "continuous-learning", "supervisor"),
        input_model=SubmitAIFullModeDecisionToolArgs,
        output_summary="AI decision policy result and application status.",
        side_effect=True,
        risk_level="high",
        approval_mode="none",
    ),
    GraphHarnessToolSpec(
        name="propose_connector_metadata",
        display_name="Propose Connector Metadata",
        description=(
            "Submit connector metadata and field mappings for graph DB review "
            "without executing connector runtime code."
        ),
        tool_groups=("ai-full-mode", "connector-proposal-write"),
        harness_ids=("full-ai-orchestrator", "continuous-learning", "supervisor"),
        input_model=ProposeConnectorMetadataToolArgs,
        output_summary="Connector proposal validation result and metadata ledger entry.",
        side_effect=True,
        risk_level="medium",
        approval_mode="none",
    ),
)

_TOOL_SPEC_BY_NAME = {spec.name: spec for spec in _TOOL_SPECS}


def list_graph_harness_tool_specs() -> tuple[GraphHarnessToolSpec, ...]:
    """Return the full graph-harness tool catalog."""
    return _TOOL_SPECS


def get_graph_harness_tool_spec(tool_name: str) -> GraphHarnessToolSpec | None:
    """Return one catalog entry by tool name."""
    return _TOOL_SPEC_BY_NAME.get(tool_name.strip())


def visible_tool_names_for_harness(harness_id: str) -> set[str]:
    """Return the declared visible tool names for one harness id."""
    normalized = harness_id.strip()
    if normalized == "":
        return set()
    return {spec.name for spec in _TOOL_SPECS if normalized in spec.harness_ids}


__all__ = [
    "CaptureGraphSnapshotToolArgs",
    "ConceptExternalRefToolArgs",
    "CreateGraphClaimToolArgs",
    "CreateManualHypothesisToolArgs",
    "GetReasoningPathToolArgs",
    "GraphChangeClaimToolArgs",
    "GraphChangeConceptToolArgs",
    "GraphDocumentToolArgs",
    "GraphHarnessToolSpec",
    "ListClaimEvidenceToolArgs",
    "ListClaimParticipantsToolArgs",
    "ListClaimsByEntityToolArgs",
    "ListGraphClaimsToolArgs",
    "ListGraphHypothesesToolArgs",
    "ListReasoningPathsToolArgs",
    "ListRelationConflictsToolArgs",
    "ProposeConnectorMetadataToolArgs",
    "ProposeGraphChangeToolArgs",
    "ProposeGraphConceptToolArgs",
    "RunMarrvelSearchToolArgs",
    "RunPubMedSearchToolArgs",
    "SubmitAIFullModeDecisionToolArgs",
    "SuggestRelationsToolArgs",
    "get_graph_harness_tool_spec",
    "list_graph_harness_tool_specs",
    "visible_tool_names_for_harness",
]
