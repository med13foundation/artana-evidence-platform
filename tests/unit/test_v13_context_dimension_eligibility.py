"""Immutable replay regressions for the consumed V13 context failure."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import cast

import pytest
from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    StructuredModelSemanticError,
)

from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    bind_source_unit_normalization,
    canonical_json_sha256,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_contracts import (
    SourceUnitNormalizationOutputV13,
)
from tests.unit.v13_context_dimension_test_support import (
    _CONSUMED_FIXTURE_SHA256,
    _CONSUMED_JOURNAL_PATH,
    _CONSUMED_NORMALIZATION_SHA256,
    _CONSUMED_ORIGINAL_SHA256,
    _CONSUMED_REPORT_FILE_SHA256,
    _CONSUMED_REPORT_PATH,
    _CONSUMED_RESULT_PATH,
    _CONSUMED_SOURCE_SHA256,
    _FIXTURE_PATH,
    _fixture,
    _original,
    _payload,
    _unit,
)


def test_consumed_singleton_genotype_payload_remains_fail_closed() -> None:
    fixture = _fixture()
    source = cast("str", fixture["source"])
    unit = _unit(source)
    original = _original(fixture=fixture, unit=unit)
    raw_normalization = _payload(fixture, "normalization")
    custody = _payload(fixture, "custody")
    canonical_result = cast(
        "dict[str, object]",
        json.loads(_CONSUMED_RESULT_PATH.read_text(encoding="utf-8")),
    )
    canonical_attempts = cast(
        "list[dict[str, object]]",
        canonical_result["attempts"],
    )
    journal_entries = [
        cast("dict[str, object]", json.loads(line))
        for line in _CONSUMED_JOURNAL_PATH.read_text(encoding="utf-8").splitlines()
    ]
    assert hashlib.sha256(_FIXTURE_PATH.read_bytes()).hexdigest() == (
        _CONSUMED_FIXTURE_SHA256
    )
    assert hashlib.sha256(_CONSUMED_REPORT_PATH.read_bytes()).hexdigest() == (
        _CONSUMED_REPORT_FILE_SHA256
    )
    assert custody["committed_result_report_sha256"] == (_CONSUMED_REPORT_FILE_SHA256)
    assert (
        hashlib.sha256(_CONSUMED_RESULT_PATH.read_bytes()).hexdigest()
        == custody["serialized_result_sha256"]
    )
    assert (
        hashlib.sha256(_CONSUMED_JOURNAL_PATH.read_bytes()).hexdigest()
        == custody["journal_sha256"]
    )
    assert custody["decision"] == "STOP_WORKFLOW_INVALID"
    assert custody["qualification_eligible"] is False
    assert custody["hidden_unit_authorized"] is False
    assert custody["graph_persistence_authorized"] is False
    assert hashlib.sha256(source.encode("utf-8")).hexdigest() == (
        _CONSUMED_SOURCE_SHA256
    )
    assert custody["source_sha256"] == _CONSUMED_SOURCE_SHA256
    assert canonical_json_sha256(_payload(fixture, "original")) == (
        _CONSUMED_ORIGINAL_SHA256
    )
    assert custody["original_output_sha256"] == _CONSUMED_ORIGINAL_SHA256
    assert custody["normalization_output_sha256"] == _CONSUMED_NORMALIZATION_SHA256
    assert (
        canonical_json_sha256(raw_normalization)
        == custody["normalization_output_sha256"]
    )
    assert custody["primary_provider_response_id"] == (
        "resp_0e9d60fe24c62f7a006a5c9b0bc78481988f076edb4407be10"
    )
    assert custody["normalization_provider_response_id"] == (
        "resp_095caf547dd21771006a5c9b12aae4819987474768f06ed065"
    )
    assert custody["sealed_report_sha256"] == (
        "eca2fd78fd4d875896b828f7b8397c66b23a76933049aab6279ec76b23354244"
    )
    assert custody["serialized_result_sha256"] == (
        "09f1a1611ff2b232fa0565c471758ebcf7ad3ea3c302d1475f582262776d7cf4"
    )
    assert custody["journal_sha256"] == (
        "d5458f71078519d5b22a4a01baea154bd3067606af5b8183181a7a016d868f31"
    )
    assert canonical_result["decision"] == custody["decision"]
    assert canonical_attempts[0]["raw_model_payload"] == _payload(fixture, "original")
    assert canonical_attempts[1]["raw_model_payload"] == raw_normalization
    assert (
        canonical_attempts[0]["provider_response_id"]
        == custody["primary_provider_response_id"]
    )
    assert (
        canonical_attempts[1]["provider_response_id"]
        == custody["normalization_provider_response_id"]
    )
    assert journal_entries[-1]["report_sha256"] == custody["sealed_report_sha256"]
    assert journal_entries[-1]["decision"] == custody["decision"]
    normalized = SourceUnitNormalizationOutputV13.model_validate(raw_normalization)

    with pytest.raises(
        StructuredModelSemanticError,
        match="context dimension spans must be verbatim source evidence",
    ):
        bind_source_unit_normalization(normalized, unit=unit, original=original)


def test_context_free_counterfactual_binds_without_mutating_consumed_payload() -> None:
    fixture = _fixture()
    source = cast("str", fixture["source"])
    unit = _unit(source)
    original = _original(fixture=fixture, unit=unit)
    consumed_payload = _payload(fixture, "normalization")
    diagnostic_payload = deepcopy(consumed_payload)
    diagnostic_payload["context_dimensions"] = []

    normalized = SourceUnitNormalizationOutputV13.model_validate(diagnostic_payload)
    result = bind_source_unit_normalization(normalized, unit=unit, original=original)

    assert len(result.accepted) == 2
    assert len(result.controlled_event_links) == 1
    assert result.output.context_dimensions == ()
    assert canonical_json_sha256(consumed_payload) == _CONSUMED_NORMALIZATION_SHA256
