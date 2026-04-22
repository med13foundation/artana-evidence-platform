"""DrugBank-specific extraction processor for queued DrugBank records.

Implements the two-tier connector architecture:
- Tier 1: Deterministic grounding of structured DrugBank fields into entities
- Tier 2: Claim generation stubs for DRUG->TARGETS->GENE/PROTEIN and
          DRUG->TREATS->DISEASE relation claims
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
from src.infrastructure.extraction.drugbank_record_helpers import (
    dedupe_strings as _dedupe_strings,
)
from src.infrastructure.extraction.drugbank_record_helpers import (
    extract_string_list as _extract_string_list,
)
from src.infrastructure.extraction.drugbank_record_helpers import (
    first_scalar as _first_scalar,
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
# Source type constant
# ---------------------------------------------------------------------------

DRUGBANK_SOURCE_TYPE = "drugbank"

# ---------------------------------------------------------------------------
# Tier 1 data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DrugBankRecord:
    """Parsed representation of a DrugBank source record."""

    drugbank_id: str
    name: str
    description: str | None = None
    targets: list[str] = field(default_factory=list)
    mechanisms: list[str] = field(default_factory=list)
    interactions: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    synonyms: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DrugBankGroundingResult:
    """Tier 1 grounding output for a single DrugBank record."""

    drug_entity: _DrugEntity
    target_entities: list[_TargetEntity]
    mechanism_claims: list[_MechanismClaim]
    provenance: _GroundingProvenance


@dataclass(frozen=True)
class _DrugEntity:
    name: str
    drugbank_id: str
    aliases: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _TargetEntity:
    name: str
    normalized_id: str | None = None
    entity_type: str = "GENE"  # GENE or PROTEIN


@dataclass(frozen=True)
class _MechanismClaim:
    mechanism_text: str
    drug_name: str


@dataclass(frozen=True)
class _GroundingProvenance:
    source: str = DRUGBANK_SOURCE_TYPE
    processor_name: str = "drugbank_contract_v1"
    record_id: str | None = None


# ---------------------------------------------------------------------------
# Tier 1: deterministic grounding
# ---------------------------------------------------------------------------


def parse_drugbank_record(raw: JSONObject) -> DrugBankRecord | None:
    """Parse a raw JSON record into a structured DrugBankRecord."""
    drugbank_id = _first_scalar(raw, ("drugbank_id", "id", "accession"))
    name = _first_scalar(raw, ("name", "drug_name", "generic_name"))
    if not drugbank_id or not name:
        return None
    description = _first_scalar(raw, ("description", "summary"))
    targets = _extract_string_list(raw, ("targets", "target_genes", "target_proteins"))
    mechanisms = _extract_string_list(
        raw,
        ("mechanisms", "mechanism_of_action", "pharmacodynamics"),
    )
    interactions = _extract_string_list(
        raw,
        ("interactions", "drug_interactions"),
    )
    categories = _extract_string_list(raw, ("categories", "atc_codes"))
    synonyms = _dedupe_strings(
        [
            drugbank_id,
            name,
            *_extract_string_list(raw, ("generic_name",)),
            *_extract_string_list(raw, ("synonyms", "aliases")),
            *_extract_string_list(raw, ("brand_names",)),
            *_extract_string_list(raw, ("product_names", "products")),
        ],
    )
    return DrugBankRecord(
        drugbank_id=drugbank_id,
        name=name,
        description=description,
        targets=targets,
        mechanisms=mechanisms,
        interactions=interactions,
        categories=categories,
        synonyms=synonyms,
    )


def ground_drugbank_record(record: DrugBankRecord) -> DrugBankGroundingResult:
    """Tier 1: deterministic grounding of a parsed DrugBank record."""
    drug_entity = _DrugEntity(
        name=record.name,
        drugbank_id=record.drugbank_id,
        aliases=record.synonyms or [record.drugbank_id],
    )

    target_entities: list[_TargetEntity] = []
    for target_name in record.targets:
        normalized = target_name.strip().upper()
        if not normalized:
            continue
        target_entities.append(
            _TargetEntity(name=target_name.strip(), normalized_id=normalized),
        )

    mechanism_claims: list[_MechanismClaim] = []
    for mechanism in record.mechanisms:
        mechanism_text = mechanism.strip()
        if mechanism_text:
            mechanism_claims.append(
                _MechanismClaim(mechanism_text=mechanism_text, drug_name=record.name),
            )

    provenance = _GroundingProvenance(
        source=DRUGBANK_SOURCE_TYPE,
        processor_name="drugbank_contract_v1",
        record_id=record.drugbank_id,
    )

    return DrugBankGroundingResult(
        drug_entity=drug_entity,
        target_entities=target_entities,
        mechanism_claims=mechanism_claims,
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
    confidence_rationale="Deterministic extraction from structured DrugBank record.",
)


def generate_drugbank_claims(
    record: DrugBankRecord,
    grounding: DrugBankGroundingResult,
) -> ExtractionContract:
    """Tier 2 stub: generate structured claims from grounded DrugBank data.

    Produces DRUG -> TARGETS -> GENE/PROTEIN and DRUG -> TREATS -> DISEASE
    relation claims. Returns the standard ExtractionContract output shape.
    Does not call LLMs.
    """
    relations: list[ExtractedRelation] = []

    # DRUG -> TARGETS -> GENE/PROTEIN
    for target in grounding.target_entities:
        relations.append(  # noqa: PERF401
            ExtractedRelation(
                source_type="DRUG",
                relation_type="TARGETS",
                target_type=target.entity_type,
                polarity="SUPPORT",
                claim_text=f"{record.name} targets {target.name}",
                source_label=record.name,
                target_label=target.name,
                assessment=_SOURCE_BACKED_ASSESSMENT,
            ),
        )

    # DRUG -> TREATS -> DISEASE (from categories that look like disease indications)
    for category in record.categories:
        category_text = category.strip()
        if category_text:
            relations.append(  # noqa: PERF401
                ExtractedRelation(
                    source_type="DRUG",
                    relation_type="TREATS",
                    target_type="DISEASE",
                    polarity="SUPPORT",
                    claim_text=f"{record.name} treats {category_text}",
                    source_label=record.name,
                    target_label=category_text,
                    assessment=_SOURCE_BACKED_ASSESSMENT,
                ),
            )

    return ExtractionContract(
        rationale=(
            f"DrugBank deterministic extraction for {record.drugbank_id} "
            f"({record.name}): {len(relations)} relation claims generated."
        ),
        evidence=[],
        confidence_score=0.85 if relations else 0.0,
        decision="generated" if relations else "fallback",
        source_type=DRUGBANK_SOURCE_TYPE,
        document_id=record.drugbank_id,
        relations=relations,
        observations=[],
        rejected_facts=[],
        shadow_mode=True,
    )


# ---------------------------------------------------------------------------
# ExtractionProcessorPort implementation
# ---------------------------------------------------------------------------


class DrugBankExtractionProcessor(ExtractionProcessorPort):
    """Extract deterministic drug/target/mechanism facts from DrugBank payloads."""

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
                processor_name="drugbank_contract_v1",
                text_source=text_source,
                document_reference=document_reference,
                error_message="missing_raw_record",
            )

        record = parse_drugbank_record(raw_record)
        drugbank_id = _first_scalar(
            raw_record,
            ("drugbank_id", "id", "accession"),
        )

        grounding_context: JSONObject = {}
        if record is not None:
            grounding = ground_drugbank_record(record)
            grounding_context = {
                "drug_name": record.name,
                "drugbank_id": record.drugbank_id,
                "targets": record.targets,
                "mechanisms": record.mechanisms,
                "categories": record.categories,
                "target_count": len(grounding.target_entities),
            }

        success_metadata: JSONObject = {
            "queue_item_id": str(queue_item.id),
            "source_type": queue_item.source_type,
            "source_record_id": queue_item.source_record_id,
            "ai_required": True,
            "reason": "drugbank_tier1_grounding_complete_defer_to_ai_pipeline",
            "drugbank_grounding": grounding_context,
        }
        if publication_id is not None:
            success_metadata["publication_id"] = publication_id
        if drugbank_id:
            success_metadata["drugbank_id"] = drugbank_id

        return ExtractionProcessorResult(
            status="skipped",
            facts=[],
            metadata=success_metadata,
            processor_name="drugbank_contract_v1",
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

    drugbank_id = _first_scalar(raw_record, ("drugbank_id", "id", "accession"))
    name = _first_scalar(raw_record, ("name", "drug_name", "generic_name"))
    targets = _extract_string_list(
        raw_record,
        ("targets", "target_genes", "target_proteins"),
    )
    categories = _extract_string_list(raw_record, ("categories", "atc_codes"))

    if drugbank_id and name:
        accumulator.add_fact(
            "drug",
            name,
            normalized_id=drugbank_id,
            source=DRUGBANK_SOURCE_TYPE,
        )
    elif name:
        accumulator.add_fact(
            "drug",
            name,
            source=DRUGBANK_SOURCE_TYPE,
        )

    for target in targets:
        target_stripped = target.strip()
        if target_stripped:
            accumulator.add_fact(
                "gene",
                target_stripped,
                normalized_id=target_stripped.upper(),
                source=DRUGBANK_SOURCE_TYPE,
            )

    for category in categories:
        category_stripped = category.strip()
        if category_stripped:
            accumulator.add_fact(
                "other",
                category_stripped,
                source=DRUGBANK_SOURCE_TYPE,
                attributes={"dimension": "therapeutic_category"},
            )

    mechanisms = _extract_string_list(
        raw_record,
        ("mechanisms", "mechanism_of_action", "pharmacodynamics"),
    )
    for mechanism in mechanisms:
        mechanism_stripped = mechanism.strip()
        if mechanism_stripped:
            accumulator.add_fact(
                "mechanism",
                mechanism_stripped,
                source=DRUGBANK_SOURCE_TYPE,
            )

    return accumulator.facts, drugbank_id


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
    "DRUGBANK_SOURCE_TYPE",
    "DrugBankExtractionProcessor",
    "DrugBankGroundingResult",
    "DrugBankRecord",
    "generate_drugbank_claims",
    "ground_drugbank_record",
    "parse_drugbank_record",
]
