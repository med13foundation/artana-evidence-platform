"""Support graph promotion of variant observation proposals."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_api.proposal_entity_payloads import optional_json_string
from artana_evidence_api.runtime.agent_output_schema import SourceMeasurementNumber
from artana_evidence_api.types.common import JSONObject
from artana_evidence_api.types.graph_contracts import (
    KernelObservationResponse,
    KernelProvenanceCreateRequest,
)
from fastapi import HTTPException, status
from pydantic import ValidationError

if TYPE_CHECKING:
    from artana_evidence_api.proposal_store import HarnessProposalRecord


def build_source_measurement_provenance_request(
    *,
    proposal: HarnessProposalRecord,
    mapping_confidence: float,
) -> KernelProvenanceCreateRequest | None:
    """Translate a validated proposal envelope into graph provenance."""
    raw_measurement = proposal.payload.get("source_measurement")
    if raw_measurement is None:
        return None
    try:
        measurement_contract = SourceMeasurementNumber.model_validate(raw_measurement)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source-measurement promotion requires a valid provenance envelope.",
        ) from exc
    measurement = measurement_contract.model_dump(mode="json")
    source_locator = measurement_contract.source_locator
    document_id = proposal.document_id or _metadata_text(
        proposal,
        key="document_id",
        default="unknown-document",
    )
    return KernelProvenanceCreateRequest(
        source_type=_metadata_text(
            proposal,
            key="document_source_type",
            default=proposal.source_kind,
        ),
        source_ref=f"document:{document_id}#{source_locator}",
        extraction_run_id=proposal.run_id,
        mapping_method="agent_source_measurement",
        mapping_confidence=mapping_confidence,
        agent_model=optional_json_string(proposal.metadata.get("agent_model")),
        raw_input={
            "document_id": document_id,
            "source_measurement": measurement,
        },
    )


def _metadata_text(
    proposal: HarnessProposalRecord,
    *,
    key: str,
    default: str,
) -> str:
    value = optional_json_string(proposal.metadata.get(key))
    return value or default


def graph_observation_promotion_result(
    *,
    observation: KernelObservationResponse,
) -> JSONObject:
    """Return stable proposal metadata for one promoted observation."""
    return {
        "graph_observation_id": str(observation.id),
        "graph_observation_subject_id": str(observation.subject_id),
        "graph_observation_variable_id": observation.variable_id,
    }


__all__ = [
    "build_source_measurement_provenance_request",
    "graph_observation_promotion_result",
]
