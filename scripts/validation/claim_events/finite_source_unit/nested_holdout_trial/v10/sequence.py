"""Create-once sequential authorization for V10 live repeats."""

from __future__ import annotations

import json
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
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v10.qualification import (
    TENTH_ARCHIVE_SHA256,
    TENTH_EXPERT_GRAPH_SHA256,
    TENTH_PROJECTION_SET_SHA256,
    TENTH_PROMPT_DIGESTS,
    TENTH_SOURCE_IDENTITY,
    require_replayed_tenth_qualification,
    require_replayed_tenth_terminal_failure,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v10.terminal_sequence import (
    finalize_terminal_failure,
)
from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
    sha256_json,
)
from scripts.validation.claim_frames.evidence import collect_repository_evidence
from scripts.validation.claim_frames.provider_receipts import (
    OpenAIProviderReceiptVerifier,
    verify_provider_receipts,
)

_SCHEMA_VERSION: Final = "tg04_nested_event_holdout.v10"
_SELECTION_SEED: Final = (
    "59107ff0d23bf9543b23df2add9885d0bab4c7dd0c38ffbd18e030734cc2c897"
)
_UNIT_ID: Final = (
    "source-unit-463bf8e1b37963d7547eb57c6d51545a466050b2c6c9faa9abc76ff8e2330914"
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
    ordinal="tenth",
    schema_version=_SCHEMA_VERSION,
    reservation_schema_version="tg04_v10_repeat_reservation.v2",
    provider_reservation_schema_version="tg04_v10_provider_reservation.v2",
    selection_seed=_SELECTION_SEED,
    projection_set_sha256=TENTH_PROJECTION_SET_SHA256,
    unit_id=_UNIT_ID,
    registry_path="artana-evaluation/tg04-v10",
    critical_gate_requirements=_CRITICAL_GATE_REQUIREMENTS,
    repeat_indices=_REPEAT_INDICES,
    expected_provider_call_count=_EXPECTED_PROVIDER_CALL_COUNT,
    execution_lease_schema_version="tg04_v10_execution_lease.v1",
    archive_sha256=TENTH_ARCHIVE_SHA256,
    expert_graph_sha256=TENTH_EXPERT_GRAPH_SHA256,
    source_identity=TENTH_SOURCE_IDENTITY,
    prompt_digests=TENTH_PROMPT_DIGESTS,
    successful_reservation_status="FINALIZED_PASS",
    terminal_seal_schema_version="tg04_v10_terminal_seal.v1",
    require_pass_for_finalization=True,
)


@dataclass(frozen=True, slots=True)
class TenthRepeatAuthorization:
    """One exclusive V10 reservation required before provider use."""

    run_id: str
    repeat_index: int
    output: Path
    reservation_path: Path
    token: str
    repository_root: Path
    repository_evidence: dict[str, object]

    def require_active(self) -> None:
        require_active(self, definition=_DEFINITION)

    def require_repository_unchanged(self) -> None:
        require_repository_unchanged(
            self,
            definition=_DEFINITION,
            collect_repository_evidence=collect_repository_evidence,
        )

    def provider_evidence_unit_id(self) -> str:
        return provider_evidence_unit_id(self, definition=_DEFINITION)


def reserve_tenth_repeat(
    *,
    repository_root: Path,
    run_id: str,
    repeat_index: int,
    output: Path,
    previous_report: Path | None,
) -> TenthRepeatAuthorization:
    """Atomically reserve V10 and require pass-before-next ordering."""

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


def finalize_tenth_repeat(
    authorization: TenthRepeatAuthorization,
    *,
    report: dict[str, object],
) -> None:
    """Seal one V10 reservation with report and gate identity."""

    finalize_repeat(
        authorization,
        definition=_DEFINITION,
        runtime=_runtime(),
        report=report,
    )


def _finalize_tenth_terminal_failure(
    authorization: TenthRepeatAuthorization,
    *,
    report: dict[str, object],
) -> None:
    """Seal a receipt-backed V10 semantic failure as permanently non-passing."""

    finalize_terminal_failure(
        authorization,
        definition=_DEFINITION,
        runtime=_runtime(),
        report=report,
        replay_terminal_failure=require_replayed_tenth_terminal_failure,
    )


def finalize_tenth_outcome(
    authorization: TenthRepeatAuthorization,
    *,
    report: dict[str, object],
) -> None:
    """Derive the only allowed terminal state from receipt-bound agent output."""

    agent_outputs = report.get("agent_outputs")
    if not isinstance(agent_outputs, dict):
        raise TypeError("tenth holdout agent outputs are unavailable")
    error_type = agent_outputs.get("error_type")
    verification = agent_outputs.get("verification")
    if error_type is None and isinstance(verification, dict):
        finalize_tenth_repeat(authorization, report=report)
        return
    if error_type == "StructuredModelSemanticError" and verification is None:
        _finalize_tenth_terminal_failure(authorization, report=report)
        return
    raise RuntimeError("tenth holdout outcome category is not sealable")


def recover_tenth_outcome(
    *,
    repository_root: Path,
    run_id: str,
    repeat_index: int,
    output: Path,
) -> dict[str, object]:
    """Seal an already written V10 report without issuing another provider call."""

    completed = subprocess.run(
        (
            "git",
            "-C",
            str(repository_root),
            "rev-parse",
            "--path-format=absolute",
            "--git-path",
            _DEFINITION.registry_path,
        ),
        check=True,
        capture_output=True,
        text=True,
    )
    reservation_path = Path(completed.stdout.strip()) / f"repeat-{repeat_index}.json"
    try:
        reservation = json.loads(reservation_path.read_text(encoding="utf-8"))
        report = json.loads(output.resolve().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise RuntimeError("tenth holdout recovery evidence is unavailable") from exc
    if not isinstance(reservation, dict) or not isinstance(report, dict):
        raise TypeError("tenth holdout recovery evidence must be JSON objects")
    repository_evidence = reservation.get("repository_evidence")
    token = reservation.get("token")
    if (
        reservation.get("status") != "EXECUTING"
        or reservation.get("run_id") != run_id
        or reservation.get("repeat_index") != repeat_index
        or reservation.get("output") != str(output.resolve())
        or not isinstance(repository_evidence, dict)
        or not isinstance(token, str)
    ):
        raise RuntimeError("tenth holdout recovery identity is invalid")
    authorization = TenthRepeatAuthorization(
        run_id=run_id,
        repeat_index=repeat_index,
        output=output.resolve(),
        reservation_path=reservation_path,
        token=token,
        repository_root=repository_root.resolve(),
        repository_evidence=repository_evidence,
    )
    finalize_tenth_outcome(authorization, report=report)
    return report


def _runtime() -> RepeatSequenceRuntime:
    return RepeatSequenceRuntime(
        collect_repository_evidence=collect_repository_evidence,
        replay_qualification=require_replayed_tenth_qualification,
        provider_verifier_factory=OpenAIProviderReceiptVerifier.from_environment,
        verify_provider_receipts=verify_provider_receipts,
        sha256_json=sha256_json,
        git_runner=subprocess.run,
        token_factory=token_hex,
        now_utc=lambda: datetime.now(UTC),
    )


def _authorization_from_values(
    values: RepeatAuthorizationValues,
) -> TenthRepeatAuthorization:
    return TenthRepeatAuthorization(
        run_id=values.run_id,
        repeat_index=values.repeat_index,
        output=values.output,
        reservation_path=values.reservation_path,
        token=values.token,
        repository_root=values.repository_root,
        repository_evidence=values.repository_evidence,
    )


__all__ = [
    "TenthRepeatAuthorization",
    "finalize_tenth_outcome",
    "finalize_tenth_repeat",
    "recover_tenth_outcome",
    "reserve_tenth_repeat",
]
