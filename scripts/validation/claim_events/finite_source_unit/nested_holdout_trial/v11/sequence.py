"""Create-once authorization for the single V11 live diagnostic."""

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
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11.custody import (
    V11_PROMPT_CONTENT_DIGESTS,
    validate_v11_attempt_chain,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11.replay import (
    V11_ARCHIVE_SHA256,
    V11_EXPERT_GRAPH_SHA256,
    V11_PROJECTION_SET_SHA256,
    require_replayed_v11_qualification,
)
from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
    sha256_json,
)
from scripts.validation.claim_frames.evidence import collect_repository_evidence
from scripts.validation.claim_frames.provider_receipts import (
    OpenAIProviderReceiptVerifier,
    verify_provider_receipts,
)

_SCHEMA_VERSION: Final = "tg04_nested_event_holdout.v11"
_SELECTION_SEED: Final = (
    "a1347ca7588d7b1b83629f74406cadb294f65c091659daa64011b1d815018005"
)
_UNIT_ID: Final = (
    "source-unit-7c8d867e63ba86da5d69978529ab5ff25686efd7035d2ba50ac899cc8f89743d"
)
_SOURCE_IDENTITY: Final[tuple[tuple[str, object], ...]] = (
    (
        "case_id",
        "bionlp-ge-2011-holdout:PMC-2806624-08-MATERIALS_AND_METHODS-01",
    ),
    ("unit_id", _UNIT_ID),
    ("unit_index", 141),
    ("source_start", 19662),
    ("source_end", 19960),
    (
        "source_sha256",
        "e8516818fb002201c7ca53c487d114ceb71fae1f35bc4d972977e5e181af37b9",
    ),
    (
        "input_sha256",
        "d5242f5c0aae5bffc5874c486c5ef7d933a86c95bd7a9445ed32a80895e83b2f",
    ),
)
_PROMPT_DIGESTS: Final = V11_PROMPT_CONTENT_DIGESTS
_CRITICAL_GATE_REQUIREMENTS: Final = frozenset(
    {
        "agent_execution_complete",
        "audit_attempt_topology_exact",
        "audit_identity_bound",
        "invalid_agent_output_zero",
        "normalization_mapping_complete",
        "provider_lineage_complete",
        "provider_receipts_verified",
        "raw_agent_outputs_preserved",
        "repeat_index_pre_registered",
    }
)

_DEFINITION: Final = RepeatSequenceDefinition(
    ordinal="eleventh",
    schema_version=_SCHEMA_VERSION,
    reservation_schema_version="tg04_v11_repeat_reservation.v1",
    provider_reservation_schema_version="tg04_v11_provider_reservation.v1",
    selection_seed=_SELECTION_SEED,
    projection_set_sha256=V11_PROJECTION_SET_SHA256,
    unit_id=_UNIT_ID,
    registry_path="artana-evaluation/tg04-v11",
    critical_gate_requirements=_CRITICAL_GATE_REQUIREMENTS,
    repeat_indices=frozenset({1}),
    expected_provider_call_count=3,
    execution_lease_schema_version="tg04_v11_execution_lease.v1",
    archive_sha256=V11_ARCHIVE_SHA256,
    expert_graph_sha256=V11_EXPERT_GRAPH_SHA256,
    source_identity=_SOURCE_IDENTITY,
    prompt_digests=_PROMPT_DIGESTS,
    successful_reservation_status="FINALIZED_DIAGNOSTIC",
    require_pass_for_finalization=False,
    required_attempt_roles=(
        ("primary", "primary", "original_extraction"),
        (
            "structure_normalization",
            "structure_normalization",
            "normalized_extraction",
        ),
        ("normalized_review", "normalized_review", "normalized_review"),
    ),
    allow_schema_retry=False,
    execution_path="three_agent_source_normalization_review",
    require_output_schema_custody=True,
    allow_terminal_workflow_failure=True,
)


@dataclass(frozen=True, slots=True)
class EleventhRepeatAuthorization:
    """One exclusive reservation before the three V11 provider calls."""

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


def reserve_eleventh_repeat(
    *,
    repository_root: Path,
    run_id: str,
    repeat_index: int,
    output: Path,
) -> EleventhRepeatAuthorization:
    """Atomically reserve the one-shot V11 diagnostic."""

    return reserve_repeat(
        definition=_DEFINITION,
        runtime=_runtime(),
        authorization_factory=_authorization_from_values,
        request=RepeatReservationRequest(
            repository_root=repository_root,
            run_id=run_id,
            repeat_index=repeat_index,
            output=output,
            previous_report=None,
        ),
    )


def finalize_eleventh_repeat(
    authorization: EleventhRepeatAuthorization,
    *,
    report: dict[str, object],
) -> None:
    """Seal either scientific outcome after full receipt-backed replay."""

    finalize_repeat(
        authorization,
        definition=_DEFINITION,
        runtime=_runtime(),
        report=report,
    )


def recover_eleventh_repeat(
    *,
    repository_root: Path,
    run_id: str,
    repeat_index: int,
    output: Path,
) -> dict[str, object]:
    """Seal an already written V11 report without another provider call."""

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
        raise RuntimeError("eleventh holdout recovery evidence is unavailable") from exc
    if not isinstance(reservation, dict) or not isinstance(report, dict):
        raise TypeError("eleventh recovery evidence must be JSON objects")
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
        raise RuntimeError("eleventh holdout recovery identity is invalid")
    authorization = EleventhRepeatAuthorization(
        run_id=run_id,
        repeat_index=repeat_index,
        output=output.resolve(),
        reservation_path=reservation_path,
        token=token,
        repository_root=repository_root.resolve(),
        repository_evidence=repository_evidence,
    )
    finalize_eleventh_repeat(authorization, report=report)
    return report


def _runtime() -> RepeatSequenceRuntime:
    return RepeatSequenceRuntime(
        collect_repository_evidence=collect_repository_evidence,
        replay_qualification=require_replayed_v11_qualification,
        provider_verifier_factory=OpenAIProviderReceiptVerifier.from_environment,
        verify_provider_receipts=verify_provider_receipts,
        sha256_json=sha256_json,
        git_runner=subprocess.run,
        token_factory=token_hex,
        now_utc=lambda: datetime.now(UTC),
        validate_attempt_chain=validate_v11_attempt_chain,
    )


def _authorization_from_values(
    values: RepeatAuthorizationValues,
) -> EleventhRepeatAuthorization:
    return EleventhRepeatAuthorization(
        run_id=values.run_id,
        repeat_index=values.repeat_index,
        output=values.output,
        reservation_path=values.reservation_path,
        token=values.token,
        repository_root=values.repository_root,
        repository_evidence=values.repository_evidence,
    )


__all__ = [
    "EleventhRepeatAuthorization",
    "finalize_eleventh_repeat",
    "recover_eleventh_repeat",
    "reserve_eleventh_repeat",
]
