"""Variant-aware document extraction bridge for genomics-capable harness docs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast
from uuid import UUID

from artana_evidence_api.claim_fingerprint import compute_claim_fingerprint
from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.ranking import rank_candidate_claim
from artana_evidence_api.review_item_store import HarnessReviewItemDraft
from artana_evidence_api.types.common import JSONObject, JSONValue

from src.application.agents.services._fact_assessment_scoring import (
    fact_assessment_payload,
    fact_evidence_weight,
)
from src.domain.agents.contexts.extraction_context import ExtractionContext
from src.domain.agents.contracts.extraction import (
    ExtractedEntityCandidate,
    ExtractedRelation,
    ExtractionContract,
    RejectedFact,
)
from src.domain.agents.contracts.fact_assessment import (
    FactAssessment,
    GroundingLevel,
    MappingStatus,
    SpeculationLevel,
    SupportBand,
)
from src.domain.services.genomics_signal_parser import build_genomics_signal_bundle
from src.infrastructure.llm.adapters.extraction_agent_adapter import (
    ArtanaExtractionAdapter,
)
from src.infrastructure.llm.graph_domain_ai_config import (
    BIOMEDICAL_EXTRACTION_PAYLOAD_CONFIG,
    BIOMEDICAL_EXTRACTION_PROMPT_CONFIG,
)
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction import DocumentExtractionReviewContext
    from artana_evidence_api.document_store import HarnessDocumentRecord
    from artana_evidence_api.graph_client import GraphTransportBundle

_SUPPORTED_VARIANT_AWARE_SOURCE_TYPES = frozenset(
    {
        "pubmed",
        "text",
        "pdf",
        "clinvar",
        "marrvel",
    },
)
_GENOMICS_VARIABLE_IDS: dict[str, str] = {
    "transcript": "VAR_TRANSCRIPT_ID",
    "genomic_position": "VAR_GENOMIC_POSITION",
    "hgvs_cdna": "VAR_HGVS_CDNA",
    "hgvs_protein": "VAR_HGVS_PROTEIN",
    "hgvs_genomic": "VAR_HGVS_GENOMIC",
    "zygosity": "VAR_ZYGOSITY",
    "inheritance": "VAR_INHERITANCE_MODE",
    "exon_or_intron": "VAR_EXON_INTRON",
    "classification": "VAR_CLINVAR_CLASS",
}
_REQUIRED_VARIANT_ANCHORS = ("gene_symbol", "hgvs_notation")
_REVIEW_ITEM_SOURCE_FAMILY = "document_extraction"
_REVIEWABLE_REJECTED_SUPPORT_BANDS = frozenset(
    {SupportBand.STRONG, SupportBand.SUPPORTED},
)
_MIN_PROTEIN_ALIAS_LENGTH = 7
_THREE_TO_ONE_AMINO_ACID_CODES: dict[str, str] = {
    "Ala": "A",
    "Arg": "R",
    "Asn": "N",
    "Asp": "D",
    "Cys": "C",
    "Gln": "Q",
    "Glu": "E",
    "Gly": "G",
    "His": "H",
    "Ile": "I",
    "Leu": "L",
    "Lys": "K",
    "Met": "M",
    "Phe": "F",
    "Pro": "P",
    "Ser": "S",
    "Thr": "T",
    "Trp": "W",
    "Tyr": "Y",
    "Val": "V",
}


@dataclass(frozen=True, slots=True)
class VariantAwareDocumentExtractionResult:
    """Structured result returned by the variant-aware extraction bridge."""

    contract: ExtractionContract
    proposal_drafts: tuple[HarnessProposalDraft, ...]
    review_item_drafts: tuple[HarnessReviewItemDraft, ...]
    skipped_items: list[JSONObject]
    candidate_discovery: JSONObject
    extraction_diagnostics: JSONObject


def document_supports_variant_aware_extraction(
    *,
    document: HarnessDocumentRecord,
) -> bool:
    """Return True when the document should use the variant-aware bridge."""
    source_type = document.source_type.strip().lower()
    if source_type not in _SUPPORTED_VARIANT_AWARE_SOURCE_TYPES:
        return False
    raw_record = _build_raw_record(document=document)
    signals = build_genomics_signal_bundle(
        raw_record=raw_record,
        source_type=source_type,
    )
    return bool(signals.get("variant_aware_recommended"))


async def extract_variant_aware_document(
    *,
    space_id: UUID,
    document: HarnessDocumentRecord,
    graph_api_gateway: GraphTransportBundle,
    review_context: DocumentExtractionReviewContext | None = None,
) -> VariantAwareDocumentExtractionResult:
    """Run the shared variant-aware extraction path for one harness document."""
    del review_context  # reserved for future ranking/prompt context expansion

    source_type = document.source_type.strip().lower()
    raw_record = _build_raw_record(document=document)
    signals = build_genomics_signal_bundle(
        raw_record=raw_record,
        source_type=source_type,
    )
    extraction_source_type = _extraction_source_type_for_document(source_type)
    if extraction_source_type is None:
        message = (
            f"Document source type '{document.source_type}' is not supported for "
            "variant-aware extraction."
        )
        raise ValueError(message)

    context = ExtractionContext(
        document_id=document.id,
        source_type=extraction_source_type,
        research_space_id=str(space_id),
        raw_record=raw_record,
        genomics_signals=signals,
        shadow_mode=True,
    )
    adapter = ArtanaExtractionAdapter(
        prompt_config=BIOMEDICAL_EXTRACTION_PROMPT_CONFIG,
        payload_config=BIOMEDICAL_EXTRACTION_PAYLOAD_CONFIG,
    )
    try:
        contract = await adapter.extract(context)
    finally:
        await adapter.close()

    variant_entities = _merge_variant_entities(
        contract=contract,
        genomics_signals=signals,
    )
    proposal_drafts, review_item_drafts, skipped_items = (
        _build_variant_aware_proposal_drafts(
            space_id=space_id,
            document=document,
            graph_api_gateway=graph_api_gateway,
            contract=contract,
            variant_entities=variant_entities,
            raw_record=raw_record,
        )
    )
    if not proposal_drafts and not review_item_drafts and not skipped_items:
        skipped_items.append(
            {
                "kind": "variant_aware_no_output",
                "reason": (
                    "Variant-aware extraction did not yield reviewable entities, "
                    "observations, or relations."
                ),
                "agent_decision": contract.decision,
                "agent_rationale": contract.rationale,
            },
        )
    candidate_discovery = {
        "method": "variant_aware_extraction",
        "variant_aware_recommended": bool(signals.get("variant_aware_recommended")),
        "llm_attempted": contract.decision == "generated",
        "llm_candidate_count": len(contract.relations),
        "entity_candidate_count": len(variant_entities),
        "observation_candidate_count": sum(
            1
            for draft in proposal_drafts
            if draft.proposal_type == "observation_candidate"
        ),
        "review_item_count": len(review_item_drafts),
        "llm_status": (
            "completed" if contract.decision == "generated" else contract.decision
        ),
    }
    extraction_diagnostics: JSONObject = {
        "extraction_mode": "variant_aware",
        "agent_decision": contract.decision,
        "agent_run_id": contract.agent_run_id,
        "variant_aware_recommended": bool(signals.get("variant_aware_recommended")),
        "variant_signal_candidate_count": len(
            cast("list[object]", signals.get("variant_candidates", [])),
        ),
        "entity_count": len(contract.entities),
        "variant_entity_count": len(variant_entities),
        "observation_count": len(contract.observations),
        "relation_count": len(contract.relations),
        "rejected_fact_count": len(contract.rejected_facts),
        "bridge_proposal_count": len(proposal_drafts),
        "bridge_review_item_count": len(review_item_drafts),
        "bridge_skipped_count": len(skipped_items),
    }
    if contract.rationale.strip():
        extraction_diagnostics["agent_rationale"] = contract.rationale.strip()
    if contract.decision != "generated":
        extraction_diagnostics["fallback_from_signals"] = bool(variant_entities)

    return VariantAwareDocumentExtractionResult(
        contract=contract,
        proposal_drafts=proposal_drafts,
        review_item_drafts=review_item_drafts,
        skipped_items=skipped_items,
        candidate_discovery=candidate_discovery,
        extraction_diagnostics=extraction_diagnostics,
    )


def _build_raw_record(
    *,
    document: HarnessDocumentRecord,
) -> JSONObject:
    metadata = {
        str(key): cast("JSONValue", to_json_value(value))
        for key, value in document.metadata.items()
    }
    text_content = document.text_content.strip()
    raw_record: JSONObject = {
        **metadata,
        "document_id": document.id,
        "title": document.title,
        "source_type": document.source_type,
        "text": text_content,
        "content": text_content,
        "abstract": text_content,
        "full_text": text_content,
    }
    if document.filename is not None:
        raw_record["filename"] = document.filename
    return raw_record


def _extraction_source_type_for_document(
    source_type: str,
) -> str | None:
    normalized = source_type.strip().lower()
    if normalized in {"text", "pdf", "pubmed"}:
        return "pubmed"
    if normalized in {"clinvar", "marrvel"}:
        return normalized
    return None


def _strong_signal_assessment(
    *,
    rationale: str,
) -> FactAssessment:
    return FactAssessment(
        support_band=SupportBand.STRONG,
        grounding_level=GroundingLevel.SPAN,
        mapping_status=MappingStatus.RESOLVED,
        speculation_level=SpeculationLevel.DIRECT,
        confidence_rationale=rationale,
    )


def _merge_variant_entities(
    *,
    contract: ExtractionContract,
    genomics_signals: JSONObject,
) -> tuple[ExtractedEntityCandidate, ...]:
    merged_by_key: dict[str, ExtractedEntityCandidate] = {}
    evidence_by_key: dict[str, list[JSONObject]] = {}

    for candidate in contract.entities:
        if candidate.entity_type.strip().upper() != "VARIANT":
            continue
        enriched_candidate = _merge_variant_candidate_with_signal(
            candidate=candidate,
            genomics_signals=genomics_signals,
        )
        key = _variant_candidate_key(enriched_candidate)
        if key not in merged_by_key:
            merged_by_key[key] = enriched_candidate
        else:
            merged_by_key[key] = _prefer_richer_variant_candidate(
                merged_by_key[key],
                enriched_candidate,
            )
        evidence_by_key.setdefault(key, []).append(
            {
                "evidence_excerpt": enriched_candidate.evidence_excerpt,
                "evidence_locator": enriched_candidate.evidence_locator,
            },
        )

    for signal_candidate in _fallback_variant_candidates_from_signals(genomics_signals):
        key = _variant_candidate_key(signal_candidate)
        if key not in merged_by_key:
            merged_by_key[key] = signal_candidate
        evidence_by_key.setdefault(key, []).append(
            {
                "evidence_excerpt": signal_candidate.evidence_excerpt,
                "evidence_locator": signal_candidate.evidence_locator,
            },
        )

    merged: list[ExtractedEntityCandidate] = []
    for key, candidate in merged_by_key.items():
        merged_metadata = dict(candidate.metadata)
        supporting_evidence = evidence_by_key.get(key, [])
        if supporting_evidence:
            merged_metadata["supporting_evidence"] = supporting_evidence
        aliases = _entity_candidate_aliases(candidate)
        if aliases:
            merged_metadata.setdefault("suggested_aliases", aliases)
        merged.append(candidate.model_copy(update={"metadata": merged_metadata}))
    return tuple(merged)


def _merge_variant_candidate_with_signal(
    *,
    candidate: ExtractedEntityCandidate,
    genomics_signals: JSONObject,
) -> ExtractedEntityCandidate:
    signal_match = _match_signal_candidate(
        label=candidate.label,
        anchors=candidate.anchors,
        genomics_signals=genomics_signals,
    )
    if signal_match is None:
        return candidate
    merged_anchors = {
        **signal_match["anchors"],
        **candidate.anchors,
    }
    merged_metadata = {
        **signal_match["metadata"],
        **candidate.metadata,
    }
    return candidate.model_copy(
        update={
            "anchors": merged_anchors,
            "metadata": merged_metadata,
        },
    )


def _fallback_variant_candidates_from_signals(
    genomics_signals: JSONObject,
) -> tuple[ExtractedEntityCandidate, ...]:
    raw_candidates = genomics_signals.get("variant_candidates")
    if not isinstance(raw_candidates, list):
        return ()
    fallback_candidates: list[ExtractedEntityCandidate] = []
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, dict):
            continue
        anchors = raw_candidate.get("anchors")
        metadata = raw_candidate.get("metadata")
        evidence_excerpt = raw_candidate.get("evidence_excerpt")
        evidence_locator = raw_candidate.get("evidence_locator")
        if not isinstance(anchors, dict) or not isinstance(metadata, dict):
            continue
        if not isinstance(evidence_excerpt, str) or not evidence_excerpt.strip():
            continue
        if not isinstance(evidence_locator, str) or not evidence_locator.strip():
            continue
        gene_symbol = anchors.get("gene_symbol")
        hgvs_notation = anchors.get("hgvs_notation")
        if not isinstance(gene_symbol, str) or not gene_symbol.strip():
            continue
        if not isinstance(hgvs_notation, str) or not hgvs_notation.strip():
            continue
        fallback_candidates.append(
            ExtractedEntityCandidate(
                entity_type="VARIANT",
                label=hgvs_notation.strip(),
                anchors={
                    str(key): cast("JSONValue", to_json_value(value))
                    for key, value in anchors.items()
                },
                metadata={
                    str(key): cast("JSONValue", to_json_value(value))
                    for key, value in metadata.items()
                },
                evidence_excerpt=evidence_excerpt.strip(),
                evidence_locator=evidence_locator.strip(),
                assessment=_strong_signal_assessment(
                    rationale=(
                        "Deterministic genomics signal parsing recovered an exact "
                        "anchored variant from the document text."
                    ),
                ),
            ),
        )
    return tuple(fallback_candidates)


def _match_signal_candidate(
    *,
    label: str,
    anchors: JSONObject,
    genomics_signals: JSONObject,
) -> JSONObject | None:
    raw_candidates = genomics_signals.get("variant_candidates")
    if not isinstance(raw_candidates, list):
        return None
    normalized_label = label.strip().lower()
    anchor_gene = _normalized_string(anchors.get("gene_symbol"))
    anchor_hgvs = _normalized_string(anchors.get("hgvs_notation"))
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, dict):
            continue
        signal_anchors = raw_candidate.get("anchors")
        signal_metadata = raw_candidate.get("metadata")
        if not isinstance(signal_anchors, dict) or not isinstance(
            signal_metadata, dict
        ):
            continue
        signal_gene = _normalized_string(signal_anchors.get("gene_symbol"))
        signal_hgvs = _normalized_string(signal_anchors.get("hgvs_notation"))
        if (
            anchor_gene is not None
            and anchor_hgvs is not None
            and signal_gene == anchor_gene
            and signal_hgvs == anchor_hgvs
        ):
            return cast("JSONObject", raw_candidate)
        signal_labels = {
            value
            for value in (
                signal_hgvs,
                _normalized_string(signal_metadata.get("hgvs_protein")),
                _normalized_string(signal_metadata.get("transcript")),
            )
            if value is not None
        }
        transcript = _normalized_string(signal_metadata.get("transcript"))
        if transcript is not None and signal_hgvs is not None:
            signal_labels.add(f"{transcript}:{signal_hgvs}")
        protein = _normalized_string(signal_metadata.get("hgvs_protein"))
        if signal_hgvs is not None and protein is not None:
            signal_labels.add(f"{signal_hgvs} ({protein})")
        if transcript is not None and signal_hgvs is not None and protein is not None:
            signal_labels.add(f"{transcript}:{signal_hgvs} ({protein})")
        for protein_alias in _protein_aliases(signal_metadata.get("hgvs_protein")):
            signal_labels.add(protein_alias.casefold())
        if normalized_label in signal_labels:
            return cast("JSONObject", raw_candidate)
        if signal_hgvs is not None and signal_hgvs in normalized_label:
            return cast("JSONObject", raw_candidate)
    return None


def _variant_candidate_key(candidate: ExtractedEntityCandidate) -> str:
    gene_symbol = _normalized_string(candidate.anchors.get("gene_symbol"))
    hgvs_notation = _normalized_string(candidate.anchors.get("hgvs_notation"))
    if gene_symbol is not None and hgvs_notation is not None:
        return f"VARIANT:{gene_symbol}:{hgvs_notation}"
    return f"VARIANT:{candidate.label.strip().lower()}"


def _prefer_richer_variant_candidate(
    existing: ExtractedEntityCandidate,
    candidate: ExtractedEntityCandidate,
) -> ExtractedEntityCandidate:
    existing_priority = fact_evidence_weight(existing)
    candidate_priority = fact_evidence_weight(candidate)
    if candidate_priority > existing_priority:
        return candidate
    if existing_priority > candidate_priority:
        return existing
    existing_richness = _anchor_richness(existing.anchors) + _anchor_richness(
        existing.metadata,
    )
    candidate_richness = _anchor_richness(candidate.anchors) + _anchor_richness(
        candidate.metadata,
    )
    return candidate if candidate_richness > existing_richness else existing


def _anchor_richness(payload: JSONObject) -> int:
    return sum(
        1
        for value in payload.values()
        if value is not None and (not isinstance(value, str) or bool(value.strip()))
    )


def _build_variant_aware_proposal_drafts(  # noqa: PLR0914
    *,
    space_id: UUID,
    document: HarnessDocumentRecord,
    graph_api_gateway: GraphTransportBundle,
    contract: ExtractionContract,
    variant_entities: tuple[ExtractedEntityCandidate, ...],
    raw_record: JSONObject,
) -> tuple[
    tuple[HarnessProposalDraft, ...],
    tuple[HarnessReviewItemDraft, ...],
    list[JSONObject],
]:
    drafts: list[HarnessProposalDraft] = []
    review_item_drafts: list[HarnessReviewItemDraft] = []
    skipped_items: list[JSONObject] = []
    entity_index = _entity_candidate_index(
        contract=contract, variant_entities=variant_entities
    )

    for index, candidate in enumerate(variant_entities):
        candidate_key = _variant_candidate_key(candidate)
        confidence = fact_evidence_weight(candidate)
        ranking = rank_candidate_claim(
            confidence=confidence,
            supporting_document_count=1,
            evidence_reference_count=1,
        )
        fingerprint = compute_claim_fingerprint(
            candidate.entity_type.strip().upper(),
            candidate_key,
            candidate.label,
        )
        drafts.append(
            HarnessProposalDraft(
                proposal_type="entity_candidate",
                source_kind="document_extraction",
                source_key=f"{document.id}:variant:{index}",
                document_id=document.id,
                title=f"Extracted entity: {candidate.entity_type} {candidate.label}",
                summary=candidate.evidence_excerpt,
                confidence=confidence,
                ranking_score=ranking.score,
                reasoning_path={
                    "kind": "entity_candidate",
                    "entity_type": candidate.entity_type,
                    "label": candidate.label,
                    "evidence_locator": candidate.evidence_locator,
                    "assessment": fact_assessment_payload(candidate),
                },
                evidence_bundle=[
                    {
                        "source_type": document.source_type,
                        "locator": candidate.evidence_locator,
                        "excerpt": candidate.evidence_excerpt,
                        "relevance": confidence,
                    },
                ],
                payload=_entity_candidate_payload(candidate),
                metadata={
                    "document_id": document.id,
                    "document_title": document.title,
                    "document_source_type": document.source_type,
                    "candidate_kind": "entity",
                    "candidate_key": candidate_key,
                    "assessment": fact_assessment_payload(candidate),
                    "review_required": not _variant_candidate_is_persistable(candidate),
                    **ranking.metadata,
                },
                claim_fingerprint=fingerprint,
            ),
        )
        if not _variant_candidate_is_persistable(candidate):
            review_item_drafts.append(
                _build_incomplete_variant_review_item(
                    document=document,
                    candidate=candidate,
                    candidate_key=candidate_key,
                    confidence=confidence,
                    ranking_score=ranking.score,
                ),
            )
            continue

        observation_drafts, observation_review_items, observation_skips = (
            _build_variant_observation_drafts(
                document=document,
                candidate=candidate,
                candidate_key=candidate_key,
            )
        )
        drafts.extend(observation_drafts)
        review_item_drafts.extend(observation_review_items)
        skipped_items.extend(observation_skips)

    for index, relation in enumerate(contract.relations):
        draft = _build_relation_draft(
            space_id=space_id,
            document=document,
            relation=relation,
            graph_api_gateway=graph_api_gateway,
            entity_index=entity_index,
            raw_record=raw_record,
            index=index,
        )
        if draft is None:
            skipped_items.append(
                {
                    "kind": "relation_skipped",
                    "relation_type": relation.relation_type,
                    "source_label": relation.source_label,
                    "target_label": relation.target_label,
                    "reason": "Relation was missing required endpoint labels.",
                },
            )
            continue
        drafts.append(draft)

    for index, rejected_fact in enumerate(contract.rejected_facts):
        review_item = _build_review_item_from_rejected_fact(
            document=document,
            rejected_fact=rejected_fact,
            index=index,
        )
        if review_item is not None:
            review_item_drafts.append(review_item)
            continue
        skipped_items.append(
            {
                "kind": "rejected_fact",
                "fact_type": rejected_fact.fact_type,
                "reason": rejected_fact.reason,
                "payload": rejected_fact.payload,
                "assessment": (
                    fact_assessment_payload(rejected_fact)
                    if rejected_fact.assessment is not None
                    else None
                ),
            },
        )

    return tuple(drafts), tuple(review_item_drafts), skipped_items


def _entity_candidate_index(
    *,
    contract: ExtractionContract,
    variant_entities: tuple[ExtractedEntityCandidate, ...],
) -> dict[tuple[str, str], ExtractedEntityCandidate]:
    index: dict[tuple[str, str], ExtractedEntityCandidate] = {}
    for candidate in (*contract.entities, *variant_entities):
        normalized_type = candidate.entity_type.strip().upper()
        if not normalized_type:
            continue
        labels = {
            candidate.label.strip().lower(),
        }
        for key in (
            "display_label",
            "hgvs_notation",
            "gene_symbol",
            "hpo_term",
            "mechanism_name",
            "name",
            "label",
        ):
            value = candidate.anchors.get(key)
            if isinstance(value, str) and value.strip():
                labels.add(value.strip().lower())
        for label in labels:
            if label and (normalized_type, label) not in index:
                index[(normalized_type, label)] = candidate
    return index


def _build_variant_observation_drafts(
    *,
    document: HarnessDocumentRecord,
    candidate: ExtractedEntityCandidate,
    candidate_key: str,
) -> tuple[list[HarnessProposalDraft], list[HarnessReviewItemDraft], list[JSONObject]]:
    drafts: list[HarnessProposalDraft] = []
    review_item_drafts: list[HarnessReviewItemDraft] = []
    skipped_items: list[JSONObject] = []
    subject_payload = _entity_candidate_payload(candidate)
    confidence = fact_evidence_weight(candidate)
    for field_name, variable_id in _GENOMICS_VARIABLE_IDS.items():
        raw_value = candidate.metadata.get(field_name)
        normalized_value = _normalized_metadata_value(raw_value)
        if normalized_value is None:
            continue
        fingerprint = compute_claim_fingerprint(
            candidate_key,
            variable_id,
            str(normalized_value),
        )
        drafts.append(
            HarnessProposalDraft(
                proposal_type="observation_candidate",
                source_kind="document_extraction",
                source_key=f"{document.id}:observation:{candidate_key}:{variable_id}",
                document_id=document.id,
                title=f"Extracted observation: {field_name} for {candidate.label}",
                summary=candidate.evidence_excerpt,
                confidence=confidence,
                ranking_score=confidence,
                reasoning_path={
                    "kind": "observation_candidate",
                    "field_name": field_name,
                    "variable_id": variable_id,
                    "candidate_key": candidate_key,
                    "assessment": fact_assessment_payload(candidate),
                },
                evidence_bundle=[
                    {
                        "source_type": document.source_type,
                        "locator": candidate.evidence_locator,
                        "excerpt": candidate.evidence_excerpt,
                        "relevance": confidence,
                    },
                ],
                payload={
                    "subject_entity_candidate": subject_payload,
                    "variable_id": variable_id,
                    "field_name": field_name,
                    "value": normalized_value,
                    "unit": None,
                    "evidence_excerpt": candidate.evidence_excerpt,
                    "evidence_locator": candidate.evidence_locator,
                },
                metadata={
                    "document_id": document.id,
                    "document_title": document.title,
                    "document_source_type": document.source_type,
                    "candidate_kind": "observation",
                    "candidate_key": candidate_key,
                    "assessment": fact_assessment_payload(candidate),
                    "subject_label": candidate.label,
                },
                claim_fingerprint=fingerprint,
            ),
        )
    phenotype_spans = candidate.metadata.get("phenotype_spans")
    if isinstance(phenotype_spans, list) and phenotype_spans:
        review_item_drafts.extend(
            _build_phenotype_review_items(
                document=document,
                candidate=candidate,
                candidate_key=candidate_key,
                phenotype_spans=phenotype_spans,
                confidence=confidence,
            ),
        )
    return drafts, review_item_drafts, skipped_items


def _build_incomplete_variant_review_item(
    *,
    document: HarnessDocumentRecord,
    candidate: ExtractedEntityCandidate,
    candidate_key: str,
    confidence: float,
    ranking_score: float,
) -> HarnessReviewItemDraft:
    fingerprint = compute_claim_fingerprint(
        candidate_key,
        "variant_review",
        candidate.label,
    )
    return HarnessReviewItemDraft(
        review_type="variant_anchor_review",
        source_family=_REVIEW_ITEM_SOURCE_FAMILY,
        source_kind="document_extraction",
        source_key=f"{document.id}:variant-review:{candidate_key}",
        document_id=document.id,
        title=f"Review incomplete variant: {candidate.label}",
        summary=(
            "This variant mention looks important, but it is missing enough anchor "
            "data that it should be reviewed before promotion."
        ),
        priority="high",
        confidence=confidence,
        ranking_score=ranking_score,
        evidence_bundle=[
            {
                "source_type": document.source_type,
                "locator": candidate.evidence_locator,
                "excerpt": candidate.evidence_excerpt,
                "relevance": confidence,
            },
        ],
        payload={
            "candidate_key": candidate_key,
            "entity_type": candidate.entity_type,
            "label": candidate.label,
            "anchors": dict(candidate.anchors),
            "metadata": dict(candidate.metadata),
            "required_anchors": list(_REQUIRED_VARIANT_ANCHORS),
            "missing_anchors": [
                anchor_name
                for anchor_name in _REQUIRED_VARIANT_ANCHORS
                if not isinstance(candidate.anchors.get(anchor_name), str)
                or candidate.anchors.get(anchor_name, "").strip() == ""
            ],
            "evidence_excerpt": candidate.evidence_excerpt,
            "evidence_locator": candidate.evidence_locator,
            "assessment": fact_assessment_payload(candidate),
        },
        metadata={
            "document_id": document.id,
            "document_title": document.title,
            "document_source_type": document.source_type,
            "candidate_kind": "entity_review",
            "candidate_key": candidate_key,
            "assessment": fact_assessment_payload(candidate),
        },
        review_fingerprint=fingerprint,
    )


def _build_phenotype_review_items(
    *,
    document: HarnessDocumentRecord,
    candidate: ExtractedEntityCandidate,
    candidate_key: str,
    phenotype_spans: list[object],
    confidence: float,
) -> list[HarnessReviewItemDraft]:
    review_items: list[HarnessReviewItemDraft] = []
    for index, phenotype_span in enumerate(phenotype_spans):
        normalized_span = _normalized_phenotype_review_span(phenotype_span)
        if normalized_span == "":
            continue
        fingerprint = compute_claim_fingerprint(
            candidate_key,
            "phenotype_review",
            normalized_span,
        )
        review_items.append(
            HarnessReviewItemDraft(
                review_type="phenotype_claim_review",
                source_family=_REVIEW_ITEM_SOURCE_FAMILY,
                source_kind="document_extraction",
                source_key=(f"{document.id}:phenotype-review:{candidate_key}:{index}"),
                document_id=document.id,
                title=f"Review phenotype link for {candidate.label}",
                summary=normalized_span,
                priority="medium",
                confidence=confidence,
                ranking_score=confidence,
                evidence_bundle=[
                    {
                        "source_type": document.source_type,
                        "locator": candidate.evidence_locator,
                        "excerpt": candidate.evidence_excerpt,
                        "relevance": confidence,
                    },
                ],
                payload={
                    "candidate_key": candidate_key,
                    "variant_label": candidate.label,
                    "variant_anchors": dict(candidate.anchors),
                    "phenotype_span": normalized_span,
                    "evidence_excerpt": candidate.evidence_excerpt,
                    "evidence_locator": candidate.evidence_locator,
                    "assessment": fact_assessment_payload(candidate),
                    "proposal_draft": {
                        "proposal_type": "candidate_claim",
                        "title": (
                            f"Extracted claim: {candidate.label} CAUSES "
                            f"{normalized_span}"
                        ),
                        "summary": candidate.evidence_excerpt,
                        "confidence": confidence,
                        "ranking_score": confidence,
                        "reasoning_path": {
                            "kind": "phenotype_review_conversion",
                            "candidate_key": candidate_key,
                            "phenotype_span": normalized_span,
                            "assessment": fact_assessment_payload(candidate),
                        },
                        "payload": {
                            "proposed_subject": _resolved_or_unresolved_entity_id(
                                label=candidate.label,
                                graph_match=None,
                            ),
                            "proposed_subject_label": candidate.label,
                            "proposed_subject_entity_candidate": (
                                _entity_candidate_payload(candidate)
                            ),
                            "proposed_claim_type": "CAUSES",
                            "proposed_object": _resolved_or_unresolved_entity_id(
                                label=normalized_span,
                                graph_match=None,
                            ),
                            "proposed_object_label": normalized_span,
                            "evidence_entity_ids": [],
                        },
                        "metadata": {
                            "document_id": document.id,
                            "document_title": document.title,
                            "document_source_type": document.source_type,
                            "subject_label": candidate.label,
                            "object_label": normalized_span,
                            "subject_entity_type": "VARIANT",
                            "object_entity_type": "PHENOTYPE",
                            "assessment": fact_assessment_payload(candidate),
                        },
                        "claim_fingerprint": compute_claim_fingerprint(
                            candidate.label,
                            "CAUSES",
                            normalized_span,
                        ),
                    },
                },
                metadata={
                    "document_id": document.id,
                    "document_title": document.title,
                    "document_source_type": document.source_type,
                    "candidate_kind": "phenotype_review",
                    "candidate_key": candidate_key,
                    "assessment": fact_assessment_payload(candidate),
                },
                review_fingerprint=fingerprint,
            ),
        )
    return review_items


def _build_review_item_from_rejected_fact(
    *,
    document: HarnessDocumentRecord,
    rejected_fact: RejectedFact,
    index: int,
) -> HarnessReviewItemDraft | None:
    if rejected_fact.fact_type != "relation" or rejected_fact.assessment is None:
        return None
    if rejected_fact.assessment.support_band not in _REVIEWABLE_REJECTED_SUPPORT_BANDS:
        return None
    rejected_payload = {
        str(key): cast("JSONValue", to_json_value(value))
        for key, value in rejected_fact.payload.items()
    }
    relation_type = _clean_text(
        rejected_payload.get("relation_type")
        or rejected_payload.get("proposed_claim_type"),
    )
    source_label = _clean_text(
        rejected_payload.get("source_label") or rejected_payload.get("subject_label"),
    )
    target_label = _clean_text(
        rejected_payload.get("target_label") or rejected_payload.get("object_label"),
    )
    if relation_type is None or source_label is None or target_label is None:
        return None
    source_type = _clean_text(rejected_payload.get("source_type")) or "ENTITY"
    target_type = _clean_text(rejected_payload.get("target_type")) or "ENTITY"
    evidence_excerpt = _clean_text(rejected_payload.get("evidence_excerpt")) or (
        rejected_fact.reason.strip()
    )
    evidence_locator = _clean_text(rejected_payload.get("evidence_locator")) or (
        f"document:{document.id}"
    )
    source_anchors = _json_object_value(rejected_payload.get("source_anchors"))
    target_anchors = _json_object_value(rejected_payload.get("target_anchors"))
    confidence = fact_evidence_weight(rejected_fact)
    ranking = rank_candidate_claim(
        confidence=confidence,
        supporting_document_count=1,
        evidence_reference_count=1,
    )
    claim_fingerprint = compute_claim_fingerprint(
        source_label,
        relation_type,
        target_label,
    )
    return HarnessReviewItemDraft(
        review_type="rejected_relation_review",
        source_family=_REVIEW_ITEM_SOURCE_FAMILY,
        source_kind="document_extraction",
        source_key=f"{document.id}:rejected-relation:{index}",
        document_id=document.id,
        title=f"Review rejected relation: {source_label} {relation_type} {target_label}",
        summary=evidence_excerpt,
        priority=(
            "high"
            if rejected_fact.assessment.support_band == SupportBand.STRONG
            else "medium"
        ),
        confidence=confidence,
        ranking_score=ranking.score,
        evidence_bundle=[
            {
                "source_type": document.source_type,
                "locator": evidence_locator,
                "excerpt": evidence_excerpt,
                "relevance": confidence,
            },
        ],
        payload={
            "reason": rejected_fact.reason,
            "fact_type": rejected_fact.fact_type,
            "rejected_fact_payload": rejected_payload,
            "assessment": fact_assessment_payload(rejected_fact),
            "proposal_draft": {
                "proposal_type": "candidate_claim",
                "title": (
                    f"Extracted claim: {source_label} {relation_type} {target_label}"
                ),
                "summary": evidence_excerpt,
                "confidence": confidence,
                "ranking_score": ranking.score,
                "reasoning_path": {
                    "kind": "rejected_relation_review_conversion",
                    "rejected_reason": rejected_fact.reason,
                    "assessment": fact_assessment_payload(rejected_fact),
                },
                "payload": {
                    "proposed_subject": _resolved_or_unresolved_entity_id(
                        label=source_label,
                        graph_match=None,
                    ),
                    "proposed_subject_label": source_label,
                    "proposed_subject_entity_candidate": (
                        _review_item_entity_candidate_payload(
                            entity_type=source_type,
                            label=source_label,
                            anchors=source_anchors,
                            evidence_excerpt=evidence_excerpt,
                            evidence_locator=evidence_locator,
                            rejected_fact=rejected_fact,
                        )
                    ),
                    "proposed_claim_type": relation_type,
                    "proposed_object": _resolved_or_unresolved_entity_id(
                        label=target_label,
                        graph_match=None,
                    ),
                    "proposed_object_label": target_label,
                    "proposed_object_entity_candidate": (
                        _review_item_entity_candidate_payload(
                            entity_type=target_type,
                            label=target_label,
                            anchors=target_anchors,
                            evidence_excerpt=evidence_excerpt,
                            evidence_locator=evidence_locator,
                            rejected_fact=rejected_fact,
                        )
                    ),
                    "evidence_entity_ids": [],
                },
                "metadata": {
                    "document_id": document.id,
                    "document_title": document.title,
                    "document_source_type": document.source_type,
                    "subject_label": source_label,
                    "object_label": target_label,
                    "subject_entity_type": source_type,
                    "object_entity_type": target_type,
                    "subject_anchors": source_anchors,
                    "object_anchors": target_anchors,
                    "assessment": fact_assessment_payload(rejected_fact),
                    **ranking.metadata,
                },
                "claim_fingerprint": claim_fingerprint,
            },
        },
        metadata={
            "document_id": document.id,
            "document_title": document.title,
            "document_source_type": document.source_type,
            "candidate_kind": "rejected_relation_review",
            "assessment": fact_assessment_payload(rejected_fact),
            "relation_type": relation_type,
        },
        review_fingerprint=claim_fingerprint,
    )


def _review_item_entity_candidate_payload(
    *,
    entity_type: str,
    label: str,
    anchors: JSONObject | None,
    evidence_excerpt: str,
    evidence_locator: str,
    rejected_fact: RejectedFact,
) -> JSONObject | None:
    normalized_entity_type = entity_type.strip().upper()
    if normalized_entity_type == "" and not anchors:
        return None
    normalized_anchors = anchors or {}
    identifiers: dict[str, str] = {}
    for key in ("gene_symbol", "hgvs_notation", "hpo_term"):
        value = normalized_anchors.get(key)
        if isinstance(value, str) and value.strip():
            identifiers[key] = value.strip()
    return {
        "entity_type": normalized_entity_type or "ENTITY",
        "label": label,
        "display_label": label,
        "aliases": [label],
        "anchors": normalized_anchors,
        "metadata": {},
        "identifiers": identifiers,
        "evidence_excerpt": evidence_excerpt,
        "evidence_locator": evidence_locator,
        "assessment": fact_assessment_payload(rejected_fact),
    }


def _normalized_phenotype_review_span(raw_value: object) -> str:
    if isinstance(raw_value, str):
        return " ".join(raw_value.split()).strip()
    if not isinstance(raw_value, dict):
        return ""
    text = raw_value.get("text")
    if not isinstance(text, str):
        return ""
    return " ".join(text.split()).strip()


def _build_relation_draft(
    *,
    space_id: UUID,
    document: HarnessDocumentRecord,
    relation: ExtractedRelation,
    graph_api_gateway: GraphTransportBundle,
    entity_index: dict[tuple[str, str], ExtractedEntityCandidate],
    raw_record: JSONObject,
    index: int,
) -> HarnessProposalDraft | None:
    source_label = _clean_text(relation.source_label)
    target_label = _clean_text(relation.target_label)
    if source_label is None or target_label is None:
        return None

    source_candidate = _resolve_relation_entity_candidate(
        relation_type=relation.source_type,
        label=source_label,
        anchors=relation.source_anchors,
        entity_index=entity_index,
    )
    target_candidate = _resolve_relation_entity_candidate(
        relation_type=relation.target_type,
        label=target_label,
        anchors=relation.target_anchors,
        entity_index=entity_index,
    )
    source_match = _resolve_graph_entity(
        space_id=space_id,
        label=source_label,
        graph_api_gateway=graph_api_gateway,
    )
    target_match = _resolve_graph_entity(
        space_id=space_id,
        label=target_label,
        graph_api_gateway=graph_api_gateway,
    )

    source_id = _resolved_or_unresolved_entity_id(
        label=source_label,
        graph_match=source_match,
    )
    target_id = _resolved_or_unresolved_entity_id(
        label=target_label,
        graph_match=target_match,
    )
    confidence = fact_evidence_weight(relation)
    ranking = rank_candidate_claim(
        confidence=confidence,
        supporting_document_count=1,
        evidence_reference_count=1,
    )
    resolved_source_label = (
        cast("str", source_match["display_label"])
        if source_match is not None
        and isinstance(source_match.get("display_label"), str)
        else source_label
    )
    resolved_target_label = (
        cast("str", target_match["display_label"])
        if target_match is not None
        and isinstance(target_match.get("display_label"), str)
        else target_label
    )
    claim_fingerprint = compute_claim_fingerprint(
        resolved_source_label,
        relation.relation_type,
        resolved_target_label,
    )
    source_document_ref = (
        cast("str", raw_record["document_id"])
        if isinstance(raw_record.get("document_id"), str)
        else document.id
    )
    summary = (
        relation.evidence_excerpt
        or relation.claim_text
        or f"{source_label} {relation.relation_type} {target_label}"
    )
    return HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key=f"{document.id}:relation:{index}",
        document_id=document.id,
        title=f"Extracted claim: {source_label} {relation.relation_type} {target_label}",
        summary=summary,
        confidence=confidence,
        ranking_score=ranking.score,
        reasoning_path={
            "kind": "relation_candidate",
            "source_type": relation.source_type,
            "target_type": relation.target_type,
            "source_label": source_label,
            "target_label": target_label,
            "claim_text": relation.claim_text,
            "evidence_locator": relation.evidence_locator,
            "assessment": fact_assessment_payload(relation),
            "source_anchors": relation.source_anchors,
            "target_anchors": relation.target_anchors,
        },
        evidence_bundle=[
            {
                "source_type": document.source_type,
                "locator": relation.evidence_locator
                or f"document:{source_document_ref}",
                "excerpt": summary,
                "relevance": confidence,
            },
        ],
        payload={
            "proposed_subject": source_id,
            "proposed_subject_label": source_label,
            "proposed_subject_entity_candidate": (
                _entity_candidate_payload(source_candidate)
                if source_candidate is not None
                else None
            ),
            "proposed_claim_type": relation.relation_type,
            "proposed_object": target_id,
            "proposed_object_label": target_label,
            "proposed_object_entity_candidate": (
                _entity_candidate_payload(target_candidate)
                if target_candidate is not None
                else None
            ),
            "evidence_entity_ids": [
                value
                for value in (source_id, target_id)
                if not value.startswith("unresolved:")
            ],
        },
        metadata={
            "document_id": document.id,
            "document_title": document.title,
            "document_source_type": document.source_type,
            "subject_label": source_label,
            "object_label": target_label,
            "resolved_subject_label": resolved_source_label,
            "resolved_object_label": resolved_target_label,
            "subject_resolved": source_match is not None,
            "object_resolved": target_match is not None,
            "subject_entity_type": relation.source_type,
            "object_entity_type": relation.target_type,
            "subject_anchors": relation.source_anchors,
            "object_anchors": relation.target_anchors,
            "assessment": fact_assessment_payload(relation),
            **ranking.metadata,
        },
        claim_fingerprint=claim_fingerprint,
    )


def _resolve_relation_entity_candidate(
    *,
    relation_type: str,
    label: str,
    anchors: JSONObject,
    entity_index: dict[tuple[str, str], ExtractedEntityCandidate],
) -> ExtractedEntityCandidate | None:
    normalized_type = relation_type.strip().upper()
    if anchors:
        gene_symbol = _normalized_string(anchors.get("gene_symbol"))
        hgvs_notation = _normalized_string(anchors.get("hgvs_notation"))
        if gene_symbol is not None and hgvs_notation is not None:
            for candidate in entity_index.values():
                if candidate.entity_type.strip().upper() != normalized_type:
                    continue
                if (
                    _normalized_string(candidate.anchors.get("gene_symbol"))
                    == gene_symbol
                    and _normalized_string(candidate.anchors.get("hgvs_notation"))
                    == hgvs_notation
                ):
                    return candidate
    return entity_index.get((normalized_type, label.strip().lower()))


def _resolve_graph_entity(
    *,
    space_id: UUID,
    label: str,
    graph_api_gateway: GraphTransportBundle,
) -> JSONObject | None:
    try:
        response = graph_api_gateway.list_entities(space_id=space_id, q=label, limit=5)
    except GraphServiceClientError:
        return None
    normalized_label = label.strip().casefold()
    for entity in response.entities:
        display_label = entity.display_label or ""
        aliases = {alias.casefold() for alias in entity.aliases}
        if display_label.casefold() == normalized_label or normalized_label in aliases:
            return {
                "id": str(entity.id),
                "display_label": display_label or str(entity.id),
            }
    return None


def _resolved_or_unresolved_entity_id(
    *,
    label: str,
    graph_match: JSONObject | None,
) -> str:
    if graph_match is not None:
        resolved_id = graph_match.get("id")
        if isinstance(resolved_id, str) and resolved_id.strip():
            return resolved_id
    normalized = "".join(
        character.lower() if character.isalnum() else "_" for character in label.strip()
    ).strip("_")
    return f"unresolved:{normalized or 'entity'}"


def _entity_candidate_payload(
    candidate: ExtractedEntityCandidate,
) -> JSONObject:
    identifiers: dict[str, str] = {}
    for key in ("gene_symbol", "hgvs_notation", "hpo_term"):
        value = candidate.anchors.get(key)
        if isinstance(value, str) and value.strip():
            identifiers[key] = value.strip()
    return {
        "entity_type": candidate.entity_type.strip().upper(),
        "label": candidate.label.strip(),
        "display_label": candidate.label.strip(),
        "aliases": _entity_candidate_aliases(candidate),
        "anchors": {
            str(key): cast("JSONValue", to_json_value(value))
            for key, value in candidate.anchors.items()
        },
        "metadata": {
            str(key): cast("JSONValue", to_json_value(value))
            for key, value in candidate.metadata.items()
        },
        "identifiers": identifiers,
        "evidence_excerpt": candidate.evidence_excerpt,
        "evidence_locator": candidate.evidence_locator,
        "assessment": fact_assessment_payload(candidate),
    }


def _entity_candidate_aliases(
    candidate: ExtractedEntityCandidate,
) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for raw_value in (
        candidate.metadata.get("hgvs_protein"),
        candidate.metadata.get("hgvs_cdna"),
        candidate.metadata.get("hgvs_genomic"),
        candidate.label,
    ):
        if not isinstance(raw_value, str) or not raw_value.strip():
            continue
        normalized = raw_value.strip()
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        aliases.append(normalized)
    transcript = candidate.metadata.get("transcript")
    hgvs_notation = candidate.anchors.get("hgvs_notation")
    hgvs_protein = candidate.metadata.get("hgvs_protein")
    if (
        isinstance(transcript, str)
        and transcript.strip()
        and isinstance(
            hgvs_notation,
            str,
        )
        and hgvs_notation.strip()
    ):
        for value in (
            f"{transcript.strip()}:{hgvs_notation.strip()}",
            (
                f"{transcript.strip()}:{hgvs_notation.strip()} ({hgvs_protein.strip()})"
                if isinstance(hgvs_protein, str) and hgvs_protein.strip()
                else None
            ),
        ):
            if value is None:
                continue
            key = value.casefold()
            if key in seen:
                continue
            seen.add(key)
            aliases.append(value)
    for protein_alias in _protein_aliases(hgvs_protein):
        key = protein_alias.casefold()
        if key in seen:
            continue
        seen.add(key)
        aliases.append(protein_alias)
    return aliases


def _variant_candidate_is_persistable(
    candidate: ExtractedEntityCandidate,
) -> bool:
    return all(
        isinstance(candidate.anchors.get(key), str) and candidate.anchors[key].strip()
        for key in _REQUIRED_VARIANT_ANCHORS
    )


def _normalized_string(raw_value: object) -> str | None:
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    return normalized.lower() if normalized else None


def _clean_text(raw_value: object) -> str | None:
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    return normalized if normalized else None


def _json_object_value(raw_value: object) -> JSONObject | None:
    if not isinstance(raw_value, dict):
        return None
    return {
        str(key): cast("JSONValue", to_json_value(value))
        for key, value in raw_value.items()
    }


def _normalized_metadata_value(raw_value: object) -> JSONValue | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, str):
        normalized = raw_value.strip()
        return normalized if normalized else None
    if isinstance(raw_value, list):
        normalized_list = [
            cast("JSONValue", to_json_value(item))
            for item in raw_value
            if item is not None and (not isinstance(item, str) or item.strip())
        ]
        return normalized_list if normalized_list else None
    return cast("JSONValue", to_json_value(raw_value))


def _protein_aliases(raw_value: object) -> tuple[str, ...]:
    if not isinstance(raw_value, str):
        return ()
    normalized = raw_value.strip()
    if not normalized:
        return ()
    stripped = normalized.removeprefix("p.")
    aliases: list[str] = []
    if stripped and stripped != normalized:
        aliases.append(stripped)
    short_alias = _short_protein_alias(stripped)
    if short_alias is not None:
        aliases.append(short_alias)
    return tuple(aliases)


def _short_protein_alias(protein_label: str) -> str | None:
    if len(protein_label) < _MIN_PROTEIN_ALIAS_LENGTH:
        return None
    prefix = protein_label[:3]
    suffix = protein_label[-3:]
    residue_index = protein_label[3:-3]
    if not residue_index.isdigit():
        return None
    start_code = _THREE_TO_ONE_AMINO_ACID_CODES.get(prefix)
    end_code = _THREE_TO_ONE_AMINO_ACID_CODES.get(suffix)
    if start_code is None or end_code is None:
        return None
    return f"{start_code}{residue_index}{end_code}"


__all__ = [
    "VariantAwareDocumentExtractionResult",
    "document_supports_variant_aware_extraction",
    "extract_variant_aware_document",
]
