"""Fallback and selection helpers for extraction adapter orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from src.application.agents.services._fact_assessment_scoring import (
    fact_evidence_weight,
    run_confidence_from_assessments,
)
from src.domain.agents.contracts import (
    EvidenceItem,
    ExtractedEntityCandidate,
    ExtractedObservation,
    ExtractedRelation,
    ExtractionContract,
    RejectedFact,
)
from src.domain.agents.contracts.assessment_compat import (
    confidence_from_extraction_contract,
)
from src.domain.agents.contracts.fact_assessment import (
    FactAssessment,
    GroundingLevel,
    MappingStatus,
    SpeculationLevel,
    build_fact_assessment_from_confidence,
)
from src.infrastructure.ingestion.types import NormalizedObservation
from src.infrastructure.ingestion.validation.observation_validator import (
    ObservationValidator,
)
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from collections.abc import Mapping

    from artana_evidence_db.semantic_ports import DictionaryPort

    from src.domain.agents.contexts.extraction_context import ExtractionContext
    from src.domain.agents.graph_domain_ai_contracts import ExtractionHeuristicConfig


def is_heuristic_extraction_contract(contract: ExtractionContract) -> bool:
    rationale = contract.rationale.strip().lower()
    return rationale.startswith("heuristic ")


def select_preferred_extraction_contract(
    primary_output: ExtractionContract,
    retry_output: ExtractionContract,
) -> ExtractionContract:
    primary_is_heuristic = is_heuristic_extraction_contract(primary_output)
    retry_is_heuristic = is_heuristic_extraction_contract(retry_output)
    if primary_is_heuristic and not retry_is_heuristic:
        return retry_output
    if retry_is_heuristic and not primary_is_heuristic:
        return primary_output
    if _extraction_signal_score(retry_output) > _extraction_signal_score(
        primary_output,
    ):
        return retry_output
    return primary_output


def _relation_rejection_count(contract: ExtractionContract) -> int:
    return sum(
        1
        for rejected_fact in contract.rejected_facts
        if rejected_fact.fact_type == "relation"
    )


def _extraction_signal_score(contract: ExtractionContract) -> tuple[int, float]:
    relation_count = len(contract.relations)
    observation_count = len(contract.observations)
    relation_rejections = _relation_rejection_count(contract)
    return (
        relation_count * 4 + observation_count * 2 + relation_rejections,
        confidence_from_extraction_contract(contract),
    )


def _build_observation_assessment(confidence: float) -> FactAssessment:
    return build_fact_assessment_from_confidence(
        confidence,
        confidence_rationale="Heuristic observation fallback derived from recognized observation candidates.",
        grounding_level=GroundingLevel.DOCUMENT,
        mapping_status=MappingStatus.RESOLVED,
        speculation_level=SpeculationLevel.DIRECT,
    )


def _build_relation_assessment(confidence: float) -> FactAssessment:
    return build_fact_assessment_from_confidence(
        confidence,
        confidence_rationale="Heuristic relation fallback derived from recognized entity candidates.",
        grounding_level=GroundingLevel.DOCUMENT,
        mapping_status=MappingStatus.RESOLVED,
        speculation_level=SpeculationLevel.HEDGED,
    )


def _build_entity_assessment(confidence: float) -> FactAssessment:
    return build_fact_assessment_from_confidence(
        confidence,
        confidence_rationale=(
            "Deterministic genomics signal parsed before extraction synthesis."
        ),
        grounding_level=GroundingLevel.SPAN,
        mapping_status=MappingStatus.RESOLVED,
        speculation_level=SpeculationLevel.DIRECT,
    )


def build_heuristic_extraction_contract(
    context: ExtractionContext,
    *,
    fallback_config: ExtractionHeuristicConfig,
    dictionary_service: DictionaryPort | None,
    agent_run_id: str | None,
    decision: Literal["generated", "fallback", "escalate"],
) -> ExtractionContract:
    observations: list[ExtractedObservation] = []
    entities = _build_signal_entity_candidates(context)
    rejected_facts: list[RejectedFact] = []

    for candidate in context.recognized_observations:
        variable_id = _resolve_variable_id(
            explicit_variable_id=candidate.variable_id,
            field_name=candidate.field_name,
            dictionary_service=dictionary_service,
        )
        if variable_id is None:
            rejected_facts.append(
                RejectedFact(
                    fact_type="observation",
                    reason="No variable mapping available",
                    payload={"field_name": candidate.field_name},
                ),
            )
            continue

        if not _is_observation_valid(
            variable_id=variable_id,
            value=candidate.value,
            unit=candidate.unit,
            dictionary_service=dictionary_service,
        ):
            rejected_facts.append(
                RejectedFact(
                    fact_type="observation",
                    reason="Observation failed dictionary validation",
                    payload={
                        "field_name": candidate.field_name,
                        "variable_id": variable_id,
                    },
                ),
            )
            continue

        observations.append(
            ExtractedObservation(
                field_name=candidate.field_name,
                variable_id=variable_id,
                value=to_json_value(candidate.value),
                unit=candidate.unit,
                assessment=_build_observation_assessment(candidate.confidence),
            ),
        )

    relations: list[ExtractedRelation] = []
    variant_entity = next(
        (
            entity
            for entity in context.recognized_entities
            if entity.entity_type.strip().upper() == "VARIANT"
        ),
        None,
    )
    phenotype_entity = next(
        (
            entity
            for entity in context.recognized_entities
            if entity.entity_type.strip().upper() == "PHENOTYPE"
        ),
        None,
    )
    claim_text = _best_claim_text_from_record(
        context.raw_record,
        fallback_config=fallback_config,
    )
    signal_variant_entity = next(
        (
            entity
            for entity in entities
            if entity.entity_type.strip().upper() == "VARIANT"
        ),
        None,
    )
    variant_context_requires_review = (
        bool(
            context.genomics_signals.get("variant_aware_recommended"),
        )
        and signal_variant_entity is None
    )
    if variant_entity and phenotype_entity and not variant_context_requires_review:
        heuristic_relation = fallback_config.relation_when_variant_and_phenotype_present
        relation_allowed = _is_relation_allowed(
            source_type=heuristic_relation.source_type,
            relation_type=heuristic_relation.relation_type,
            target_type=heuristic_relation.target_type,
            dictionary_service=dictionary_service,
        )
        if relation_allowed:
            relations.append(
                ExtractedRelation(
                    source_type=heuristic_relation.source_type,
                    relation_type=heuristic_relation.relation_type,
                    target_type=heuristic_relation.target_type,
                    polarity=heuristic_relation.polarity,
                    claim_text=claim_text,
                    claim_section=None,
                    source_label=(
                        signal_variant_entity.label
                        if signal_variant_entity is not None
                        else variant_entity.display_label
                    ),
                    source_anchors=(
                        signal_variant_entity.anchors
                        if signal_variant_entity is not None
                        else {
                            str(key): to_json_value(value)
                            for key, value in variant_entity.identifiers.items()
                        }
                    ),
                    target_label=phenotype_entity.display_label,
                    target_anchors={
                        **{
                            str(key): to_json_value(value)
                            for key, value in phenotype_entity.identifiers.items()
                        },
                        "display_label": phenotype_entity.display_label,
                    },
                    assessment=_build_relation_assessment(
                        min(
                            (
                                signal_variant_entity.confidence
                                if signal_variant_entity is not None
                                else variant_entity.confidence
                            ),
                            phenotype_entity.confidence,
                        ),
                    ),
                ),
            )
        else:
            rejected_facts.append(
                RejectedFact(
                    fact_type="relation",
                    reason="Relation triple not allowed by dictionary constraints",
                    payload={
                        "source_type": heuristic_relation.source_type,
                        "relation_type": heuristic_relation.relation_type,
                        "target_type": heuristic_relation.target_type,
                    },
                ),
            )
    elif variant_context_requires_review:
        rejected_facts.append(
            RejectedFact(
                fact_type="relation",
                reason="Variant-rich context requires anchored variant review",
                payload={
                    "reason": "variant_context_incomplete_requires_review",
                    "genomics_signals": to_json_value(context.genomics_signals),
                },
            ),
        )

    pipeline_payload = {
        str(key): to_json_value(value) for key, value in context.raw_record.items()
    }
    if observations:
        for observation in observations:
            pipeline_payload[observation.field_name] = to_json_value(observation.value)

    evidence = [
        EvidenceItem(
            source_type="db",
            locator=f"source_document:{context.document_id}",
            excerpt="Deterministic extraction fallback mapped recognized candidates",
            relevance=0.75 if observations else 0.4,
        ),
    ]
    resolved_decision: Literal["generated", "fallback", "escalate"] = (
        "generated" if observations or relations else decision
    )
    confidence = run_confidence_from_assessments(
        (
            *(fact_evidence_weight(observation) for observation in observations),
            *(fact_evidence_weight(relation) for relation in relations),
        ),
    )
    if confidence == 0.0 and not observations and not relations:
        confidence = 0.4

    return ExtractionContract(
        decision=resolved_decision,
        confidence_score=confidence,
        rationale="Heuristic extraction fallback executed",
        evidence=evidence,
        source_type=context.source_type,
        document_id=context.document_id,
        entities=entities,
        observations=observations,
        relations=relations,
        rejected_facts=rejected_facts,
        pipeline_payloads=[pipeline_payload] if pipeline_payload else [],
        shadow_mode=context.shadow_mode,
        agent_run_id=agent_run_id,
    )


def _resolve_variable_id(
    *,
    explicit_variable_id: str | None,
    field_name: str,
    dictionary_service: DictionaryPort | None,
) -> str | None:
    if isinstance(explicit_variable_id, str) and explicit_variable_id.strip():
        return explicit_variable_id.strip()
    if dictionary_service is None:
        return None
    resolved = dictionary_service.resolve_synonym(field_name)
    if resolved is None:
        return None
    return resolved.id


def _build_signal_entity_candidates(
    context: ExtractionContext,
) -> list[ExtractedEntityCandidate]:
    raw_candidates = context.genomics_signals.get("variant_candidates")
    if not isinstance(raw_candidates, list):
        return []
    entities: list[ExtractedEntityCandidate] = []
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, dict):
            continue
        gene_symbol = raw_candidate.get("gene_symbol")
        hgvs_notation = raw_candidate.get("hgvs_notation")
        if not isinstance(gene_symbol, str) or not gene_symbol.strip():
            continue
        if not isinstance(hgvs_notation, str) or not hgvs_notation.strip():
            continue
        metadata = raw_candidate.get("metadata")
        anchors = raw_candidate.get("anchors")
        evidence_excerpt = raw_candidate.get("evidence_excerpt")
        evidence_locator = raw_candidate.get("evidence_locator")
        if not isinstance(metadata, dict) or not isinstance(anchors, dict):
            continue
        if not isinstance(evidence_excerpt, str) or not evidence_excerpt.strip():
            continue
        if not isinstance(evidence_locator, str) or not evidence_locator.strip():
            continue
        label = hgvs_notation.strip()
        entities.append(
            ExtractedEntityCandidate(
                entity_type="VARIANT",
                label=label,
                anchors={
                    str(key): to_json_value(value) for key, value in anchors.items()
                },
                metadata={
                    str(key): to_json_value(value) for key, value in metadata.items()
                },
                evidence_excerpt=evidence_excerpt.strip(),
                evidence_locator=evidence_locator.strip(),
                assessment=_build_entity_assessment(0.9),
            ),
        )
    return entities


def _best_claim_text_from_record(
    raw_record: Mapping[str, object],
    *,
    fallback_config: ExtractionHeuristicConfig,
) -> str | None:
    for field_name in fallback_config.claim_text_fields:
        value = raw_record.get(field_name)
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if not normalized:
            continue
        return normalized[:2000]
    return None


def _is_observation_valid(
    *,
    variable_id: str,
    value: object,
    unit: str | None,
    dictionary_service: DictionaryPort | None,
) -> bool:
    if dictionary_service is None:
        return True
    validator = ObservationValidator(dictionary_service)
    validated = validator.validate(
        NormalizedObservation(
            subject_anchor={},
            variable_id=variable_id,
            value=to_json_value(value),
            unit=unit,
            observed_at=None,
            provenance={},
        ),
    )
    return validated is not None


def _is_relation_allowed(
    *,
    source_type: str,
    relation_type: str,
    target_type: str,
    dictionary_service: DictionaryPort | None,
) -> bool:
    if dictionary_service is None:
        return True
    return dictionary_service.is_relation_allowed(
        source_type=source_type,
        relation_type=relation_type,
        target_type=target_type,
    )
