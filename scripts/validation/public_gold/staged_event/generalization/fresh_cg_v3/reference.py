"""Build the V3 exposed-case reference only from blinded adjudication evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.contracts import (
    ExactSourceSpan,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.reference_contracts import (
    ContextParticipantReference,
    FreshCGTwoLaneReference,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v3.contracts import (
    ExposedCaseReferenceV3,
    RootCauseConsensus,
    V3CategoricalReference,
)


def build_exposed_reference(
    *,
    v2_reference_path: Path,
    dispute_packet_path: Path,
    consensus_path: Path,
) -> ExposedCaseReferenceV3:
    """Apply only adjudicated reference corrections; never read model output."""

    v2 = FreshCGTwoLaneReference.model_validate_json(
        v2_reference_path.read_text(encoding="utf-8")
    )
    consensus = RootCauseConsensus.model_validate_json(
        consensus_path.read_text(encoding="utf-8")
    )
    packet = _object(json.loads(dispute_packet_path.read_text(encoding="utf-8")))
    if _sha256(dispute_packet_path) != consensus.dispute_packet_sha256:
        raise ValueError("consensus dispute-packet hash changed")
    case = next(item for item in v2.cases if item.case_id == consensus.case_id)
    candidates = _object(packet["candidate_interpretations"])
    direction = _selected_string(
        _object(candidates["direction"]),
        consensus.corrections.direction.selected_candidate_id,
    )
    uncertainty = _selected_string(
        _object(candidates["uncertainty"]),
        consensus.corrections.uncertainty.selected_candidate_id,
    )
    context = _selected_context(
        _object(candidates["contextual_participants"]),
        consensus.corrections.contextual_participants.selected_candidate_id,
    )
    role = case.argument_roles[0]
    if (
        role.value is None
        or case.comparison.value is None
        or case.polarity.value is None
    ):
        raise ValueError("unchanged V2 reference fields must remain resolved")
    if case.statistics.value is None:
        raise ValueError("unchanged V2 statistics must remain resolved")
    study_activity = ExactSourceSpan(
        start=316,
        end=336,
        text="We have investigated",
    )
    return ExposedCaseReferenceV3(
        case_id=case.case_id,
        document_id=case.document_id,
        source_sha256=case.source_sha256,
        direct_cg_event=case.direct_cg_event,
        direct_cg_participants=case.direct_cg_participants,
        direct_cg_reference_sha256=case.direct_cg_reference_sha256,
        role=V3CategoricalReference(
            field_id=role.field_id,
            value=role.value,
            accepted_evidence=role.accepted_evidence,
            source_general_rule=(
                "Evaluate role only after the direct occurrence maps exactly."
            ),
        ),
        direction=V3CategoricalReference(
            field_id="direction",
            value=direction,
            accepted_evidence=(study_activity,),
            source_general_rule=consensus.corrections.direction.source_general_rule,
        ),
        comparison=V3CategoricalReference(
            field_id="comparison",
            value=case.comparison.value,
            accepted_evidence=case.comparison.accepted_evidence,
            source_general_rule="No explicit comparison is present.",
        ),
        polarity=V3CategoricalReference(
            field_id="polarity",
            value=case.polarity.value,
            accepted_evidence=case.polarity.accepted_evidence,
            source_general_rule="The study activity is affirmatively stated.",
        ),
        uncertainty=V3CategoricalReference(
            field_id="uncertainty",
            value=uncertainty,
            accepted_evidence=(study_activity,),
            source_general_rule=consensus.corrections.uncertainty.source_general_rule,
        ),
        statistics=case.statistics.value,
        contextual_participants=context,
        dispute_packet_sha256=consensus.dispute_packet_sha256,
        consensus_sha256=_sha256(consensus_path),
        adjudicator_sha256_by_id=consensus.adjudicator_sha256_by_id,
        source_general_corrections=(
            consensus.corrections.contextual_participants.source_general_rule,
            consensus.corrections.direction.source_general_rule,
            consensus.corrections.uncertainty.source_general_rule,
        ),
    )


def write_exposed_reference(
    path: Path,
    reference: ExposedCaseReferenceV3,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(reference.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _selected_string(candidates: dict[str, object], selected: str | None) -> str:
    if selected is None:
        raise ValueError("corrected categorical field lacks selected candidate")
    value = candidates.get(selected)
    if not isinstance(value, str):
        raise TypeError("selected categorical candidate is not a string")
    return value


def _selected_context(
    candidates: dict[str, object],
    selected: str | None,
) -> tuple[ContextParticipantReference, ...]:
    if selected is None:
        raise ValueError("corrected context lacks selected candidate")
    raw = candidates.get(selected)
    if not isinstance(raw, list):
        raise TypeError("selected context candidate is not a list")
    return tuple(ContextParticipantReference.model_validate(item) for item in raw)


def _object(value: object) -> dict[str, object]:
    return cast("dict[str, object]", value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = ["build_exposed_reference", "write_exposed_reference"]
