"""Fallback and selection helpers for entity-recognition adapter orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from src.domain.agents.contracts import (
    EntityRecognitionContract,
    EvidenceItem,
    RecognizedEntityCandidate,
    RecognizedObservationCandidate,
)
from src.domain.agents.contracts.recognition_assessment import (
    AmbiguityStatus,
    BoundaryQuality,
    NormalizationStatus,
    RecognitionAssessment,
    RecognitionBand,
)
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from src.domain.agents.contexts.entity_recognition_context import (
        EntityRecognitionContext,
    )
    from src.domain.agents.graph_domain_ai_contracts import (
        EntityRecognitionHeuristicFieldMap,
    )
    from src.type_definitions.common import JSONObject


def is_heuristic_entity_recognition_contract(
    contract: EntityRecognitionContract,
) -> bool:
    rationale = contract.rationale.strip().lower()
    return rationale.startswith("heuristic ")


def select_preferred_entity_recognition_contract(
    primary_output: EntityRecognitionContract,
    retry_output: EntityRecognitionContract,
) -> EntityRecognitionContract:
    primary_is_heuristic = is_heuristic_entity_recognition_contract(primary_output)
    retry_is_heuristic = is_heuristic_entity_recognition_contract(retry_output)
    if primary_is_heuristic and not retry_is_heuristic:
        return retry_output
    if retry_is_heuristic and not primary_is_heuristic:
        return primary_output
    if _entity_signal_score(retry_output) > _entity_signal_score(primary_output):
        return retry_output
    return primary_output


def _entity_signal_score(
    contract: EntityRecognitionContract,
) -> tuple[int, float, float]:
    entity_count = len(contract.recognized_entities)
    observation_count = len(contract.recognized_observations)
    item_confidences = [
        candidate.confidence for candidate in contract.recognized_entities
    ] + [candidate.confidence for candidate in contract.recognized_observations]
    average_item_confidence = (
        sum(item_confidences) / len(item_confidences)
        if item_confidences
        else contract.confidence_score
    )
    return (
        entity_count * 3 + observation_count,
        average_item_confidence,
        contract.confidence_score,
    )


def build_heuristic_entity_recognition_contract(
    context: EntityRecognitionContext,
    *,
    fallback_config: EntityRecognitionHeuristicFieldMap,
    agent_run_id: str | None,
    decision: Literal["generated", "fallback", "escalate"],
) -> EntityRecognitionContract:
    source_type = context.source_type.strip().lower()
    raw_record = dict(context.raw_record)
    field_candidates = [
        str(key)
        for key, value in raw_record.items()
        if isinstance(value, str | int | float | bool)
    ]

    entities: list[RecognizedEntityCandidate] = []
    variant_label = _extract_scalar(
        raw_record,
        fallback_config.field_keys_for(source_type, "variant"),
    )
    if variant_label:
        entities.append(
            RecognizedEntityCandidate(
                entity_type="VARIANT",
                display_label=variant_label,
                identifiers={"variant_id": variant_label},
                assessment=RecognitionAssessment(
                    recognition_band=RecognitionBand.STRONG,
                    boundary_quality=BoundaryQuality.CLEAR,
                    normalization_status=NormalizationStatus.RESOLVED,
                    ambiguity_status=AmbiguityStatus.CLEAR,
                    confidence_rationale=(
                        "Variant identifier is explicit in the source record."
                    ),
                ),
            ),
        )

    gene_label = _extract_scalar(
        raw_record,
        fallback_config.field_keys_for(source_type, "gene"),
    )
    if gene_label:
        entities.append(
            RecognizedEntityCandidate(
                entity_type="GENE",
                display_label=gene_label,
                identifiers={"gene_symbol": gene_label},
                assessment=RecognitionAssessment(
                    recognition_band=RecognitionBand.SUPPORTED,
                    boundary_quality=BoundaryQuality.CLEAR,
                    normalization_status=NormalizationStatus.RESOLVED,
                    ambiguity_status=AmbiguityStatus.CLEAR,
                    confidence_rationale=(
                        "Gene symbol is directly grounded in the source record."
                    ),
                ),
            ),
        )

    phenotype_label = _extract_scalar(
        raw_record,
        fallback_config.field_keys_for(source_type, "phenotype"),
    )
    if phenotype_label:
        entities.append(
            RecognizedEntityCandidate(
                entity_type="PHENOTYPE",
                display_label=phenotype_label,
                identifiers={"label": phenotype_label},
                assessment=RecognitionAssessment(
                    recognition_band=RecognitionBand.TENTATIVE,
                    boundary_quality=BoundaryQuality.PARTIAL,
                    normalization_status=NormalizationStatus.PARTIAL,
                    ambiguity_status=AmbiguityStatus.SOME_AMBIGUITY,
                    confidence_rationale=(
                        "Phenotype label is present but may need normalization."
                    ),
                ),
            ),
        )

    publication_label = _extract_scalar(
        raw_record,
        fallback_config.field_keys_for(source_type, "publication"),
    )
    if publication_label:
        entities.append(
            RecognizedEntityCandidate(
                entity_type="PUBLICATION",
                display_label=publication_label,
                identifiers={"publication_ref": publication_label},
                assessment=RecognitionAssessment(
                    recognition_band=RecognitionBand.SUPPORTED,
                    boundary_quality=BoundaryQuality.CLEAR,
                    normalization_status=NormalizationStatus.NOT_APPLICABLE,
                    ambiguity_status=AmbiguityStatus.NOT_APPLICABLE,
                    confidence_rationale=(
                        "Publication reference is directly grounded in metadata."
                    ),
                ),
            ),
        )

    observations: list[RecognizedObservationCandidate] = []
    for field_name in field_candidates:
        value = raw_record.get(field_name)
        if value is None:
            continue
        json_value = to_json_value(value)
        observations.append(
            RecognizedObservationCandidate(
                field_name=field_name,
                value=json_value,
                assessment=RecognitionAssessment(
                    recognition_band=RecognitionBand.SUPPORTED,
                    boundary_quality=BoundaryQuality.CLEAR,
                    normalization_status=NormalizationStatus.RESOLVED,
                    ambiguity_status=AmbiguityStatus.CLEAR,
                    confidence_rationale=(
                        f"Observed field '{field_name}' is directly present in the source."
                    ),
                ),
            ),
        )

    pipeline_payload = {
        str(key): to_json_value(value) for key, value in raw_record.items()
    }
    evidence = [
        EvidenceItem(
            source_type="db",
            locator=f"source_document:{context.document_id}",
            excerpt="Deterministic fallback parsed raw_record fields",
            relevance=0.7 if entities else 0.4,
        ),
    ]
    resolved_decision: Literal["generated", "fallback", "escalate"] = (
        "generated" if entities else decision
    )
    confidence = 0.78 if entities else 0.4

    return EntityRecognitionContract(
        decision=resolved_decision,
        confidence_score=confidence,
        rationale=f"Heuristic {source_type} parsing fallback executed",
        evidence=evidence,
        source_type=context.source_type,
        document_id=context.document_id,
        primary_entity_type=(
            entities[0].entity_type
            if entities
            else fallback_config.primary_entity_type_for(source_type)
        ),
        field_candidates=field_candidates,
        recognized_entities=entities,
        recognized_observations=observations,
        pipeline_payloads=[pipeline_payload] if pipeline_payload else [],
        shadow_mode=context.shadow_mode,
        agent_run_id=agent_run_id,
    )


def _extract_scalar(raw_record: JSONObject, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = raw_record.get(key)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
        if isinstance(value, int | float):
            return str(value)
    return None
