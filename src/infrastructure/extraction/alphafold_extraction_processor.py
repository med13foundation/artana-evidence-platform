"""AlphaFold extraction processor: Tier 1 grounding + Tier 2 claim stubs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from src.application.services.ports.extraction_processor_port import (
    ExtractionProcessorPort,
    ExtractionProcessorResult,
    ExtractionTextPayload,
)
from src.domain.agents.contracts.extraction import (
    ExtractedRelation,
    ExtractionContract,
)
from src.domain.agents.contracts.fact_assessment import (
    FactAssessment,
    GroundingLevel,
    MappingStatus,
    SpeculationLevel,
    SupportBand,
)
from src.infrastructure.extraction.alphafold_models import (
    ALPHAFOLD_SOURCE_TYPE,
    AlphaFoldDomain,
    AlphaFoldGroundingResult,
    AlphaFoldRecord,
)
from src.infrastructure.extraction.alphafold_models import (
    DomainEntity as _DomainEntity,
)
from src.infrastructure.extraction.alphafold_models import (
    DomainLocationClaim as _DomainLocationClaim,
)
from src.infrastructure.extraction.alphafold_models import (
    GroundingProvenance as _GroundingProvenance,
)
from src.infrastructure.extraction.alphafold_models import (
    ProteinEntity as _ProteinEntity,
)

if TYPE_CHECKING:
    from src.domain.entities.extraction_queue_item import ExtractionQueueItem
    from src.domain.entities.publication import Publication
    from src.type_definitions.common import (
        ExtractionFact,
        ExtractionFactType,
        ExtractionTextSource,
        JSONObject,
    )


# ---------------------------------------------------------------------------
# Tier 1: deterministic grounding
# ---------------------------------------------------------------------------


def parse_alphafold_record(raw: JSONObject) -> AlphaFoldRecord | None:
    """Parse a raw JSON record into a structured AlphaFoldRecord."""
    uniprot_id = _first_scalar(raw, ("uniprot_id", "uniprotId", "accession"))
    protein_name = _first_scalar(raw, ("protein_name", "proteinName", "name"))
    if not uniprot_id or not protein_name:
        return None

    confidence_raw = raw.get("predicted_structure_confidence") or raw.get(
        "plddt_mean",
    )
    predicted_structure_confidence = 0.0
    if isinstance(confidence_raw, int | float):
        predicted_structure_confidence = float(confidence_raw)

    domains: list[AlphaFoldDomain] = []
    raw_domains = raw.get("domains")
    if isinstance(raw_domains, list):
        for entry in raw_domains:
            if not isinstance(entry, dict):
                continue
            domain_name = _first_scalar(entry, ("name", "domain_name", "pfam_name"))
            start_raw = entry.get("start") or entry.get("start_position")
            end_raw = entry.get("end") or entry.get("end_position")
            if (
                not domain_name
                or not isinstance(start_raw, int)
                or not isinstance(
                    end_raw,
                    int,
                )
            ):
                continue
            domain_confidence_raw = entry.get("confidence") or entry.get("plddt")
            domain_confidence = 0.0
            if isinstance(domain_confidence_raw, int | float):
                domain_confidence = float(domain_confidence_raw)
            domains.append(
                AlphaFoldDomain(
                    name=domain_name,
                    start=start_raw,
                    end=end_raw,
                    confidence=domain_confidence,
                ),
            )

    return AlphaFoldRecord(
        uniprot_id=uniprot_id,
        protein_name=protein_name,
        domains=domains,
        predicted_structure_confidence=predicted_structure_confidence,
    )


def ground_alphafold_record(record: AlphaFoldRecord) -> AlphaFoldGroundingResult:
    """Tier 1: deterministic grounding of a parsed AlphaFold record."""
    protein_entity = _ProteinEntity(
        name=record.protein_name,
        uniprot_id=record.uniprot_id,
    )

    domain_entities: list[_DomainEntity] = []
    domain_location_claims: list[_DomainLocationClaim] = []

    for domain in record.domains:
        normalized_id = f"{record.uniprot_id}:{domain.name}:{domain.start}-{domain.end}"
        domain_entities.append(
            _DomainEntity(
                name=domain.name,
                start=domain.start,
                end=domain.end,
                confidence=domain.confidence,
                normalized_id=normalized_id,
            ),
        )
        domain_location_claims.append(
            _DomainLocationClaim(
                domain_name=domain.name,
                protein_name=record.protein_name,
                start=domain.start,
                end=domain.end,
            ),
        )

    provenance = _GroundingProvenance(
        source=ALPHAFOLD_SOURCE_TYPE,
        processor_name="alphafold_contract_v1",
        record_id=record.uniprot_id,
    )

    return AlphaFoldGroundingResult(
        protein_entity=protein_entity,
        domain_entities=domain_entities,
        domain_location_claims=domain_location_claims,
        provenance=provenance,
    )


# ---------------------------------------------------------------------------
# Tier 2: claim generation stubs
# ---------------------------------------------------------------------------

_SOURCE_BACKED_ASSESSMENT = FactAssessment(
    support_band=SupportBand.SUPPORTED,
    grounding_level=GroundingLevel.DOCUMENT,
    mapping_status=MappingStatus.RESOLVED,
    speculation_level=SpeculationLevel.DIRECT,
    confidence_rationale="Deterministic extraction from AlphaFold structural prediction.",
)


def generate_alphafold_claims(
    record: AlphaFoldRecord,
    grounding: AlphaFoldGroundingResult,
) -> ExtractionContract:
    """Tier 2 stub: generate structured claims from grounded AlphaFold data.

    Produces PROTEIN_DOMAIN -> PART_OF -> PROTEIN and
    VARIANT -> LOCATED_IN -> PROTEIN_DOMAIN relation claims.
    Returns the standard ExtractionContract output shape.
    Does not call LLMs.
    """
    relations: list[ExtractedRelation] = []

    # PROTEIN_DOMAIN -> PART_OF -> PROTEIN
    for domain_entity in grounding.domain_entities:
        relations.append(  # noqa: PERF401
            ExtractedRelation(
                source_type="PROTEIN_DOMAIN",
                relation_type="PART_OF",
                target_type="PROTEIN",
                polarity="SUPPORT",
                claim_text=(
                    f"{domain_entity.name} (residues {domain_entity.start}-"
                    f"{domain_entity.end}) is part of {record.protein_name}"
                ),
                source_label=domain_entity.name,
                target_label=record.protein_name,
                assessment=_SOURCE_BACKED_ASSESSMENT,
            ),
        )

    # VARIANT -> LOCATED_IN -> PROTEIN_DOMAIN (stub for future variant mapping)
    # This is a structural stub: when variant records are available, they would
    # be mapped to domain boundaries. We emit one placeholder claim per domain
    # to establish the claim shape.
    for domain_entity in grounding.domain_entities:
        relations.append(  # noqa: PERF401
            ExtractedRelation(
                source_type="VARIANT",
                relation_type="PART_OF",
                target_type="PROTEIN_DOMAIN",
                polarity="SUPPORT",
                claim_text=(
                    f"Variants in residues {domain_entity.start}-{domain_entity.end} "
                    f"are located in {domain_entity.name} of {record.protein_name}"
                ),
                source_label=f"variant_in_{domain_entity.normalized_id}",
                target_label=domain_entity.name,
                assessment=FactAssessment(
                    support_band=SupportBand.TENTATIVE,
                    grounding_level=GroundingLevel.GENERATED,
                    mapping_status=MappingStatus.NOT_APPLICABLE,
                    speculation_level=SpeculationLevel.HYPOTHETICAL,
                    confidence_rationale=(
                        "Structural stub: domain boundary established but no "
                        "specific variant mapped yet."
                    ),
                ),
            ),
        )

    return ExtractionContract(
        rationale=(
            f"AlphaFold deterministic extraction for {record.uniprot_id} "
            f"({record.protein_name}): {len(relations)} relation claims generated."
        ),
        evidence=[],
        confidence_score=0.85 if relations else 0.0,
        decision="generated" if relations else "fallback",
        source_type=ALPHAFOLD_SOURCE_TYPE,
        document_id=record.uniprot_id,
        relations=relations,
        observations=[],
        rejected_facts=[],
        shadow_mode=True,
    )


# ---------------------------------------------------------------------------
# ExtractionProcessorPort implementation
# ---------------------------------------------------------------------------


class AlphaFoldExtractionProcessor(ExtractionProcessorPort):
    """Extract deterministic protein/domain facts from AlphaFold payloads."""

    def extract_publication(
        self,
        *,
        queue_item: ExtractionQueueItem,
        publication: Publication | None,
        text_payload: ExtractionTextPayload | None = None,
    ) -> ExtractionProcessorResult:
        text_source = _resolve_text_source(text_payload)
        document_reference = _resolve_document_reference(text_payload)
        publication_id = publication.id if publication is not None else None

        raw_record = _extract_raw_record(queue_item)
        if raw_record is None:
            failure_metadata: JSONObject = {
                "reason": "missing_raw_record",
                "queue_item_id": str(queue_item.id),
                "source_record_id": queue_item.source_record_id,
            }
            if publication_id is not None:
                failure_metadata["publication_id"] = publication_id
            return ExtractionProcessorResult(
                status="failed",
                facts=[],
                metadata=failure_metadata,
                processor_name="alphafold_contract_v1",
                text_source=text_source,
                document_reference=document_reference,
                error_message="missing_raw_record",
            )

        record = parse_alphafold_record(raw_record)
        uniprot_id = _first_scalar(
            raw_record,
            ("uniprot_id", "uniprotId", "accession"),
        )

        grounding_context: JSONObject = {}
        if record is not None:
            grounding = ground_alphafold_record(record)
            grounding_context = {
                "protein_name": record.protein_name,
                "uniprot_id": record.uniprot_id,
                "predicted_structure_confidence": record.predicted_structure_confidence,
                "domains": [
                    {
                        "name": d.name,
                        "start": d.start,
                        "end": d.end,
                        "confidence": d.confidence,
                    }
                    for d in record.domains
                ],
                "domain_count": len(grounding.domain_entities),
            }

        success_metadata: JSONObject = {
            "queue_item_id": str(queue_item.id),
            "source_type": queue_item.source_type,
            "source_record_id": queue_item.source_record_id,
            "ai_required": True,
            "reason": "alphafold_tier1_grounding_complete_defer_to_ai_pipeline",
            "alphafold_grounding": grounding_context,
        }
        if publication_id is not None:
            success_metadata["publication_id"] = publication_id
        if uniprot_id:
            success_metadata["uniprot_id"] = uniprot_id

        return ExtractionProcessorResult(
            status="skipped",
            facts=[],
            metadata=success_metadata,
            processor_name="alphafold_contract_v1",
            processor_version="1.0",
            text_source=text_source,
            document_reference=document_reference,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_ExtractionProcessorResultStatus = Literal["completed", "failed", "skipped"]


def _extract_raw_record(queue_item: ExtractionQueueItem) -> JSONObject | None:
    raw_record_value = queue_item.metadata.get("raw_record")
    if isinstance(raw_record_value, dict):
        return raw_record_value
    return None


def _resolve_text_source(
    payload: ExtractionTextPayload | None,
) -> ExtractionTextSource:
    if payload is None:
        return "full_text"
    return payload.text_source


def _resolve_document_reference(payload: ExtractionTextPayload | None) -> str | None:
    if payload is None:
        return None
    return payload.document_reference


def _extract_facts(raw_record: JSONObject) -> tuple[list[ExtractionFact], str | None]:
    accumulator = _FactAccumulator()

    uniprot_id = _first_scalar(raw_record, ("uniprot_id", "uniprotId", "accession"))
    protein_name = _first_scalar(raw_record, ("protein_name", "proteinName", "name"))

    if protein_name:
        accumulator.add_fact(
            "gene",
            protein_name,
            normalized_id=uniprot_id,
            source=ALPHAFOLD_SOURCE_TYPE,
            attributes={"entity_type": "PROTEIN"},
        )

    raw_domains = raw_record.get("domains")
    if isinstance(raw_domains, list):
        for entry in raw_domains:
            if not isinstance(entry, dict):
                continue
            domain_name = _first_scalar(entry, ("name", "domain_name", "pfam_name"))
            if domain_name:
                start_raw = entry.get("start") or entry.get("start_position")
                end_raw = entry.get("end") or entry.get("end_position")
                attrs: JSONObject = {"entity_type": "PROTEIN_DOMAIN"}
                if isinstance(start_raw, int):
                    attrs["start"] = start_raw
                if isinstance(end_raw, int):
                    attrs["end"] = end_raw
                normalized_domain_id = None
                if (
                    uniprot_id
                    and isinstance(start_raw, int)
                    and isinstance(
                        end_raw,
                        int,
                    )
                ):
                    normalized_domain_id = (
                        f"{uniprot_id}:{domain_name}:{start_raw}-{end_raw}"
                    )
                accumulator.add_fact(
                    "other",
                    domain_name,
                    normalized_id=normalized_domain_id,
                    source=ALPHAFOLD_SOURCE_TYPE,
                    attributes=attrs,
                )

    return accumulator.facts, uniprot_id


def _first_scalar(payload: JSONObject, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
        if isinstance(value, int):
            return str(value)
    return None


class _FactAccumulator:
    def __init__(self) -> None:
        self.facts: list[ExtractionFact] = []
        self._seen: set[tuple[ExtractionFactType, str, str | None]] = set()

    def add_fact(
        self,
        fact_type: ExtractionFactType,
        value: str,
        *,
        normalized_id: str | None = None,
        source: str | None = None,
        attributes: JSONObject | None = None,
    ) -> None:
        normalized_value = value.strip()
        if not normalized_value:
            return
        key = (fact_type, normalized_value, normalized_id)
        if key in self._seen:
            return
        self._seen.add(key)
        fact: ExtractionFact = {
            "fact_type": fact_type,
            "value": normalized_value,
        }
        if normalized_id:
            fact["normalized_id"] = normalized_id
        if source:
            fact["source"] = source
        if attributes:
            fact["attributes"] = attributes
        self.facts.append(fact)


__all__ = [
    "ALPHAFOLD_SOURCE_TYPE",
    "AlphaFoldDomain",
    "AlphaFoldExtractionProcessor",
    "AlphaFoldGroundingResult",
    "AlphaFoldRecord",
    "generate_alphafold_claims",
    "ground_alphafold_record",
    "parse_alphafold_record",
]
