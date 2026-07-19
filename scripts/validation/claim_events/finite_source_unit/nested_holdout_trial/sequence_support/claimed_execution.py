"""Read-only provider identity reconstruction for a consumed execution lease."""

from __future__ import annotations

from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.repeat_sequence import (
    RepeatAuthorization,
    RepeatSequenceDefinition,
    _execution_lease_for_finalization,
    _provider_evidence_unit_id,
    _ProviderReservationIdentity,
)


def claimed_provider_evidence_unit_id(
    authorization: RepeatAuthorization,
    *,
    definition: RepeatSequenceDefinition,
) -> str:
    """Rebuild provider identity from an already consumed, validated lease."""

    authorization.require_active()
    authorization.require_repository_unchanged()
    execution_lease_sha256 = _execution_lease_for_finalization(
        authorization,
        definition=definition,
    )
    return _provider_evidence_unit_id(
        definition=definition,
        identity=_ProviderReservationIdentity(
            run_id=authorization.run_id,
            repeat_index=authorization.repeat_index,
            output=str(authorization.output),
            token=authorization.token,
            repository_evidence=authorization.repository_evidence,
            execution_lease_sha256=execution_lease_sha256,
        ),
    )


__all__ = ["claimed_provider_evidence_unit_id"]
