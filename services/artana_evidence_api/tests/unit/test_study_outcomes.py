"""Unit tests for trial study-outcome extraction and storage."""

from __future__ import annotations

from uuid import uuid4

import pytest
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.models import HarnessDocumentModel, HarnessRunModel
from artana_evidence_api.study_outcomes import (
    HarnessStudyOutcomeStore,
    SqlAlchemyStudyOutcomeStore,
    StudyOutcomeDraft,
    document_supports_study_outcome_extraction,
    extract_study_outcome_drafts,
)
from sqlalchemy.orm import Session


def _pubmed_document(
    *,
    text: str,
    publication_types: list[str],
    source_type: str = "pubmed",
):
    store = HarnessDocumentStore()
    return store.create_document(
        document_id=uuid4(),
        space_id=uuid4(),
        created_by=uuid4(),
        title="Trial outcomes",
        source_type=source_type,
        filename=None,
        media_type="text/plain",
        sha256="0" * 64,
        byte_size=len(text.encode("utf-8")),
        page_count=None,
        text_content=text,
        ingestion_run_id=uuid4(),
        enrichment_status="completed",
        extraction_status="not_started",
        metadata={
            "pubmed": {
                "pmid": "15758009",
                "publication_types": publication_types,
            },
        },
    )


def test_study_outcome_extraction_only_accepts_pubmed_clinical_trials() -> None:
    trial_document = _pubmed_document(
        text="Temozolomide plus radiotherapy vs radiotherapy alone median OS 14.6 vs 12.1 months.",
        publication_types=["Randomized Controlled Trial"],
    )
    review_document = _pubmed_document(
        text="Temozolomide plus radiotherapy vs radiotherapy alone median OS 14.6 vs 12.1 months.",
        publication_types=["Review"],
    )
    uploaded_document = _pubmed_document(
        text="Temozolomide plus radiotherapy vs radiotherapy alone median OS 14.6 vs 12.1 months.",
        publication_types=["Clinical Trial"],
        source_type="text",
    )

    assert document_supports_study_outcome_extraction(trial_document)
    assert not document_supports_study_outcome_extraction(review_document)
    assert not document_supports_study_outcome_extraction(uploaded_document)


def test_extract_study_outcome_drafts_parses_trial_survival_and_hazard_ratio() -> None:
    document = _pubmed_document(
        text=(
            "Temozolomide plus radiotherapy vs radiotherapy alone median OS "
            "14.6 vs 12.1 months; 2-year OS 26.5% vs 10.4%; HR 0.63 "
            "(95% CI 0.52-0.75)."
        ),
        publication_types=["Randomized Controlled Trial"],
    )

    drafts = extract_study_outcome_drafts(document)

    median_os = [
        draft for draft in drafts if draft.outcome_metric == "median_overall_survival"
    ]
    assert len(median_os) == 2
    intervention_median = next(
        draft
        for draft in median_os
        if draft.intervention == "Temozolomide plus radiotherapy"
    )
    comparator_median = next(
        draft for draft in median_os if draft.intervention == "radiotherapy alone"
    )
    assert intervention_median.comparator == "radiotherapy alone"
    assert intervention_median.value == pytest.approx(14.6)
    assert intervention_median.unit == "months"
    assert comparator_median.comparator == "Temozolomide plus radiotherapy"
    assert comparator_median.value == pytest.approx(12.1)

    two_year_os = [
        draft
        for draft in drafts
        if draft.outcome_metric == "two_year_overall_survival_rate"
    ]
    assert {draft.value for draft in two_year_os} == {26.5, 10.4}
    assert all(draft.unit == "percent" for draft in two_year_os)

    hazard_ratio = next(
        draft for draft in drafts if draft.outcome_metric == "hazard_ratio"
    )
    assert hazard_ratio.intervention == "Temozolomide plus radiotherapy"
    assert hazard_ratio.comparator == "radiotherapy alone"
    assert hazard_ratio.value == pytest.approx(0.63)
    assert hazard_ratio.unit == "ratio"
    assert hazard_ratio.confidence_interval_low == pytest.approx(0.52)
    assert hazard_ratio.confidence_interval_high == pytest.approx(0.75)
    assert hazard_ratio.source_pmid == "15758009"
    assert "median OS 14.6" in hazard_ratio.source_quote


def test_in_memory_study_outcome_store_dedupes_and_filters() -> None:
    store = HarnessStudyOutcomeStore()
    space_id = uuid4()
    document_id = uuid4()
    run_id = uuid4()
    draft = StudyOutcomeDraft(
        intervention="Temozolomide plus radiotherapy",
        comparator="radiotherapy alone",
        outcome_metric="median_overall_survival",
        value=14.6,
        unit="months",
        confidence_interval_low=None,
        confidence_interval_high=None,
        population="reported trial population",
        n=None,
        source_pmid="15758009",
        source_quote="median OS 14.6 vs 12.1 months",
        metadata={"extraction_method": "pattern_v1"},
    )

    first_create = store.create_outcomes(
        space_id=space_id,
        document_id=document_id,
        run_id=run_id,
        outcomes=(draft,),
    )
    duplicate_create = store.create_outcomes(
        space_id=space_id,
        document_id=document_id,
        run_id=run_id,
        outcomes=(draft,),
    )

    assert len(first_create) == 1
    assert duplicate_create == []
    assert store.count_outcomes(space_id=space_id) == 1

    filtered = store.list_outcomes(
        space_id=space_id,
        intervention="temozolomide",
        outcome_metric="median_overall_survival",
    )

    assert len(filtered) == 1
    assert filtered[0].document_id == str(document_id)
    assert filtered[0].run_id == str(run_id)


def test_sqlalchemy_study_outcome_store_persists_and_filters(
    db_session: Session,
) -> None:
    space_id = str(uuid4())
    run_id = str(uuid4())
    document_id = str(uuid4())
    db_session.add(
        HarnessRunModel(
            id=run_id,
            space_id=space_id,
            harness_id="research-init",
            title="Research init",
            status="completed",
            input_payload={},
            graph_service_status="ok",
            graph_service_version="test",
        ),
    )
    db_session.commit()
    db_session.add(
        HarnessDocumentModel(
            id=document_id,
            space_id=space_id,
            created_by=str(uuid4()),
            title="Trial outcomes",
            source_type="pubmed",
            filename=None,
            media_type="text/plain",
            sha256="1" * 64,
            byte_size=10,
            page_count=None,
            text_content="trial text",
            text_excerpt="trial text",
            ingestion_run_id=run_id,
            last_enrichment_run_id=None,
            last_extraction_run_id=run_id,
            enrichment_status="completed",
            extraction_status="completed",
            metadata_payload={},
        ),
    )
    db_session.commit()
    store = SqlAlchemyStudyOutcomeStore(db_session)

    store.create_outcomes(
        space_id=space_id,
        document_id=document_id,
        run_id=run_id,
        outcomes=(
            StudyOutcomeDraft(
                intervention="Lomustine plus temozolomide",
                comparator="temozolomide",
                outcome_metric="median_overall_survival",
                value=48.1,
                unit="months",
                confidence_interval_low=None,
                confidence_interval_high=None,
                population="MGMT-methylated subgroup",
                n=None,
                source_pmid="30782343",
                source_quote="median OS 48.1 vs 31.4 months",
                metadata={"extraction_method": "pattern_v1"},
            ),
        ),
    )

    outcomes = store.list_outcomes(
        space_id=space_id,
        intervention="lomustine",
        population="MGMT",
        outcome_metric="median_overall_survival",
    )

    assert len(outcomes) == 1
    assert outcomes[0].value == pytest.approx(48.1)
    assert outcomes[0].metadata["extraction_method"] == "pattern_v1"
