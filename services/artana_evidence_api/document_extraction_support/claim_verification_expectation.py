"""When claim verification is required, and what its absence means.

Two independent gates -- the candidate trust ladder and canonical promotion --
ask the same question: does this candidate need claim-verification lineage, and
does it have it?  They previously answered it with the same eight lines of
duplicated logic, which is how they came to share the same defect.

That logic treated *absent* markers as a pass.  A candidate carrying no
verification metadata scored `verified_evidence`, while one that attempted
verification and fell short was demoted to `agent_candidate`.  Skipping the
check scored strictly better than attempting it -- exactly the inversion
invariant 8 ("missing is not equal") exists to prevent.

The shim was reasonable while the verification loop was dark: pre-existing
candidates carry no markers and demoting all of them at once would have been a
false signal.  It stops being reasonable the moment the loop runs, because then
absence means the loop declined to verify.  So expectation is tied to whether
the loop is actually enabled rather than to whether the candidate happens to
carry the fields it would have written.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

#: Metadata keys written by the claim verification loop.
CLAIM_VERIFICATION_MARKER_FIELDS: tuple[str, ...] = (
    "claim_verification",
    "claim_verification_terminal",
    "claim_verification_lineage_status",
    "claim_verification_qualification_complete",
)
_EXPERIMENT_FLAG = "ARTANA_CLAIM_VERIFICATION_EXPERIMENT"


def claim_verification_loop_enabled() -> bool:
    """Return whether the claim verification loop is running for this process.

    Reads the same switch `ClaimVerificationRuntimeConfig.from_environment`
    uses, so the floors cannot expect verification the pipeline is not
    performing, nor excuse its absence once it is.
    """

    raw = os.getenv(_EXPERIMENT_FLAG)
    if raw is None:
        return False
    normalized = raw.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    message = f"{_EXPERIMENT_FLAG} must be an explicit boolean value"
    raise ValueError(message)


def claim_verification_is_required(metadata: Mapping[str, object]) -> bool:
    """Return whether this candidate must carry claim-verification lineage.

    Required when the loop is enabled -- absence then means the loop declined
    to verify, which is a finding rather than a non-event -- or when the
    candidate carries any marker, since a partial envelope must never pass.
    """

    if claim_verification_loop_enabled():
        return True
    return any(field in metadata for field in CLAIM_VERIFICATION_MARKER_FIELDS)


__all__ = [
    "CLAIM_VERIFICATION_MARKER_FIELDS",
    "claim_verification_is_required",
    "claim_verification_loop_enabled",
]
