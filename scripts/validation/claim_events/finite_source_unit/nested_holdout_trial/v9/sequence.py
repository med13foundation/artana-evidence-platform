"""Create-once, sequential authorization for ninth-holdout live repeats."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_hex
from typing import Final

from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.repeat_sequence import (
    RepeatAuthorizationValues,
    RepeatReservationRequest,
    RepeatSequenceDefinition,
    RepeatSequenceRuntime,
    finalize_repeat,
    provider_evidence_unit_id,
    require_active,
    require_repository_unchanged,
    reserve_repeat,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v9.qualification import (
    require_replayed_ninth_qualification,
)
from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
    sha256_json,
)
from scripts.validation.claim_frames.evidence import collect_repository_evidence
from scripts.validation.claim_frames.provider_receipts import (
    OpenAIProviderReceiptVerifier,
    verify_provider_receipts,
)

_SCHEMA_VERSION: Final = "tg04_nested_event_holdout.v9"
_SELECTION_SEED: Final = (
    "b1498772852d13333a1201ddaa02c55098fdcc183bee01ef9da0915faf0ceafd"
)
_PROJECTION_SET_SHA256: Final = (
    "9163b0d185bdafdc093d158ec0a5b4da0e37d950904d998d822084d04f455915"
)
_UNIT_ID: Final = (
    "source-unit-eb96c6e419821d8b930aebe6c1a891e185a0fcddccd3d05efa6ba05ef37601c0"
)
_REPEAT_INDICES: Final = frozenset({1, 2, 3})
_EXPECTED_PROVIDER_CALL_COUNT: Final = 2
_CRITICAL_GATE_REQUIREMENTS: Final = frozenset(
    {
        "agent_execution_complete",
        "all_candidates_source_entailed",
        "attempt_model_identity_bound",
        "audit_attempt_topology_exact",
        "audit_identity_bound",
        "candidate_inventory_complete",
        "complete_acceptable_projection_recovered",
        "controlled_event_link_ambiguity_zero",
        "controlled_event_reference_orphan_zero",
        "controlled_event_target_orphan_zero",
        "invalid_agent_output_zero",
        "provider_lineage_complete",
        "provider_receipts_verified",
        "repeat_index_pre_registered",
        "sealed_graph_shape_verified",
        "single_representation_family_recovered",
        "unmatched_trusted_candidate_zero",
    },
)

_DEFINITION: Final = RepeatSequenceDefinition(
    ordinal="ninth",
    schema_version=_SCHEMA_VERSION,
    reservation_schema_version="tg04_v9_repeat_reservation.v1",
    provider_reservation_schema_version="tg04_v9_provider_reservation.v1",
    selection_seed=_SELECTION_SEED,
    projection_set_sha256=_PROJECTION_SET_SHA256,
    unit_id=_UNIT_ID,
    registry_path="artana-evaluation/tg04-v9",
    critical_gate_requirements=_CRITICAL_GATE_REQUIREMENTS,
    repeat_indices=_REPEAT_INDICES,
    expected_provider_call_count=_EXPECTED_PROVIDER_CALL_COUNT,
)


@dataclass(frozen=True, slots=True)
class NinthRepeatAuthorization:
    """One exclusive reservation that must exist before a provider call."""

    run_id: str
    repeat_index: int
    output: Path
    reservation_path: Path
    token: str
    repository_root: Path
    repository_evidence: dict[str, object]

    def require_active(self) -> None:
        """Reject forged, finalized, or replaced reservations."""

        require_active(self, definition=_DEFINITION)

    def require_repository_unchanged(self) -> None:
        """Require the live tracked tree to equal the reservation snapshot."""

        require_repository_unchanged(
            self,
            definition=_DEFINITION,
            collect_repository_evidence=collect_repository_evidence,
        )

    def provider_evidence_unit_id(self) -> str:
        """Bind provider calls to this reservation and tracked repository tree."""

        return provider_evidence_unit_id(self, definition=_DEFINITION)


def reserve_ninth_repeat(
    *,
    repository_root: Path,
    run_id: str,
    repeat_index: int,
    output: Path,
    previous_report: Path | None,
) -> NinthRepeatAuthorization:
    """Atomically reserve one repeat and enforce pass-before-next ordering."""

    return reserve_repeat(
        definition=_DEFINITION,
        runtime=_runtime(),
        authorization_factory=_authorization_from_values,
        request=RepeatReservationRequest(
            repository_root=repository_root,
            run_id=run_id,
            repeat_index=repeat_index,
            output=output,
            previous_report=previous_report,
        ),
    )


def finalize_ninth_repeat(
    authorization: NinthRepeatAuthorization,
    *,
    report: dict[str, object],
) -> None:
    """Seal one reservation with the immutable report identity and gate result."""

    finalize_repeat(
        authorization,
        definition=_DEFINITION,
        runtime=_runtime(),
        report=report,
    )


def _runtime() -> RepeatSequenceRuntime:
    return RepeatSequenceRuntime(
        collect_repository_evidence=collect_repository_evidence,
        replay_qualification=require_replayed_ninth_qualification,
        provider_verifier_factory=OpenAIProviderReceiptVerifier.from_environment,
        verify_provider_receipts=verify_provider_receipts,
        sha256_json=sha256_json,
        git_runner=subprocess.run,
        token_factory=token_hex,
        now_utc=lambda: datetime.now(UTC),
    )


def _authorization_from_values(
    values: RepeatAuthorizationValues,
) -> NinthRepeatAuthorization:
    return NinthRepeatAuthorization(
        run_id=values.run_id,
        repeat_index=values.repeat_index,
        output=values.output,
        reservation_path=values.reservation_path,
        token=values.token,
        repository_root=values.repository_root,
        repository_evidence=values.repository_evidence,
    )


__all__ = [
    "NinthRepeatAuthorization",
    "finalize_ninth_repeat",
    "reserve_ninth_repeat",
]
