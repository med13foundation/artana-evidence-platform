"""Observation request provenance contract tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
from artana_evidence_db.graph_api_schemas.kernel_graph_schemas import (
    KernelProvenanceCreateRequest,
)
from artana_evidence_db.graph_api_schemas.kernel_observation_schemas import (
    KernelObservationCreateRequest,
)
from pydantic import ValidationError


def _provenance() -> KernelProvenanceCreateRequest:
    return KernelProvenanceCreateRequest(
        source_type="document_extraction",
        source_ref="document:test#raw_record.text",
        mapping_method="agent_source_measurement",
        raw_input={"source_measurement": {"literal_span": "0.125"}},
    )


def test_ai_observation_accepts_inline_provenance() -> None:
    request = KernelObservationCreateRequest(
        subject_id=uuid4(),
        variable_id="VAR_ALLELE_FREQUENCY",
        value=0.125,
        provenance=_provenance(),
        observation_origin="AI_AUTHORED",
    )

    assert request.provenance is not None
    assert request.provenance_id is None


@pytest.mark.parametrize(
    ("provenance_id", "provenance", "origin"),
    [
        (uuid4(), _provenance(), "AI_AUTHORED"),
        (None, _provenance(), "MANUAL"),
        (None, None, "AI_AUTHORED"),
    ],
)
def test_observation_rejects_ambiguous_or_missing_provenance(
    provenance_id: object,
    provenance: KernelProvenanceCreateRequest | None,
    origin: str,
) -> None:
    with pytest.raises(ValidationError):
        KernelObservationCreateRequest.model_validate(
            {
                "subject_id": str(uuid4()),
                "variable_id": "VAR_ALLELE_FREQUENCY",
                "value": 0.125,
                "provenance_id": provenance_id,
                "provenance": provenance,
                "observation_origin": origin,
            },
        )
