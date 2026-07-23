"""Synthetic qualification of the direct foreground V11 transport."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import cast

from scripts.validation.provider_receipt_boundary.background.contracts import (
    TelemetryProviderRequestV2,
)
from scripts.validation.provider_receipt_boundary.foreground import (
    ForegroundExecutionRuntime,
    execute_foreground_provider_call_telemetry_v2,
)
from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.attempts import (
    acknowledge_attempt,
    reserve_attempt,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    StageCustodyInput,
    StageCustodyPaths,
    persist_stage_custody,
    write_json_atomic,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.provider import (
    provider_format,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.config import (
    DEFAULT_PATHS,
    MODEL,
    QUALIFICATION_ID,
    QUALIFICATION_TIMEOUT_SECONDS,
    REASONING_EFFORT,
    REPO,
    V11Run2Paths,
)

QUALIFICATION_PASS = "FOREGROUND_TRANSPORT_QUALIFIED"
QUALIFICATION_INVALID = "INVALID_FOREGROUND_TRANSPORT_QUALIFICATION"
_REMOTE_REF_FIELD_COUNT = 2
_IMPLEMENTATION_FILES = (
    "scripts/run_staged_generalization_v11_exposed_run2.py",
    "scripts/validation/provider_receipt_boundary/foreground/__init__.py",
    "scripts/validation/provider_receipt_boundary/foreground/contracts.py",
    "scripts/validation/provider_receipt_boundary/foreground/execution.py",
    "scripts/validation/provider_receipt_boundary/foreground/validation.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v11_run2/"
    "qualification.py",
)


class QualificationError(RuntimeError):
    """Foreground qualification cannot violate its one-call contract."""


def qualification_input() -> str:
    return (
        "This is a transport-only synthetic schema qualification. "
        "It is not scientific evidence and must not receive scientific credit.\n\n"
        "Source sentence: Transport qualification sentence.\n\n"
        "Return case_id `transport-qualification`. Inventory exactly one "
        "OBSERVATION event grounded to the complete source sentence, with trigger "
        "text `qualification`. Return no participants. Return one link entry for "
        "that event with no arguments. Use direction OBSERVED, comparison "
        "NOT_APPLICABLE, polarity AFFIRMED, uncertainty ASSERTED, one NONE "
        "statistical observation, author interpretation NOT_CLAIMED, and the "
        "complete source sentence as semantic evidence. Select that event as the "
        "root, mark the graph COMPLETE, and provide short explanations."
    )


def build_qualification_preregistration() -> dict[str, object]:
    value = qualification_input()
    return {
        "schema_version": (
            "artana.staged_generalization.v11_foreground_qualification.v3"
        ),
        "experiment_id": QUALIFICATION_ID,
        "authorization": "TRANSPORT_ONLY_SYNTHETIC_NO_SCIENTIFIC_CREDIT",
        "provider": {
            "model": f"openai:{MODEL}",
            "reasoning_effort": REASONING_EFFORT,
            "transport": "DIRECT_OPENAI_FOREGROUND_RESPONSES",
            "background": False,
            "store": True,
            "request_timeout_seconds": QUALIFICATION_TIMEOUT_SECONDS,
            "provider_retries": 0,
            "fallback": False,
            "application_max_output_tokens": None,
            "application_max_total_tokens": None,
        },
        "input_sha256": hashlib.sha256(value.encode()).hexdigest(),
        "schema_sha256": _canonical_sha256(
            V9StagedGeneralizationOutput.model_json_schema()
        ),
        "provider_format_sha256": _canonical_sha256(provider_format()),
        "implementation_sha256": {
            name: _sha256(REPO / name) for name in _IMPLEMENTATION_FILES
        },
        "acceptance": {
            "one_creation_call": True,
            "one_response_id": True,
            "one_confirmation_retrieval": True,
            "one_input_item_retrieval": True,
            "complete_usage": True,
            "confirmation_usage_is_authoritative": True,
            "creation_usage_snapshot_may_differ": True,
            "opaque_reasoning_transport_may_be_omitted_on_confirmation": True,
            "scientific_payload_and_identity_must_remain_exact": True,
            "strict_v11_schema": True,
            "provider_retries": 0,
            "duplicate_creation_calls": 0,
            "fallback": False,
            "hidden_token_ceiling": False,
            "scientific_credit": False,
        },
    }


def write_qualification_preregistration(
    paths: V11Run2Paths = DEFAULT_PATHS,
) -> None:
    write_json_atomic(
        paths.qualification.preregistration,
        build_qualification_preregistration(),
    )


def verify_qualification_preregistration(
    paths: V11Run2Paths = DEFAULT_PATHS,
    *,
    remote_gate: bool = False,
) -> dict[str, object]:
    loaded = _object(
        json.loads(
            paths.qualification.preregistration.read_text(encoding="utf-8")
        )
    )
    if loaded != build_qualification_preregistration():
        raise QualificationError(
            "foreground qualification preregistration changed"
        )
    if remote_gate:
        _verify_remote_head()
    return loaded


def execute_qualification(
    paths: V11Run2Paths = DEFAULT_PATHS,
    *,
    remote_gate: bool = True,
    runtime: ForegroundExecutionRuntime | None = None,
) -> str:
    """Execute one synthetic creation and persist custody before returning."""

    outputs = (
        paths.qualification.attempt,
        paths.qualification.bundle,
        paths.qualification.receipt,
        paths.qualification.raw_output,
        paths.qualification.result,
    )
    if any(path.exists() for path in outputs):
        raise QualificationError("foreground qualification already started")
    preregistration = verify_qualification_preregistration(
        paths,
        remote_gate=remote_gate,
    )
    del preregistration
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise QualificationError("OPENAI_API_KEY is absent")
    preregistration_sha256 = _sha256(paths.qualification.preregistration)
    value = qualification_input()
    reserve_attempt(
        paths.qualification.attempt,
        stage=f"TRANSPORT_QUALIFICATION:{QUALIFICATION_ID}",
        provider_input=value,
        preregistration_sha256=preregistration_sha256,
    )
    request = TelemetryProviderRequestV2(
        provider_input=value,
        provider_format=provider_format(),
        provider_model_id=MODEL,
        reasoning_effort=REASONING_EFFORT,
        pricing={"input": 0.000001, "cached_input": 0.0000001, "output": 0.000006},
        metadata={
            "artana_experiment": QUALIFICATION_ID,
            "artana_scientific_change": "TRANSPORT_ONLY",
            "artana_qualification_credit": "NONE",
        },
    )
    active = runtime or ForegroundExecutionRuntime(
        on_completed=lambda response_id: acknowledge_attempt(
            paths.qualification.attempt,
            response_id=response_id,
        )
    )
    try:
        execution = execute_foreground_provider_call_telemetry_v2(
            api_key=api_key,
            request=request,
            request_timeout_seconds=QUALIFICATION_TIMEOUT_SECONDS,
            output_model=V9StagedGeneralizationOutput,
            runtime=active,
        )
    except ProviderExecutionError as exc:
        write_json_atomic(
            paths.qualification.result,
            {
                "schema_version": (
                    "artana.staged_generalization."
                    "v11_foreground_qualification_result.v3"
                ),
                "experiment_id": QUALIFICATION_ID,
                "decision": QUALIFICATION_INVALID,
                "failure_stage": exc.stage,
                "root_cause": exc.root_cause,
                "diagnostics": exc.diagnostics,
                "scientific_credit": False,
                "graph_writes": 0,
            },
        )
        return QUALIFICATION_INVALID
    response_id = _receipt_response_id(execution.receipt)
    attempt = _object(
        json.loads(paths.qualification.attempt.read_text(encoding="utf-8"))
    )
    if (
        attempt.get("state") != "ACKNOWLEDGED"
        or attempt.get("response_id") != response_id
    ):
        write_json_atomic(
            paths.qualification.result,
            {
                "schema_version": (
                    "artana.staged_generalization."
                    "v11_foreground_qualification_result.v3"
                ),
                "experiment_id": QUALIFICATION_ID,
                "decision": QUALIFICATION_INVALID,
                "failure_stage": "QUALIFICATION_RESPONSE_ID_CUSTODY",
                "root_cause": "attempt response ID is absent or differs",
                "scientific_credit": False,
                "graph_writes": 0,
            },
        )
        return QUALIFICATION_INVALID
    persist_stage_custody(
        custody_input=StageCustodyInput(
            paths=StageCustodyPaths(
                bundle=paths.qualification.bundle,
                receipt=paths.qualification.receipt,
                raw_output=paths.qualification.raw_output,
            ),
            stage=f"TRANSPORT_QUALIFICATION:{QUALIFICATION_ID}",
            provider_input=value,
            schema_sha256=_canonical_sha256(
                V9StagedGeneralizationOutput.model_json_schema()
            ),
        ),
        output=execution.extraction,
        canonical_payload=execution.canonical_payload,
        receipt=execution.receipt,
    )
    identity = _object(execution.receipt["identity"])
    usage = _object(execution.receipt["usage"])
    usage_policy = _object(execution.receipt["foreground_usage_policy"])
    passed = (
        execution.extraction.case_id == "transport-qualification"
        and execution.creation_response.get("background") is False
        and execution.confirmation_response.get("background") is False
        and execution.receipt.get("provider_creation_calls") == 1
        and execution.receipt.get("provider_retries") == 0
        and execution.receipt.get("duplicate_creation_calls") == 0
        and execution.receipt.get("confirmation_retrieval_requests") == 1
        and execution.receipt.get("input_item_retrieval_requests") == 1
        and usage_policy.get("authoritative_snapshot")
        == "CONFIRMATION_RETRIEVAL"
        and usage_policy.get("scientific_validity_dependency") is False
    )
    result = {
        "schema_version": (
            "artana.staged_generalization.v11_foreground_qualification_result.v3"
        ),
        "experiment_id": QUALIFICATION_ID,
        "decision": QUALIFICATION_PASS if passed else QUALIFICATION_INVALID,
        "transport": execution.receipt["transport"],
        "model": identity["model"],
        "reasoning_effort": REASONING_EFFORT,
        "response_id": identity["response_id"],
        "usage": usage,
        "foreground_usage_policy": usage_policy,
        "provider_creation_calls": execution.receipt["provider_creation_calls"],
        "provider_retries": execution.receipt["provider_retries"],
        "duplicate_creation_calls": execution.receipt[
            "duplicate_creation_calls"
        ],
        "confirmation_retrieval_requests": execution.receipt[
            "confirmation_retrieval_requests"
        ],
        "input_item_retrieval_requests": execution.receipt[
            "input_item_retrieval_requests"
        ],
        "application_max_output_tokens": None,
        "application_max_total_tokens": None,
        "scientific_credit": False,
        "graph_writes": 0,
    }
    write_json_atomic(paths.qualification.result, result)
    return cast("str", result["decision"])


def _verify_remote_head() -> None:
    branch = _git("branch", "--show-current")
    local = _git("rev-parse", "HEAD")
    remote = _git("ls-remote", "--heads", "origin", branch).split()
    if (
        not branch
        or len(remote) != _REMOTE_REF_FIELD_COUNT
        or remote[0] != local
    ):
        raise QualificationError(
            "local and remote heads differ before transport qualification"
        )


def _git(*arguments: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed local Git executable.
        ["git", *arguments],  # noqa: S607
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise QualificationError(completed.stderr.strip())
    return completed.stdout.strip()


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise QualificationError("expected JSON object")
    return value


def _receipt_response_id(receipt: dict[str, object]) -> str:
    identity = receipt.get("identity")
    if not isinstance(identity, dict):
        raise QualificationError("qualification receipt identity is absent")
    response_id = identity.get("response_id")
    if not isinstance(response_id, str) or not response_id:
        raise QualificationError("qualification response ID is absent")
    return response_id


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "QUALIFICATION_INVALID",
    "QUALIFICATION_PASS",
    "QualificationError",
    "build_qualification_preregistration",
    "execute_qualification",
    "qualification_input",
    "verify_qualification_preregistration",
    "write_qualification_preregistration",
]
