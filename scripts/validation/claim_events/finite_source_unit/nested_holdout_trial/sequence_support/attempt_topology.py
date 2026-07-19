"""Version-supplied attempt topology helpers for repeat custody."""

from __future__ import annotations

from collections.abc import Sequence

_DEFAULT_ROLES = (
    ("primary", "primary", "extraction"),
    ("weak_review", "weak_review", "verification"),
)
_DEFAULT_EXECUTION_PATH = "agent_only_source_unit"


def allowed_role_pairs(
    required_roles: Sequence[tuple[str, str, str]],
    *,
    allow_schema_retry: bool,
) -> set[tuple[str, str]]:
    """Return accepted attempt/pass pairs for one sequence version."""

    pairs = {(attempt_role, pass_role) for attempt_role, pass_role, _ in required_roles}
    if allow_schema_retry:
        pairs.add(("schema_retry", "primary"))
    return pairs


def attempt_role_count(attempts: Sequence[object], role: str) -> int:
    """Count audited attempts with one exact categorical role."""

    return sum(
        isinstance(attempt, dict) and attempt.get("attempt_role") == role
        for attempt in attempts
    )


def receipt_matches_attempt(
    *,
    receipt: dict[object, object],
    attempt: dict[object, object],
    unit_id: str,
    receipt_model_id: str,
) -> bool:
    """Require provider receipt identity to match its audited attempt."""

    return (
        receipt.get("expected_case_id") == unit_id
        and receipt.get("expected_model_id") == receipt_model_id
        and receipt.get("expected_output_sha256")
        == attempt.get("provider_output_sha256")
        and receipt.get("expected_payload_sha256") == attempt.get("payload_sha256")
        and receipt.get("expected_prompt_sha256") == attempt.get("prompt_sha256")
        and receipt.get("expected_invocation_id") == attempt.get("invocation_id")
        and receipt.get("expected_kernel_run_id") == attempt.get("kernel_run_id")
        and receipt.get("expected_source_sha256") == attempt.get("source_sha256")
        and receipt.get("expected_input_sha256") == attempt.get("input_sha256")
        and receipt.get("expected_evidence_unit_sha256")
        == attempt.get("evidence_unit_sha256")
    )


def non_default_topology_evidence(
    *,
    required_roles: tuple[tuple[str, str, str], ...],
    allow_schema_retry: bool,
    execution_path: str,
) -> dict[str, object] | None:
    """Freeze topology only when a version differs from historical defaults."""

    if (
        required_roles == _DEFAULT_ROLES
        and allow_schema_retry
        and execution_path == _DEFAULT_EXECUTION_PATH
    ):
        return None
    return {
        "required_roles": [list(role) for role in required_roles],
        "allow_schema_retry": allow_schema_retry,
        "execution_path": execution_path,
    }


__all__ = [
    "allowed_role_pairs",
    "attempt_role_count",
    "non_default_topology_evidence",
    "receipt_matches_attempt",
]
