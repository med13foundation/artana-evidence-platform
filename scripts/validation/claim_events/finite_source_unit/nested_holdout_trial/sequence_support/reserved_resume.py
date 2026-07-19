"""Identity validation for resuming an unconsumed repeat reservation."""

from __future__ import annotations

from collections.abc import Callable

from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.repeat_sequence import (
    AuthorizationT,
    RepeatAuthorizationValues,
    RepeatReservationRequest,
    RepeatSequenceDefinition,
    RepeatSequenceRuntime,
    _execution_lease_path,
    _read_json,
    _registry_root,
    _reservation_has_frozen_identity,
)


def resume_reserved_repeat(
    *,
    definition: RepeatSequenceDefinition,
    runtime: RepeatSequenceRuntime,
    authorization_factory: Callable[[RepeatAuthorizationValues], AuthorizationT],
    request: RepeatReservationRequest,
) -> AuthorizationT:
    """Recreate authorization for an untouched, identity-matched reservation."""

    if not request.run_id.strip():
        raise ValueError(f"{definition.label} run_id must be nonempty")
    if request.repeat_index not in definition.repeat_indices:
        raise ValueError(f"{definition.label} repeat index is not pre-registered")
    output = request.output.resolve()
    if output.exists():
        raise FileExistsError(f"{definition.label} output already exists: {output}")
    reservation_path = (
        _registry_root(
            request.repository_root,
            definition=definition,
            git_runner=runtime.git_runner,
        )
        / f"repeat-{request.repeat_index}.json"
    )
    reservation = _read_json(reservation_path, definition=definition)
    repository_root = request.repository_root.resolve()
    repository_evidence = runtime.collect_repository_evidence(repository_root)
    stored_repository_evidence = reservation.get("repository_evidence")
    token = reservation.get("token")
    if (
        reservation.get("schema_version") != definition.reservation_schema_version
        or reservation.get("status") != "RESERVED"
        or reservation.get("run_id") != request.run_id
        or reservation.get("repeat_index") != request.repeat_index
        or reservation.get("output") != str(output)
        or reservation.get("selection_seed") != definition.selection_seed
        or reservation.get("projection_set_sha256")
        != definition.projection_set_sha256
        or reservation.get("unit_id") != definition.unit_id
        or not _reservation_has_frozen_identity(reservation, definition=definition)
        or not isinstance(stored_repository_evidence, dict)
        or stored_repository_evidence != repository_evidence
        or repository_evidence.get("clean") is not True
        or not isinstance(token, str)
        or not token
        or reservation.get("execution_lease_sha256") is not None
        or _execution_lease_path(reservation_path).exists()
    ):
        raise RuntimeError(f"{definition.label} reserved repeat cannot be resumed")
    authorization = authorization_factory(
        RepeatAuthorizationValues(
            run_id=request.run_id,
            repeat_index=request.repeat_index,
            output=output,
            reservation_path=reservation_path,
            token=token,
            repository_root=repository_root,
            repository_evidence=stored_repository_evidence,
        ),
    )
    authorization.require_active()
    authorization.require_repository_unchanged()
    return authorization


__all__ = ["resume_reserved_repeat"]
