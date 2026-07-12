"""Unit tests for the variant-aware document extraction bridge."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from artana_evidence_api import variant_extraction_bridges
from artana_evidence_api.document_store import HarnessDocumentRecord
from artana_evidence_api.runtime.agent_output_schema import SourceMeasurementNumber
from artana_evidence_api.types.graph_contracts import (
    KernelEntityListResponse,
)
from artana_evidence_api.types.graph_fact_assessment import (
    FactAssessment,
    GroundingLevel,
    MappingStatus,
    SpeculationLevel,
    SupportBand,
)
from artana_evidence_api.variant_aware_document_extraction import (
    document_supports_variant_aware_extraction,
    extract_variant_aware_document,
)
from artana_evidence_api.variant_extraction_contracts import (
    ExtractedEntityCandidate,
    ExtractedObservation,
    ExtractedRelation,
    ExtractionContract,
    LLMExtractedEntityCandidate,
    LLMExtractedObservation,
    LLMExtractionContract,
    LLMIdentifierField,
    LLMLiteralField,
    LLMRejectedFact,
    RejectedFact,
)


class _FakeKernelStore:
    def __init__(self) -> None:
        self.closed = False
        self.kernel: _FakeKernel | None = None

    async def close(self) -> None:
        self.closed = True


class _FakeKernel:
    def __init__(self, *, store, model_port, **kwargs) -> None:
        del kwargs
        self.store = store
        self.model_port = model_port
        self.closed = False
        store.kernel = self

    async def close(self) -> None:
        self.closed = True


class _FakeSingleStepClient:
    def __init__(self, *, kernel) -> None:
        self.kernel = kernel


class _EmptyGraphGateway:
    def list_entities(
        self,
        *,
        space_id,
        q: str | None = None,
        entity_type: str | None = None,
        ids: list[str] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelEntityListResponse:
        del space_id, q, entity_type, ids, offset, limit
        return KernelEntityListResponse(entities=[], total=0, offset=0, limit=50)


def test_genomics_signal_bundle_limits_deterministic_variant_scan_to_prompt_budget() -> None:
    text = (
        "No variant mention in the bounded prefix. "
        + ("background " * 1300)
        + " MED13 c.977C>T appears only after the deterministic scan limit."
    )

    signals = variant_extraction_bridges.build_genomics_signal_bundle(
        raw_record={"abstract": text},
        source_type="pubmed",
    )

    assert signals["variant_candidates"] == []
    assert signals["variant_aware_recommended"] is False


def _assessment(
    *,
    support_band: SupportBand = SupportBand.STRONG,
    rationale: str = "Exact anchored variant evidence.",
) -> FactAssessment:
    return FactAssessment(
        support_band=support_band,
        grounding_level=GroundingLevel.SPAN,
        mapping_status=MappingStatus.RESOLVED,
        speculation_level=SpeculationLevel.DIRECT,
        confidence_rationale=rationale,
    )


def _llm_variant_subject_anchors() -> list[LLMIdentifierField]:
    return [
        LLMIdentifierField(key="gene_symbol", value="MED13"),
        LLMIdentifierField(key="hgvs_notation", value="c.977C>A"),
    ]


def _llm_source_measurement_observation(
    *,
    value: str,
    literal_span: str,
    unit: str,
    source_hash: str = "source-hash-adversarial",
) -> LLMExtractedObservation:
    return LLMExtractedObservation(
        field_name="source_value",
        variable_id="SOURCE_VALUE",
        value=SourceMeasurementNumber(
            value=value,
            source_locator="raw_record.text",
            literal_span=literal_span,
            field_name="source_value",
            unit=unit,
            extraction_method="literal_copy",
            source_hash=source_hash,
        ),
        unit=unit,
        subject_label="NM_015335.6:c.977C>A (p.Thr326Lys)",
        subject_anchors=_llm_variant_subject_anchors(),
        assessment=_assessment(),
    )


def _document(*, text: str, source_type: str = "text") -> HarnessDocumentRecord:
    now = datetime.now(UTC)
    return HarnessDocumentRecord(
        id=str(uuid4()),
        space_id=str(uuid4()),
        created_by=str(uuid4()),
        title="Synthetic variant-aware note",
        source_type=source_type,
        filename=None,
        media_type="text/plain",
        sha256="deadbeef",
        byte_size=len(text.encode("utf-8")),
        page_count=None,
        text_content=text,
        text_excerpt=text[:80],
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=str(uuid4()),
        last_enrichment_run_id=None,
        last_extraction_run_id=None,
        enrichment_status="not_started",
        extraction_status="not_started",
        metadata={},
        created_at=now,
        updated_at=now,
    )


def _single_variant_contract(*, document_id: str) -> ExtractionContract:
    return ExtractionContract(
        decision="generated",
        confidence_score=0.0,
        rationale="Recovered one anchored variant from the source record.",
        evidence=[],
        source_type="pubmed",
        document_id=document_id,
        entities=[
            ExtractedEntityCandidate(
                entity_type="VARIANT",
                label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                anchors={
                    "gene_symbol": "MED13",
                    "hgvs_notation": "c.977C>A",
                },
                metadata={
                    "transcript": "NM_015335.6",
                    "hgvs_cdna": "c.977C>A",
                    "hgvs_protein": "p.Thr326Lys",
                    "classification": "Likely Pathogenic",
                },
                evidence_excerpt="MED13 NM_015335.6:c.977C>A (p.Thr326Lys)",
                evidence_locator="text_span:10-34",
                assessment=_assessment(),
            ),
        ],
        observations=[],
        relations=[],
        rejected_facts=[],
        pipeline_payloads=[],
        shadow_mode=True,
        agent_run_id="variant-aware-source-test",
    )


def _single_variant_llm_contract(*, document_id: str) -> LLMExtractionContract:
    return LLMExtractionContract(
        decision="generated",
        rationale="Recovered one anchored variant from the source record.",
        evidence=[],
        source_type="pubmed",
        document_id=document_id,
        entities=[
            LLMExtractedEntityCandidate(
                entity_type="VARIANT",
                label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                anchors=[
                    LLMIdentifierField(key="gene_symbol", value="MED13"),
                    LLMIdentifierField(key="hgvs_notation", value="c.977C>A"),
                ],
                metadata=[
                    LLMLiteralField(key="transcript", value="NM_015335.6"),
                    LLMLiteralField(key="hgvs_cdna", value="c.977C>A"),
                    LLMLiteralField(key="hgvs_protein", value="p.Thr326Lys"),
                    LLMLiteralField(key="classification", value="Likely Pathogenic"),
                ],
                evidence_excerpt="MED13 NM_015335.6:c.977C>A (p.Thr326Lys)",
                evidence_locator="text_span:10-34",
                assessment=_assessment(),
            ),
        ],
        observations=[],
        relations=[],
        rejected_facts=[],
        shadow_mode=True,
        agent_run_id="variant-aware-source-test",
    )


def test_llm_extraction_converts_verified_source_measurement() -> None:
    source_hash = "source-hash-1"
    contract = LLMExtractionContract(
        rationale="Copied one source measurement.",
        evidence=[],
        decision="generated",
        source_type="pubmed",
        document_id="document-1",
        observations=[
            LLMExtractedObservation(
                field_name="allele_frequency",
                variable_id="VAR_ALLELE_FREQUENCY",
                value=SourceMeasurementNumber(
                    value="0.125",
                    source_locator="raw_record.text",
                    literal_span="0.125",
                    field_name="allele_frequency",
                    unit="ratio",
                    extraction_method="literal_copy",
                    source_hash=source_hash,
                ),
                unit="ratio",
                subject_label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                subject_anchors=_llm_variant_subject_anchors(),
                assessment=_assessment(),
            ),
        ],
    )
    contract = LLMExtractionContract.model_validate(contract.model_dump(mode="json"))

    extracted = contract.to_extraction_contract(
        expected_source_hash=source_hash,
        source_values_by_locator={
            "raw_record.text": "Allele frequency was 0.125.",
        },
    )

    assert extracted.confidence_score == 0.9
    assert extracted.observations[0].value == 0.125
    assert extracted.observations[0].source_measurement is not None
    assert extracted.observations[0].source_measurement.literal_span == "0.125"


def test_llm_extraction_accepts_leading_dot_source_measurement() -> None:
    source_hash = "source-hash-leading-dot"
    contract = LLMExtractionContract(
        rationale="Copied a leading-dot source measurement.",
        evidence=[],
        decision="generated",
        source_type="paper",
        document_id="document-leading-dot",
        observations=[
            LLMExtractedObservation(
                field_name="p_value",
                variable_id="STUDY_P_VALUE",
                value=SourceMeasurementNumber(
                    value=".03",
                    source_locator="raw_record.text",
                    literal_span=".03",
                    field_name="p_value",
                    unit="unitless",
                    extraction_method="literal_copy",
                    source_hash=source_hash,
                ),
                unit="unitless",
                subject_label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                subject_anchors=_llm_variant_subject_anchors(),
                assessment=_assessment(),
            ),
        ],
    )

    extracted = contract.to_extraction_contract(
        expected_source_hash=source_hash,
        source_values_by_locator={"raw_record.text": "The result was p=.03."},
    )

    assert extracted.observations[0].value == 0.03


@pytest.mark.parametrize(
    ("literal_span", "value", "expected_value", "unit"),
    [
        ("5mg", "5", 5, "mg"),
        ("12kb", "12", 12, "kb"),
        ("3x", "3", 3, "x"),
        ("25%", "25", 25, "percent"),
    ],
)
def test_llm_extraction_accepts_literal_unit_adjacent_measurement(
    literal_span: str,
    value: str,
    expected_value: int,
    unit: str,
) -> None:
    source_hash = "source-hash-unit-adjacent"
    contract = LLMExtractionContract(
        rationale="Copied a measurement with its literal unit.",
        evidence=[],
        decision="generated",
        source_type="paper",
        document_id="document-unit-adjacent",
        observations=[
            LLMExtractedObservation(
                field_name="source_value",
                variable_id="SOURCE_VALUE",
                value=SourceMeasurementNumber(
                    value=value,
                    source_locator="raw_record.text",
                    literal_span=literal_span,
                    field_name="source_value",
                    unit=unit,
                    extraction_method="literal_copy",
                    source_hash=source_hash,
                ),
                unit=unit,
                subject_label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                subject_anchors=_llm_variant_subject_anchors(),
                assessment=_assessment(),
            ),
        ],
    )

    extracted = contract.to_extraction_contract(
        expected_source_hash=source_hash,
        source_values_by_locator={
            "raw_record.text": f"The reported measurement was {literal_span}."
        },
    )

    assert extracted.observations[0].value == expected_value
    assert extracted.observations[0].unit == unit


def test_llm_extraction_rejects_nearby_large_source_number() -> None:
    source_hash = "source-hash-large-number"
    contract = LLMExtractionContract(
        rationale="Returned a nearby large number.",
        evidence=[],
        decision="generated",
        source_type="paper",
        document_id="document-large-number",
        observations=[
            LLMExtractedObservation(
                field_name="coordinate",
                variable_id="GENOMIC_COORDINATE",
                value=SourceMeasurementNumber(
                    value="1000000000001",
                    source_locator="raw_record.text",
                    literal_span="1000000000000",
                    field_name="coordinate",
                    unit="unitless",
                    extraction_method="literal_copy",
                    source_hash=source_hash,
                ),
                unit="unitless",
                subject_label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                subject_anchors=_llm_variant_subject_anchors(),
                assessment=_assessment(),
            ),
        ],
    )

    with pytest.raises(ValueError, match="Numeric observation"):
        contract.to_extraction_contract(
            expected_source_hash=source_hash,
            source_values_by_locator={
                "raw_record.text": "Coordinate 1000000000000 was reported."
            },
        )


@pytest.mark.parametrize(
    ("literal_span", "source_text", "measurement_unit", "outer_unit", "match"),
    [
        ("5", "Dose was 5.", "mg", "mg", "value and unit"),
        ("5kg", "Dose was 5kg.", "mg", "mg", "value and unit"),
        ("somemg 5", "Dose was somemg 5.", "mg", "mg", "value and unit"),
        ("5mg", "Dose was 5mg.", "mg", None, "does not match"),
    ],
)
def test_llm_extraction_rejects_unsupported_or_inconsistent_unit(
    literal_span: str,
    source_text: str,
    measurement_unit: str,
    outer_unit: str | None,
    match: str,
) -> None:
    source_hash = "source-hash-unit-validation"
    contract = LLMExtractionContract(
        rationale="Returned a measurement with unsupported unit provenance.",
        evidence=[],
        decision="generated",
        source_type="paper",
        document_id="document-unit-validation",
        observations=[
            LLMExtractedObservation(
                field_name="dose",
                variable_id="DOSE",
                value=SourceMeasurementNumber(
                    value="5",
                    source_locator="raw_record.text",
                    literal_span=literal_span,
                    field_name="dose",
                    unit=measurement_unit,
                    extraction_method="literal_copy",
                    source_hash=source_hash,
                ),
                unit=outer_unit,
                subject_label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                subject_anchors=_llm_variant_subject_anchors(),
                assessment=_assessment(),
            ),
        ],
    )

    with pytest.raises(ValueError, match=match):
        contract.to_extraction_contract(
            expected_source_hash=source_hash,
            source_values_by_locator={"raw_record.text": source_text},
        )


@pytest.mark.parametrize(
    ("literal_span", "value", "unit", "source_text"),
    [
        ("5mg", "5", "unitless", "Reported 5mg."),
        ("5", "5", "unitless", "Reported 5 mg."),
        ("5 mg", "5", "ratio", "Reported 5 mg."),
        ("<=5 mg", "5", "mg", "Reported <=5 mg."),
        ("5 mg", "5", "mg", "Reported <=5 mg."),
        ("5-10 mg", "10", "mg", "Reported 5-10 mg."),
        ("10 mg", "10", "mg", "Reported 5-10 mg."),
    ],
)
def test_llm_extraction_rejects_unit_stripping_bounds_and_ranges(
    literal_span: str,
    value: str,
    unit: str,
    source_text: str,
) -> None:
    contract = LLMExtractionContract(
        rationale="Attempted a non-scalar literal copy.",
        evidence=[],
        decision="generated",
        source_type="paper",
        document_id="document-adversarial-measurement",
        observations=[
            _llm_source_measurement_observation(
                value=value,
                literal_span=literal_span,
                unit=unit,
            ),
        ],
    )

    with pytest.raises(ValueError, match="Numeric observation"):
        contract.to_extraction_contract(
            expected_source_hash="source-hash-adversarial",
            source_values_by_locator={"raw_record.text": source_text},
        )


def test_source_measurement_rejects_json_number_before_float_rounding() -> None:
    with pytest.raises(ValueError, match="value"):
        SourceMeasurementNumber.model_validate(
            {
                "value": 100000000000000000001.0,
                "source_locator": "raw_record.text",
                "literal_span": "100000000000000000001",
                "field_name": "source_value",
                "unit": "unitless",
                "extraction_method": "literal_copy",
                "source_hash": "source-hash-adversarial",
            },
        )


def test_llm_extraction_preserves_large_integer_lexeme() -> None:
    value = "100000000000000000001"
    contract = LLMExtractionContract(
        rationale="Copied an exact large integer.",
        evidence=[],
        decision="generated",
        source_type="paper",
        document_id="document-large-integer",
        observations=[
            _llm_source_measurement_observation(
                value=value,
                literal_span=value,
                unit="unitless",
            ),
        ],
    )

    extracted = contract.to_extraction_contract(
        expected_source_hash="source-hash-adversarial",
        source_values_by_locator={"raw_record.text": f"Coordinate {value}."},
    )

    assert extracted.observations[0].value == 100000000000000000001
    assert extracted.observations[0].source_measurement is not None
    assert extracted.observations[0].source_measurement.value == value


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("genomic_position", "12345"),
        ("exon_or_intron", "exon 2"),
        ("read_depth", "30x"),
        ("source_span_start", "10"),
    ],
)
def test_llm_entity_rejects_all_numeric_metadata(
    field_name: str,
    value: str,
) -> None:
    with pytest.raises(ValueError, match="source_measurement observation"):
        LLMExtractedEntityCandidate(
            entity_type="VARIANT",
            label="MED13 c.977C>A",
            anchors=[
                LLMIdentifierField(key="gene_symbol", value="MED13"),
                LLMIdentifierField(key="hgvs_notation", value="c.977C>A"),
            ],
            metadata=[LLMLiteralField(key=field_name, value=value)],
            evidence_excerpt="Variant evidence includes exon 2 at position 12345.",
            evidence_locator="raw_record.text",
            assessment=_assessment(),
        )


@pytest.mark.parametrize(
    ("key", "value"),
    [("target_label", "stage 2"), ("source_span_start", "10")],
)
def test_llm_rejected_fact_rejects_numeric_payload(key: str, value: str) -> None:
    with pytest.raises(ValueError, match="Numeric rejected-fact payload"):
        LLMRejectedFact(
            fact_type="relation",
            reason="Candidate requires review.",
            payload=[LLMLiteralField(key=key, value=value)],
            assessment=_assessment(),
        )


@pytest.mark.parametrize("value", ["0.125", ".125", "stage 2"])
def test_llm_extraction_rejects_numeric_observation_text(value: str) -> None:
    contract = LLMExtractionContract(
        rationale="Returned numeric-looking observation text.",
        evidence=[],
        decision="generated",
        source_type="paper",
        document_id="document-numeric-text",
        observations=[
            LLMExtractedObservation(
                field_name="source_value",
                variable_id="SOURCE_VALUE",
                value=value,
                assessment=_assessment(),
            ),
        ],
    )

    with pytest.raises(ValueError, match="source_measurement envelope"):
        contract.to_extraction_contract(
            expected_source_hash="source-hash-1",
            source_values_by_locator={"raw_record.text": value},
        )


def test_llm_extraction_keeps_categorical_observation_text() -> None:
    contract = LLMExtractionContract(
        rationale="Returned a categorical observation.",
        evidence=[],
        decision="generated",
        source_type="paper",
        document_id="document-category",
        observations=[
            LLMExtractedObservation(
                field_name="classification",
                variable_id="VAR_CLINVAR_CLASS",
                value="Likely Pathogenic",
                assessment=_assessment(),
            ),
        ],
    )

    extracted = contract.to_extraction_contract(
        expected_source_hash="source-hash-1",
        source_values_by_locator={},
    )

    assert extracted.observations[0].value == "Likely Pathogenic"


@pytest.mark.parametrize(
    (
        "source_hash",
        "literal_span",
        "value",
        "source_locator",
        "extraction_method",
        "match",
    ),
    [
        (
            "wrong-source",
            "0.125",
            "0.125",
            "raw_record.text",
            "literal_copy",
            "source_hash",
        ),
        (
            "source-hash-1",
            "invented-value",
            "0.125",
            "raw_record.text",
            "literal_copy",
            "literal_span",
        ),
        (
            "source-hash-1",
            "0.125",
            "999",
            "raw_record.text",
            "literal_copy",
            "value",
        ),
        (
            "source-hash-1",
            "0.125",
            "0.125",
            "invented.path",
            "literal_copy",
            "source_locator",
        ),
        (
            "source-hash-1",
            "0.1",
            "0.1",
            "raw_record.text",
            "literal_copy",
            "source locator",
        ),
        (
            "source-hash-1",
            "0.125",
            "0.125",
            "raw_record.text",
            "model_inference",
            "extraction_method",
        ),
    ],
)
def test_llm_extraction_rejects_unverified_source_measurement(
    source_hash: str,
    literal_span: str,
    value: str,
    source_locator: str,
    extraction_method: str,
    match: str,
) -> None:
    contract = LLMExtractionContract(
        rationale="Attempted one source measurement.",
        evidence=[],
        decision="generated",
        source_type="pubmed",
        document_id="document-1",
        observations=[
            LLMExtractedObservation(
                field_name="allele_frequency",
                variable_id="VAR_ALLELE_FREQUENCY",
                value=SourceMeasurementNumber(
                    value=value,
                    source_locator=source_locator,
                    literal_span=literal_span,
                    field_name="allele_frequency",
                    unit="ratio",
                    extraction_method=extraction_method,
                    source_hash=source_hash,
                ),
                unit="ratio",
                subject_label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                subject_anchors=_llm_variant_subject_anchors(),
                assessment=_assessment(),
            ),
        ],
    )

    with pytest.raises(ValueError, match=match):
        contract.to_extraction_contract(
            expected_source_hash="source-hash-1",
            source_values_by_locator={
                "raw_record.text": "Allele frequency was 0.125.",
            },
        )


@pytest.mark.parametrize(
    ("field_type", "value"),
    [
        (LLMIdentifierField, 12345),
        (LLMLiteralField, 0.99),
        (LLMLiteralField, 1),
    ],
)
def test_llm_dynamic_fields_reject_untyped_numbers(
    field_type: type[LLMIdentifierField | LLMLiteralField],
    value: object,
) -> None:
    with pytest.raises(ValueError, match="value"):
        field_type.model_validate({"key": "source_field", "value": value})


def test_llm_extraction_rejects_duplicate_dynamic_identifiers() -> None:
    contract = LLMExtractionContract(
        rationale="Returned conflicting identifiers.",
        evidence=[],
        decision="generated",
        source_type="pubmed",
        document_id="document-1",
        entities=[
            LLMExtractedEntityCandidate(
                entity_type="VARIANT",
                label="MED13 c.977C>A",
                anchors=[
                    LLMIdentifierField(key="gene_symbol", value="MED13"),
                    LLMIdentifierField(key="gene_symbol", value="OTHER"),
                ],
                metadata=[],
                evidence_excerpt="MED13 c.977C>A",
                evidence_locator="raw_record.text",
                assessment=_assessment(),
            ),
        ],
    )

    with pytest.raises(ValueError, match="Duplicate dynamic field key"):
        contract.to_extraction_contract(
            expected_source_hash="source-hash-1",
            source_values_by_locator={"raw_record.text": "MED13 c.977C>A"},
        )


def _variant_context(*, document_id: str = "doc-variant-1") -> (
    variant_extraction_bridges.ExtractionContext
):
    return variant_extraction_bridges.ExtractionContext(
        document_id=document_id,
        source_type="pubmed",
        research_space_id=str(uuid4()),
        raw_record={
            "document_id": document_id,
            "title": "Synthetic MED13 variant note",
            "text": (
                "MED13 NM_015335.6:c.977C>A (p.Thr326Lys) was classified "
                "as Likely Pathogenic in a child with developmental delay."
            ),
        },
        genomics_signals={
            "variant_aware_recommended": True,
            "variant_candidates": [
                {
                    "gene_symbol": "MED13",
                    "hgvs_notation": "c.977C>A",
                    "evidence_excerpt": "MED13 NM_015335.6:c.977C>A",
                },
            ],
        },
        shadow_mode=True,
    )


def _patch_variant_adapter_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    step_output: object,
) -> list[_FakeKernelStore]:
    created_stores: list[_FakeKernelStore] = []

    def _create_store() -> _FakeKernelStore:
        store = _FakeKernelStore()
        created_stores.append(store)
        return store

    async def _fake_run_single_step_with_policy(*_args, **_kwargs):
        return SimpleNamespace(output=step_output)

    monkeypatch.setattr(
        variant_extraction_bridges,
        "has_configured_openai_api_key",
        lambda: True,
    )
    monkeypatch.setattr(
        variant_extraction_bridges,
        "get_model_registry",
        lambda: SimpleNamespace(
            get_default_model=lambda _capability: SimpleNamespace(
                model_id="openai:gpt-5.4-mini",
            ),
            get_model=lambda _model_id: SimpleNamespace(timeout_seconds=30.0),
        ),
    )
    monkeypatch.setattr(
        variant_extraction_bridges,
        "normalize_litellm_model_id",
        lambda model_id: model_id.replace(":", "/"),
    )
    monkeypatch.setattr(
        variant_extraction_bridges,
        "create_artana_postgres_store",
        _create_store,
    )
    monkeypatch.setattr(
        variant_extraction_bridges,
        "run_single_step_with_policy",
        _fake_run_single_step_with_policy,
    )
    monkeypatch.setattr("artana.kernel.ArtanaKernel", _FakeKernel)
    monkeypatch.setattr("artana.agent.SingleStepModelClient", _FakeSingleStepClient)
    return created_stores


def test_artana_extraction_adapter_returns_fallback_without_openai_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        variant_extraction_bridges,
        "has_configured_openai_api_key",
        lambda: False,
    )

    context = _variant_context()
    result = asyncio.run(variant_extraction_bridges.ArtanaExtractionAdapter().extract(context))

    assert result.decision == "fallback"
    assert result.document_id == context.document_id
    assert result.source_type == context.source_type
    assert "OPENAI_API_KEY" in result.rationale


def test_artana_extraction_adapter_runs_service_local_llm_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _variant_context()
    contract = _single_variant_llm_contract(document_id=context.document_id)
    created_stores = _patch_variant_adapter_runtime(
        monkeypatch,
        step_output=contract.model_dump(mode="json"),
    )

    result = asyncio.run(variant_extraction_bridges.ArtanaExtractionAdapter().extract(context))

    assert result.decision == "generated"
    assert result.document_id == context.document_id
    assert result.source_type == context.source_type
    assert result.entities[0].anchors == {
        "gene_symbol": "MED13",
        "hgvs_notation": "c.977C>A",
    }
    assert result.agent_run_id is not None
    assert result.agent_run_id.startswith("variant_extraction:pubmed:")
    assert len(created_stores) == 1
    assert created_stores[0].closed is True
    assert created_stores[0].kernel is not None
    assert created_stores[0].kernel.closed is True


def test_artana_extraction_adapter_fails_closed_on_invalid_llm_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _variant_context()
    _patch_variant_adapter_runtime(monkeypatch, step_output={"decision": "generated"})

    result = asyncio.run(variant_extraction_bridges.ArtanaExtractionAdapter().extract(context))

    assert result.decision == "fallback"
    assert result.document_id == context.document_id
    assert result.source_type == context.source_type
    assert result.agent_run_id is not None
    assert result.agent_run_id.startswith("variant_extraction:pubmed:")
    assert "failed closed" in result.rationale


def test_artana_extraction_adapter_fails_closed_on_forged_measurement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _variant_context()
    contract = LLMExtractionContract(
        rationale="Returned a forged source measurement.",
        evidence=[],
        decision="generated",
        source_type=context.source_type,
        document_id=context.document_id,
        observations=[
            LLMExtractedObservation(
                field_name="allele_frequency",
                variable_id="VAR_ALLELE_FREQUENCY",
                value=SourceMeasurementNumber(
                    value="999",
                    source_locator="raw_record.text",
                    literal_span="MED13",
                    field_name="allele_frequency",
                    unit="ratio",
                    extraction_method="literal_copy",
                    source_hash="forged-source-hash",
                ),
                unit="ratio",
                subject_label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                subject_anchors=_llm_variant_subject_anchors(),
                assessment=_assessment(),
            ),
        ],
    )
    _patch_variant_adapter_runtime(
        monkeypatch,
        step_output=contract.model_dump(mode="json"),
    )

    result = asyncio.run(variant_extraction_bridges.ArtanaExtractionAdapter().extract(context))

    assert result.decision == "fallback"
    assert result.agent_run_id is not None
    assert "source_hash" in result.rationale


def test_variant_prompt_exposes_hash_and_valid_scalar_locators() -> None:
    context = _variant_context()
    context.raw_record.update(
        {
            "selected_record_index": 0,
            "retrieval_score": 0.98,
            "source_span": {"start": 10, "end": 20},
        },
    )
    payload = variant_extraction_bridges._prompt_payload_from_context(
        context,
    )

    assert isinstance(payload["source_hash"], str)
    assert len(payload["source_hash"]) == 64
    locators = payload["allowed_source_locators"]
    assert isinstance(locators, list)
    assert "raw_record.text" in locators
    assert all(locator.startswith("raw_record.") for locator in locators)
    assert "raw_record.selected_record_index" not in locators
    assert "raw_record.retrieval_score" not in locators
    assert "raw_record.source_span.start" not in locators
    assert "genomics_signals.variant_aware_recommended" not in locators
    assert not any("source_span" in locator for locator in locators)


def test_document_supports_variant_aware_extraction_detects_genomics_signals() -> None:
    variant_document = _document(
        text=(
            "Trio exome sequencing identified heterozygous de novo "
            "MED13 NM_015335.6:c.977C>A (p.Thr326Lys)."
        ),
    )
    generic_document = _document(
        text="MED13 associates with cardiomyopathy in one mouse model.",
    )

    assert document_supports_variant_aware_extraction(document=variant_document) is True
    assert (
        document_supports_variant_aware_extraction(document=generic_document) is False
    )


@pytest.mark.parametrize(
    ("document_source_type", "expected_extraction_source_type"),
    [
        ("text", "pubmed"),
        ("pdf", "pubmed"),
        ("pubmed", "pubmed"),
        ("clinvar", "clinvar"),
        ("marrvel", "marrvel"),
    ],
)
def test_extract_variant_aware_document_normalizes_supported_source_types(
    monkeypatch,
    document_source_type: str,
    expected_extraction_source_type: str,
) -> None:
    document = _document(
        text="MED13 NM_015335.6:c.977C>A (p.Thr326Lys) was classified as Likely Pathogenic.",
        source_type=document_source_type,
    )
    seen: dict[str, str] = {}

    async def _fake_extract(self, context):  # noqa: ANN001
        del self
        seen["source_type"] = context.source_type
        return _single_variant_contract(document_id=document.id)

    async def _fake_close(self) -> None:  # noqa: ANN001
        del self

    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.extract",
        _fake_extract,
    )
    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.close",
        _fake_close,
    )

    result = asyncio.run(
        extract_variant_aware_document(
            space_id=uuid4(),
            document=document,
            graph_api_gateway=_EmptyGraphGateway(),
        ),
    )

    assert seen["source_type"] == expected_extraction_source_type
    assert result.extraction_diagnostics["bridge_proposal_count"] >= 1


def test_extract_variant_aware_document_collapses_duplicate_variant_mentions(
    monkeypatch,
) -> None:
    document = _document(
        text=(
            "Clinical report: MED13 c.977C>A (p.Thr326Lys) was confirmed. "
            "The same report also spelled it as "
            "NM_015335.6:c.977C>A (p.Thr326Lys)."
        ),
    )

    contract = ExtractionContract(
        decision="generated",
        confidence_score=0.0,
        rationale="Recovered one anchored variant and one phenotype relation.",
        evidence=[],
        source_type="pubmed",
        document_id=document.id,
        entities=[
            ExtractedEntityCandidate(
                entity_type="VARIANT",
                label="c.977C>A",
                anchors={
                    "gene_symbol": "MED13",
                    "hgvs_notation": "c.977C>A",
                },
                metadata={},
                evidence_excerpt="MED13 c.977C>A (p.Thr326Lys)",
                evidence_locator="text_span:10-34",
                assessment=_assessment(),
            ),
            ExtractedEntityCandidate(
                entity_type="VARIANT",
                label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                anchors={
                    "gene_symbol": "MED13",
                    "hgvs_notation": "c.977C>A",
                },
                metadata={
                    "transcript": "NM_015335.6",
                    "hgvs_cdna": "c.977C>A",
                    "hgvs_protein": "p.Thr326Lys",
                    "classification": "Likely Pathogenic",
                },
                evidence_excerpt="NM_015335.6:c.977C>A (p.Thr326Lys)",
                evidence_locator="text_span:52-90",
                assessment=_assessment(),
            ),
            ExtractedEntityCandidate(
                entity_type="VARIANT",
                label="T326K",
                anchors={},
                metadata={},
                evidence_excerpt="The draft table abbreviated the change as T326K.",
                evidence_locator="text_span:91-110",
                assessment=_assessment(
                    support_band=SupportBand.TENTATIVE,
                    rationale="Short protein alias recovered from a draft table.",
                ),
            ),
        ],
        observations=[],
        relations=[
            ExtractedRelation(
                source_type="VARIANT",
                relation_type="CAUSES",
                target_type="PHENOTYPE",
                source_label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                target_label="developmental delay",
                source_anchors={
                    "gene_symbol": "MED13",
                    "hgvs_notation": "c.977C>A",
                },
                evidence_excerpt=(
                    "MED13 NM_015335.6:c.977C>A (p.Thr326Lys) was associated "
                    "with developmental delay."
                ),
                evidence_locator="sentence:1",
                assessment=_assessment(),
            ),
        ],
        rejected_facts=[],
        pipeline_payloads=[],
        shadow_mode=True,
        agent_run_id="variant-aware-test",
    )

    async def _fake_extract(self, context):  # noqa: ANN001
        del self, context
        return contract

    async def _fake_close(self) -> None:  # noqa: ANN001
        del self

    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.extract",
        _fake_extract,
    )
    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.close",
        _fake_close,
    )

    result = asyncio.run(
        extract_variant_aware_document(
            space_id=uuid4(),
            document=document,
            graph_api_gateway=_EmptyGraphGateway(),
        ),
    )

    entity_drafts = [
        draft
        for draft in result.proposal_drafts
        if draft.proposal_type == "entity_candidate"
    ]
    observation_drafts = [
        draft
        for draft in result.proposal_drafts
        if draft.proposal_type == "observation_candidate"
    ]
    claim_drafts = [
        draft
        for draft in result.proposal_drafts
        if draft.proposal_type == "candidate_claim"
    ]

    assert len(entity_drafts) == 1
    assert entity_drafts[0].payload["display_label"] == (
        "NM_015335.6:c.977C>A (p.Thr326Lys)"
    )
    assert len(entity_drafts[0].payload["metadata"]["supporting_evidence"]) >= 2
    assert "T326K" in entity_drafts[0].payload["aliases"]
    assert {draft.payload["variable_id"] for draft in observation_drafts} >= {
        "VAR_TRANSCRIPT_ID",
        "VAR_HGVS_CDNA",
        "VAR_HGVS_PROTEIN",
        "VAR_CLINVAR_CLASS",
    }
    assert len(claim_drafts) == 1
    subject_candidate = claim_drafts[0].payload["proposed_subject_entity_candidate"]
    assert subject_candidate["identifiers"] == {
        "gene_symbol": "MED13",
        "hgvs_notation": "c.977C>A",
    }
    assert result.candidate_discovery["entity_candidate_count"] == 1


def test_extract_variant_aware_document_stages_source_measurement_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document(
        text=(
            "MED13 NM_015335.6:c.977C>A (p.Thr326Lys) had an allele frequency "
            "of 0.125."
        ),
    )
    contract = _single_variant_contract(document_id=document.id).model_copy(
        update={
            "observations": [
                ExtractedObservation(
                    field_name="allele_frequency",
                    variable_id="VAR_ALLELE_FREQUENCY",
                    value=0.125,
                    unit="ratio",
                    subject_label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                    subject_anchors={
                        "gene_symbol": "MED13",
                        "hgvs_notation": "c.977C>A",
                    },
                    source_measurement=SourceMeasurementNumber(
                        value="0.125",
                        source_locator="raw_record.text",
                        literal_span="0.125",
                        field_name="allele_frequency",
                        unit="ratio",
                        extraction_method="literal_copy",
                        source_hash="source-hash-staging",
                    ),
                    assessment=_assessment(),
                ),
            ],
        },
    )

    async def _fake_extract(self, context):  # noqa: ANN001
        del self, context
        return contract

    async def _fake_close(self) -> None:  # noqa: ANN001
        del self

    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.extract",
        _fake_extract,
    )
    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.close",
        _fake_close,
    )

    result = asyncio.run(
        extract_variant_aware_document(
            space_id=uuid4(),
            document=document,
            graph_api_gateway=_EmptyGraphGateway(),
        ),
    )

    drafts = [
        draft
        for draft in result.proposal_drafts
        if draft.proposal_type == "observation_candidate"
        and draft.payload["variable_id"] == "VAR_ALLELE_FREQUENCY"
    ]
    assert len(drafts) == 1
    assert drafts[0].payload["value"] == 0.125
    assert drafts[0].payload["source_measurement"] == {
        "origin": "source_measurement",
        "value": "0.125",
        "source_locator": "raw_record.text",
        "literal_span": "0.125",
        "field_name": "allele_frequency",
        "unit": "ratio",
        "extraction_method": "literal_copy",
        "source_hash": "source-hash-staging",
    }
    assert drafts[0].payload["subject_entity_candidate"]["identifiers"] == {
        "gene_symbol": "MED13",
        "hgvs_notation": "c.977C>A",
    }


def test_extract_variant_aware_document_falls_back_to_deterministic_signals(
    monkeypatch,
) -> None:
    document = _document(
        text=(
            "Trio exome sequencing identified heterozygous de novo MED13 "
            "NM_015335.6:c.977C>A (p.Thr326Lys), classified as Likely "
            "Pathogenic in exon 7. The child had developmental delay and "
            "cardiomyopathy concern."
        ),
    )

    contract = ExtractionContract(
        decision="escalate",
        confidence_score=0.0,
        rationale="LLM deferred to deterministic signal extraction.",
        evidence=[],
        source_type="pubmed",
        document_id=document.id,
        entities=[],
        observations=[],
        relations=[],
        rejected_facts=[],
        pipeline_payloads=[],
        shadow_mode=True,
        agent_run_id="variant-aware-fallback-test",
    )

    async def _fake_extract(self, context):  # noqa: ANN001
        del self, context
        return contract

    async def _fake_close(self) -> None:  # noqa: ANN001
        del self

    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.extract",
        _fake_extract,
    )
    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.close",
        _fake_close,
    )

    result = asyncio.run(
        extract_variant_aware_document(
            space_id=uuid4(),
            document=document,
            graph_api_gateway=_EmptyGraphGateway(),
        ),
    )

    entity_drafts = [
        draft
        for draft in result.proposal_drafts
        if draft.proposal_type == "entity_candidate"
    ]
    observation_variable_ids = {
        draft.payload["variable_id"]
        for draft in result.proposal_drafts
        if draft.proposal_type == "observation_candidate"
    }
    review_item_types = {draft.review_type for draft in result.review_item_drafts}

    assert len(entity_drafts) == 1
    assert entity_drafts[0].payload["identifiers"] == {
        "gene_symbol": "MED13",
        "hgvs_notation": "c.977C>A",
    }
    assert observation_variable_ids >= {
        "VAR_TRANSCRIPT_ID",
        "VAR_HGVS_CDNA",
        "VAR_HGVS_PROTEIN",
        "VAR_ZYGOSITY",
        "VAR_INHERITANCE_MODE",
        "VAR_EXON_INTRON",
        "VAR_CLINVAR_CLASS",
    }
    assert "phenotype_claim_review" in review_item_types
    assert result.extraction_diagnostics["fallback_from_signals"] is True
    assert result.extraction_diagnostics["agent_extraction_completed"] is False
    assert result.extraction_diagnostics["fallback_output_used"] is True
    assert result.extraction_diagnostics["trusted_evidence_eligible"] is False
    assert all(
        draft.metadata["agent_extraction_completed"] is False
        and draft.metadata["fallback_output_used"] is True
        and draft.metadata["trusted_evidence_eligible"] is False
        for draft in result.proposal_drafts
    )
    assert all(
        draft.metadata["agent_extraction_completed"] is False
        and draft.metadata["fallback_output_used"] is True
        and draft.metadata["trusted_evidence_eligible"] is False
        and draft.payload["proposal_draft"]["metadata"][
            "agent_extraction_completed"
        ]
        is False
        and draft.payload["proposal_draft"]["metadata"]["fallback_output_used"]
        is True
        and draft.payload["proposal_draft"]["metadata"][
            "trusted_evidence_eligible"
        ]
        is False
        for draft in result.review_item_drafts
        if draft.review_type == "phenotype_claim_review"
    )


def test_extract_variant_aware_document_treats_signal_only_generated_output_as_fallback(
    monkeypatch,
) -> None:
    document = _document(
        text=(
            "Trio exome sequencing identified heterozygous de novo MED13 "
            "NM_015335.6:c.977C>A (p.Thr326Lys), classified as Likely "
            "Pathogenic in exon 7."
        ),
    )
    contract = ExtractionContract(
        decision="generated",
        confidence_score=0.0,
        rationale="Agent completed but emitted no structured variant entities.",
        evidence=[],
        source_type="pubmed",
        document_id=document.id,
        entities=[],
        observations=[],
        relations=[],
        rejected_facts=[],
        pipeline_payloads=[],
        shadow_mode=True,
        agent_run_id="variant-aware-signal-only-generated-test",
    )

    async def _fake_extract(self, context):  # noqa: ANN001
        del self, context
        return contract

    async def _fake_close(self) -> None:  # noqa: ANN001
        del self

    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.extract",
        _fake_extract,
    )
    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.close",
        _fake_close,
    )

    result = asyncio.run(
        extract_variant_aware_document(
            space_id=uuid4(),
            document=document,
            graph_api_gateway=_EmptyGraphGateway(),
        ),
    )

    assert result.proposal_drafts
    assert result.extraction_diagnostics["agent_extraction_completed"] is False
    assert result.extraction_diagnostics["fallback_output_used"] is True
    assert result.extraction_diagnostics["trusted_evidence_eligible"] is False
    assert all(
        draft.metadata["agent_extraction_completed"] is False
        and draft.metadata["fallback_output_used"] is True
        and draft.metadata["trusted_evidence_eligible"] is False
        for draft in result.proposal_drafts
    )


def test_extract_variant_aware_document_treats_same_key_signal_enrichment_as_untrusted(
    monkeypatch,
) -> None:
    document = _document(text="MED13 c.977C>A was reported with p.Thr326Lys.")
    contract = ExtractionContract(
        decision="generated",
        confidence_score=0.0,
        rationale="Agent emitted the variant anchors only.",
        evidence=[],
        source_type="pubmed",
        document_id=document.id,
        entities=[
            ExtractedEntityCandidate(
                entity_type="VARIANT",
                label="MED13 c.977C>A",
                anchors={
                    "gene_symbol": "MED13",
                    "hgvs_notation": "c.977C>A",
                },
                metadata={},
                evidence_excerpt="MED13 c.977C>A",
                evidence_locator="text_span:0-14",
                assessment=_assessment(),
            ),
        ],
        observations=[],
        relations=[],
        rejected_facts=[],
        pipeline_payloads=[],
        shadow_mode=True,
        agent_run_id="variant-aware-same-key-signal-enrichment-test",
    )

    async def _fake_extract(self, context):  # noqa: ANN001
        del self, context
        return contract

    async def _fake_close(self) -> None:  # noqa: ANN001
        del self

    def _fake_signal_bundle(*, raw_record: object, source_type: str):
        del raw_record, source_type
        return {
            "variant_aware_recommended": True,
            "variant_candidates": [
                {
                    "anchors": {
                        "gene_symbol": "MED13",
                        "hgvs_notation": "c.977C>A",
                    },
                    "metadata": {
                        "classification": "Likely Pathogenic",
                        "hgvs_protein": "p.Thr326Lys",
                    },
                    "evidence_excerpt": "MED13 c.977C>A",
                    "evidence_locator": "text_span:0-14",
                },
            ],
        }

    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.extract",
        _fake_extract,
    )
    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.close",
        _fake_close,
    )
    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.build_genomics_signal_bundle",
        _fake_signal_bundle,
    )

    result = asyncio.run(
        extract_variant_aware_document(
            space_id=uuid4(),
            document=document,
            graph_api_gateway=_EmptyGraphGateway(),
        ),
    )

    observation_drafts = [
        draft
        for draft in result.proposal_drafts
        if draft.proposal_type == "observation_candidate"
    ]
    observation_variable_ids = {draft.payload["variable_id"] for draft in observation_drafts}
    assert observation_variable_ids >= {"VAR_HGVS_PROTEIN", "VAR_CLINVAR_CLASS"}
    assert result.extraction_diagnostics["fallback_from_signals"] is True
    assert result.extraction_diagnostics["agent_extraction_completed"] is False
    assert result.extraction_diagnostics["fallback_output_used"] is True
    assert result.extraction_diagnostics["trusted_evidence_eligible"] is False
    assert all(
        draft.metadata["trusted_evidence_eligible"] is False
        for draft in observation_drafts
    )


def test_extract_variant_aware_document_treats_mixed_signal_fallback_as_untrusted(
    monkeypatch,
) -> None:
    document = _document(
        text=(
            "Report mentions MED13 c.977C>A and a separate MED13 c.1000G>T "
            "variant."
        ),
    )
    contract = _single_variant_contract(document_id=document.id)

    async def _fake_extract(self, context):  # noqa: ANN001
        del self, context
        return contract

    async def _fake_close(self) -> None:  # noqa: ANN001
        del self

    def _fake_signal_bundle(*, raw_record: object, source_type: str):
        del raw_record, source_type
        return {
            "variant_aware_recommended": True,
            "variant_candidates": [
                {
                    "anchors": {
                        "gene_symbol": "MED13",
                        "hgvs_notation": "c.977C>A",
                    },
                    "metadata": {"hgvs_protein": "p.Thr326Lys"},
                    "evidence_excerpt": "MED13 c.977C>A",
                    "evidence_locator": "text_span:17-30",
                },
                {
                    "anchors": {
                        "gene_symbol": "MED13",
                        "hgvs_notation": "c.1000G>T",
                    },
                    "metadata": {"hgvs_protein": "p.Gly334Cys"},
                    "evidence_excerpt": "MED13 c.1000G>T",
                    "evidence_locator": "text_span:51-65",
                },
            ],
        }

    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.extract",
        _fake_extract,
    )
    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.close",
        _fake_close,
    )
    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.build_genomics_signal_bundle",
        _fake_signal_bundle,
    )

    result = asyncio.run(
        extract_variant_aware_document(
            space_id=uuid4(),
            document=document,
            graph_api_gateway=_EmptyGraphGateway(),
        ),
    )

    variant_labels = {
        draft.payload["display_label"]
        for draft in result.proposal_drafts
        if draft.proposal_type == "entity_candidate"
    }
    assert len(variant_labels) >= 2
    assert "c.1000G>T" in variant_labels
    assert result.extraction_diagnostics["fallback_from_signals"] is True
    assert result.extraction_diagnostics["agent_extraction_completed"] is False
    assert result.extraction_diagnostics["fallback_output_used"] is True
    assert result.extraction_diagnostics["trusted_evidence_eligible"] is False
    assert all(
        draft.metadata["trusted_evidence_eligible"] is False
        for draft in result.proposal_drafts
    )


def test_extract_variant_aware_document_detects_unmatched_signal_with_non_variant_agent_entity(
    monkeypatch,
) -> None:
    document = _document(text="MED13 c.1000G>T was reported.")
    contract = ExtractionContract(
        decision="generated",
        confidence_score=0.0,
        rationale="Agent emitted a gene but missed the variant signal.",
        evidence=[],
        source_type="pubmed",
        document_id=document.id,
        entities=[
            ExtractedEntityCandidate(
                entity_type="GENE",
                label="MED13",
                anchors={"gene_symbol": "MED13"},
                metadata={},
                evidence_excerpt="MED13 c.1000G>T",
                evidence_locator="text_span:0-15",
                assessment=_assessment(),
            ),
        ],
        observations=[],
        relations=[],
        rejected_facts=[],
        pipeline_payloads=[],
        shadow_mode=True,
        agent_run_id="variant-aware-non-variant-agent-test",
    )

    async def _fake_extract(self, context):  # noqa: ANN001
        del self, context
        return contract

    async def _fake_close(self) -> None:  # noqa: ANN001
        del self

    def _fake_signal_bundle(*, raw_record: object, source_type: str):
        del raw_record, source_type
        return {
            "variant_aware_recommended": True,
            "variant_candidates": [
                {
                    "anchors": {
                        "gene_symbol": "MED13",
                        "hgvs_notation": "c.1000G>T",
                    },
                    "metadata": {"hgvs_protein": "p.Gly334Cys"},
                    "evidence_excerpt": "MED13 c.1000G>T",
                    "evidence_locator": "text_span:0-15",
                },
            ],
        }

    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.extract",
        _fake_extract,
    )
    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.close",
        _fake_close,
    )
    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.build_genomics_signal_bundle",
        _fake_signal_bundle,
    )

    result = asyncio.run(
        extract_variant_aware_document(
            space_id=uuid4(),
            document=document,
            graph_api_gateway=_EmptyGraphGateway(),
        ),
    )

    assert result.extraction_diagnostics["fallback_from_signals"] is True
    assert result.extraction_diagnostics["agent_extraction_completed"] is False
    assert all(
        draft.metadata["trusted_evidence_eligible"] is False
        for draft in result.proposal_drafts
    )


def test_extract_variant_aware_document_falls_back_for_pubmed_variant_prose(
    monkeypatch,
) -> None:
    document = _document(
        text=(
            "A de novo missense variant c.977C>A, p.Thr326Lys in MED13 was "
            "reported in a patient with developmental delay."
        ),
        source_type="pubmed",
    )
    contract = ExtractionContract(
        decision="escalate",
        confidence_score=0.0,
        rationale="LLM deferred to deterministic signal extraction.",
        evidence=[],
        source_type="pubmed",
        document_id=document.id,
        entities=[],
        observations=[],
        relations=[],
        rejected_facts=[],
        pipeline_payloads=[],
        shadow_mode=True,
        agent_run_id="variant-aware-pubmed-prose-fallback-test",
    )

    async def _fake_extract(self, context):  # noqa: ANN001
        del self, context
        return contract

    async def _fake_close(self) -> None:  # noqa: ANN001
        del self

    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.extract",
        _fake_extract,
    )
    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.close",
        _fake_close,
    )

    assert document_supports_variant_aware_extraction(document=document) is True

    result = asyncio.run(
        extract_variant_aware_document(
            space_id=uuid4(),
            document=document,
            graph_api_gateway=_EmptyGraphGateway(),
        ),
    )

    entity_drafts = [
        draft
        for draft in result.proposal_drafts
        if draft.proposal_type == "entity_candidate"
    ]
    observation_variable_ids = {
        draft.payload["variable_id"]
        for draft in result.proposal_drafts
        if draft.proposal_type == "observation_candidate"
    }

    assert len(entity_drafts) == 1
    assert entity_drafts[0].payload["identifiers"] == {
        "gene_symbol": "MED13",
        "hgvs_notation": "c.977C>A",
    }
    assert observation_variable_ids >= {"VAR_HGVS_CDNA", "VAR_HGVS_PROTEIN"}
    assert result.extraction_diagnostics["fallback_from_signals"] is True


def test_extract_variant_aware_document_defers_incomplete_variant_anchors(
    monkeypatch,
) -> None:
    document = _document(
        text="MARRVEL ClinVar panel mentions a MED13 variant without complete HGVS.",
        source_type="marrvel",
    )
    contract = ExtractionContract(
        decision="generated",
        confidence_score=0.82,
        rationale="Variant mention needs human review before graph promotion.",
        evidence=[],
        source_type="marrvel",
        document_id=document.id,
        entities=[
            ExtractedEntityCandidate(
                entity_type="VARIANT",
                label="MED13 variant",
                anchors={"gene_symbol": "MED13"},
                metadata={},
                evidence_excerpt="MED13 variant",
                evidence_locator="marrvel:clinvar:0",
                assessment=_assessment(
                    support_band=SupportBand.TENTATIVE,
                    rationale="Missing HGVS notation.",
                ),
            ),
        ],
        observations=[],
        relations=[],
        rejected_facts=[],
        pipeline_payloads=[],
        shadow_mode=True,
        agent_run_id="variant-aware-incomplete-anchor-test",
    )

    async def _fake_extract(self, context):  # noqa: ANN001
        del self, context
        return contract

    async def _fake_close(self) -> None:  # noqa: ANN001
        del self

    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.extract",
        _fake_extract,
    )
    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.close",
        _fake_close,
    )

    result = asyncio.run(
        extract_variant_aware_document(
            space_id=uuid4(),
            document=document,
            graph_api_gateway=_EmptyGraphGateway(),
        ),
    )

    assert result.proposal_drafts[0].metadata["review_required"] is True
    assert result.review_item_drafts
    assert result.review_item_drafts[0].review_type == "variant_anchor_review"


def test_extract_variant_aware_document_preserves_decomposed_mechanism_claims(
    monkeypatch,
) -> None:
    document = _document(
        text=(
            "MED13 NM_015335.6:c.977C>A (p.Thr326Lys) falls in a "
            "phosphodegron-like region, may impair Fbw7-mediated degradation, "
            "and could alter protein stability in a way that helps explain the "
            "neurodevelopmental phenotype."
        ),
    )

    contract = ExtractionContract(
        decision="generated",
        confidence_score=0.0,
        rationale="Recovered one anchored variant plus decomposed mechanism claims.",
        evidence=[],
        source_type="pubmed",
        document_id=document.id,
        entities=[
            ExtractedEntityCandidate(
                entity_type="VARIANT",
                label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                anchors={
                    "gene_symbol": "MED13",
                    "hgvs_notation": "c.977C>A",
                },
                metadata={
                    "transcript": "NM_015335.6",
                    "hgvs_cdna": "c.977C>A",
                    "hgvs_protein": "p.Thr326Lys",
                },
                evidence_excerpt="MED13 NM_015335.6:c.977C>A (p.Thr326Lys)",
                evidence_locator="sentence:1",
                assessment=_assessment(),
            ),
        ],
        observations=[],
        relations=[
            ExtractedRelation(
                source_type="VARIANT",
                relation_type="LOCATED_IN",
                target_type="PROTEIN_DOMAIN",
                source_label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                target_label="phosphodegron-like region",
                source_anchors={
                    "gene_symbol": "MED13",
                    "hgvs_notation": "c.977C>A",
                },
                evidence_excerpt="The altered residue falls within a phosphodegron-like region.",
                evidence_locator="sentence:1",
                claim_text="The altered residue falls within a phosphodegron-like region.",
                assessment=_assessment(),
            ),
            ExtractedRelation(
                source_type="VARIANT",
                relation_type="AFFECTS",
                target_type="PROCESS",
                source_label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                target_label="Fbw7-mediated degradation",
                source_anchors={
                    "gene_symbol": "MED13",
                    "hgvs_notation": "c.977C>A",
                },
                evidence_excerpt="The change may impair Fbw7-mediated degradation.",
                evidence_locator="sentence:2",
                claim_text="The change may impair Fbw7-mediated degradation.",
                assessment=_assessment(
                    support_band=SupportBand.SUPPORTED,
                    rationale="Mechanism wording is evidence-backed but still hedged.",
                ),
            ),
            ExtractedRelation(
                source_type="VARIANT",
                relation_type="EXPLAINS",
                target_type="PHENOTYPE",
                source_label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                target_label="neurodevelopmental phenotype",
                source_anchors={
                    "gene_symbol": "MED13",
                    "hgvs_notation": "c.977C>A",
                },
                evidence_excerpt=(
                    "Altered protein stability could help explain the neurodevelopmental phenotype."
                ),
                evidence_locator="sentence:3",
                claim_text=(
                    "Altered protein stability could help explain the neurodevelopmental phenotype."
                ),
                assessment=_assessment(
                    support_band=SupportBand.TENTATIVE,
                    rationale="Phenotype explanation remains partly speculative.",
                ),
            ),
        ],
        rejected_facts=[],
        pipeline_payloads=[],
        shadow_mode=True,
        agent_run_id="variant-aware-mechanism-test",
    )

    async def _fake_extract(self, context):  # noqa: ANN001
        del self, context
        return contract

    async def _fake_close(self) -> None:  # noqa: ANN001
        del self

    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.extract",
        _fake_extract,
    )
    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.close",
        _fake_close,
    )

    result = asyncio.run(
        extract_variant_aware_document(
            space_id=uuid4(),
            document=document,
            graph_api_gateway=_EmptyGraphGateway(),
        ),
    )

    claim_drafts = [
        draft
        for draft in result.proposal_drafts
        if draft.proposal_type == "candidate_claim"
    ]

    assert len(claim_drafts) == 2
    assert result.extraction_diagnostics["relation_count"] == 3
    assert result.extraction_diagnostics["bridge_skipped_count"] == 1
    assert all(len(draft.summary.strip()) < 200 for draft in claim_drafts)
    assert {draft.payload["proposed_claim_type"] for draft in claim_drafts} == {
        "LOCATED_IN",
        "MODULATES",
    }
    assert result.skipped_items == [
        {
            "kind": "relation_skipped",
            "relation_type": "EXPLAINS",
            "source_label": "NM_015335.6:c.977C>A (p.Thr326Lys)",
            "target_label": "neurodevelopmental phenotype",
            "reason": "Relation type requires governed dictionary review.",
        },
    ]


def test_extract_variant_aware_document_promotes_strong_rejected_relations_to_review_items(
    monkeypatch,
) -> None:
    document = _document(
        text=(
            "MED13 c.977C>A was described near developmental delay, but the model "
            "flagged the relation for review instead of emitting it directly."
        ),
    )

    contract = ExtractionContract(
        decision="generated",
        confidence_score=0.0,
        rationale="One strong but rejected relation should become a review item.",
        evidence=[],
        source_type="pubmed",
        document_id=document.id,
        entities=[
            ExtractedEntityCandidate(
                entity_type="VARIANT",
                label="MED13 c.977C>A",
                anchors={
                    "gene_symbol": "MED13",
                    "hgvs_notation": "c.977C>A",
                },
                metadata={},
                evidence_excerpt="MED13 c.977C>A was noted in the report.",
                evidence_locator="sentence:1",
                assessment=_assessment(),
            ),
        ],
        observations=[],
        relations=[],
        rejected_facts=[
            RejectedFact(
                fact_type="relation",
                reason="Relation needs curator review before proposal staging",
                payload={
                    "source_type": "VARIANT",
                    "relation_type": "CAUSES",
                    "target_type": "PHENOTYPE",
                    "source_label": "MED13 c.977C>A",
                    "target_label": "developmental delay",
                    "source_anchors": {
                        "gene_symbol": "MED13",
                        "hgvs_notation": "c.977C>A",
                    },
                    "evidence_excerpt": (
                        "The variant appeared in the same paragraph as developmental delay."
                    ),
                    "evidence_locator": "sentence:2",
                },
                assessment=_assessment(
                    support_band=SupportBand.SUPPORTED,
                    rationale="The evidence is strong enough to review, but not auto-stage.",
                ),
            ),
            RejectedFact(
                fact_type="relation",
                reason="Too speculative to review",
                payload={
                    "source_type": "VARIANT",
                    "relation_type": "EXPLAINS",
                    "target_type": "PHENOTYPE",
                    "source_label": "MED13 c.977C>A",
                    "target_label": "cardiomyopathy",
                },
                assessment=_assessment(
                    support_band=SupportBand.TENTATIVE,
                    rationale="This should stay audit-only metadata.",
                ),
            ),
            RejectedFact(
                fact_type="relation",
                reason="Raw relation type needs governed dictionary review",
                payload={
                    "source_type": "VARIANT",
                    "relation_type": "PROTECTS_AGAINST",
                    "target_type": "PHENOTYPE",
                    "source_label": "MED13 c.977C>A",
                    "target_label": "developmental delay",
                },
                assessment=_assessment(
                    support_band=SupportBand.SUPPORTED,
                    rationale="Strong enough to review, but the relation type is not governed.",
                ),
            ),
        ],
        pipeline_payloads=[],
        shadow_mode=True,
        agent_run_id="variant-aware-rejected-review-test",
    )

    async def _fake_extract(self, context):  # noqa: ANN001
        del self, context
        return contract

    async def _fake_close(self) -> None:  # noqa: ANN001
        del self

    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.extract",
        _fake_extract,
    )
    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.close",
        _fake_close,
    )

    result = asyncio.run(
        extract_variant_aware_document(
            space_id=uuid4(),
            document=document,
            graph_api_gateway=_EmptyGraphGateway(),
        ),
    )

    rejected_review_items = [
        draft
        for draft in result.review_item_drafts
        if draft.review_type == "rejected_relation_review"
    ]

    assert len(rejected_review_items) == 1
    assert rejected_review_items[0].source_family == "document_extraction"
    assert (
        rejected_review_items[0].payload["proposal_draft"]["payload"][
            "proposed_claim_type"
        ]
        == "CAUSES"
    )
    assert any(
        item["kind"] == "rejected_fact"
        and item["reason"] == "Too speculative to review"
        for item in result.skipped_items
    )
    assert any(
        item["kind"] == "rejected_fact"
        and item["reason"] == "Raw relation type needs governed dictionary review"
        for item in result.skipped_items
    )


def test_extract_variant_aware_document_canonicalizes_rejected_relation_review_items(
    monkeypatch,
) -> None:
    document = _document(
        text="MED13 c.977C>A affects developmental delay in the curated passage.",
    )

    contract = ExtractionContract(
        decision="generated",
        confidence_score=0.0,
        rationale="One rejected relation should convert through canonical taxonomy.",
        evidence=[],
        source_type="pubmed",
        document_id=document.id,
        entities=[],
        observations=[],
        relations=[],
        rejected_facts=[
            RejectedFact(
                fact_type="relation",
                reason="Relation needs review before proposal staging",
                payload={
                    "source_type": "VARIANT",
                    "relation_type": "AFFECTS",
                    "target_type": "PHENOTYPE",
                    "source_label": "MED13 c.977C>A",
                    "target_label": "developmental delay",
                    "evidence_excerpt": "MED13 c.977C>A affects developmental delay.",
                    "evidence_locator": "sentence:1",
                },
                assessment=_assessment(
                    support_band=SupportBand.SUPPORTED,
                    rationale="The relation is reviewable after canonicalization.",
                ),
            ),
        ],
        pipeline_payloads=[],
        shadow_mode=True,
        agent_run_id="variant-aware-rejected-canonical-test",
    )

    async def _fake_extract(self, context):  # noqa: ANN001
        del self, context
        return contract

    async def _fake_close(self) -> None:  # noqa: ANN001
        del self

    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.extract",
        _fake_extract,
    )
    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.close",
        _fake_close,
    )

    result = asyncio.run(
        extract_variant_aware_document(
            space_id=uuid4(),
            document=document,
            graph_api_gateway=_EmptyGraphGateway(),
        ),
    )

    review_item = next(
        draft
        for draft in result.review_item_drafts
        if draft.review_type == "rejected_relation_review"
    )
    assert (
        review_item.payload["proposal_draft"]["payload"]["proposed_claim_type"]
        == "MODULATES"
    )
    assert review_item.metadata["relation_type"] == "MODULATES"
