"""Unit tests for normalized source-result capture metadata."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    attach_source_capture_metadata,
    source_result_capture_metadata,
)


def test_source_result_capture_metadata_normalizes_registered_source() -> None:
    capture = source_result_capture_metadata(
        source_key="clinical-trials",
        capture_stage=SourceCaptureStage.SOURCE_DOCUMENT,
        capture_method="research_plan",
        locator="clinical_trials:document:abc123",
        external_id="NCT00000000",
        retrieved_at=datetime(2026, 4, 25, 12, 0, tzinfo=UTC),
        run_id="run-1",
        query="MED13",
        query_payload={"query": "MED13"},
        result_count=3,
        provenance={"provider": "clinicaltrials.gov"},
    )

    assert capture["source_key"] == "clinical_trials"
    assert capture["source_family"] == "clinical"
    assert capture["capture_stage"] == "source_document"
    assert capture["capture_method"] == "research_plan"
    assert capture["retrieved_at"] == "2026-04-25T12:00:00+00:00"
    assert capture["query_payload"] == {"query": "MED13"}
    assert capture["result_count"] == 3
    assert capture["provenance"] == {"provider": "clinicaltrials.gov"}


def test_source_result_capture_rejects_unknown_source() -> None:
    with pytest.raises(ValueError, match="Unknown source key"):
        source_result_capture_metadata(
            source_key="not_registered",
            capture_stage=SourceCaptureStage.SOURCE_DOCUMENT,
            capture_method="research_plan",
            locator="not_registered:1",
        )


def test_source_result_capture_rejects_invalid_retrieved_at_string() -> None:
    with pytest.raises(ValueError, match="retrieved_at"):
        source_result_capture_metadata(
            source_key="pubmed",
            capture_stage=SourceCaptureStage.SEARCH_RESULT,
            capture_method="direct_source_search",
            locator="pubmed:search:1",
            retrieved_at="not a timestamp",
        )


def test_source_result_capture_rejects_naive_retrieved_at() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        source_result_capture_metadata(
            source_key="pubmed",
            capture_stage=SourceCaptureStage.SEARCH_RESULT,
            capture_method="direct_source_search",
            locator="pubmed:search:1",
            retrieved_at="2026-04-25T12:00:00",
        )


def test_attach_source_capture_metadata_uses_stable_key() -> None:
    metadata = attach_source_capture_metadata(
        metadata={"source": "research-init-pubmed"},
        source_capture={"source_key": "pubmed", "locator": "pubmed:1"},
    )

    assert metadata == {
        "source": "research-init-pubmed",
        "source_capture": {"source_key": "pubmed", "locator": "pubmed:1"},
    }
