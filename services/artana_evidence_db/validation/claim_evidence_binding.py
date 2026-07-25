"""Whether a claim's evidence can be followed back to a source.

Two different questions were being answered by one predicate.

*Is this claim well-formed?* is permissive by design -- a free-text summary is
enough for a workflow to plan around, and raising that bar turns well-formed
claims into blocking failures.

*May this be written to the graph?* is stricter. A summary describes evidence;
it does not anchor the claim to anything a reader could check. Reporting
PERSISTABLE on that basis promises a write the graph should not accept.

`has_evidence` answers the first, `has_bound_evidence` the second, and
`has_bound_evidence` is strictly stronger -- a request can never be persistable
while failing the validity gate. See ART-VAL-006 / #201.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_db.validation.source_evidence_write_validation import (
    SourceEvidenceWriteValidationService,
)

if TYPE_CHECKING:
    from artana_evidence_db.graph_api_schemas.kernel_relation_schemas import (
        KernelRelationClaimCreateRequest,
        KernelRelationTripleValidationRequest,
    )
    from artana_evidence_db.kernel_domain_models import KernelEntity
    from artana_evidence_db.validation.source_evidence_write_validation import (
        SourceEvidenceWriteValidationIssue,
    )

_SOURCE_EVIDENCE_WRITE_VALIDATION = SourceEvidenceWriteValidationService()


def _normalized(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def has_evidence(request: KernelRelationTripleValidationRequest) -> bool:
    """Return whether anything at all was attached as evidence.

    Gates *validity*, not persistability. Deliberately permissive: one non-empty
    field is enough for the claim to be well-formed.
    """

    return any(
        (
            request.evidence_summary,
            request.evidence_sentence,
            request.source_document_id,
            request.source_evidence,
            request.source_document_ref,
        ),
    )


def has_bound_evidence(request: KernelRelationTripleValidationRequest) -> bool:
    """Return whether the evidence is tied to an identifiable source.

    Requires a typed `source_evidence` handoff or an identified source document.
    Whitespace is not a source, so a blank reference does not bind.
    """

    return any(
        (
            request.source_evidence,
            request.source_document_id,
            _normalized(request.source_document_ref),
        ),
    )


def entity_names(entity: KernelEntity) -> tuple[str, ...]:
    """Return an entity's label and aliases, matching the write path exactly.

    `routers/claims.py` builds the same tuple before calling the source-evidence
    gate. Both call sites must agree, or the advisory verdict and the write
    verdict can diverge on alias matching alone.
    """

    aliases = getattr(entity, "aliases", None) or ()
    return tuple(
        name
        for name in [getattr(entity, "display_label", None), *aliases]
        if isinstance(name, str) and name.strip() != ""
    )


def source_evidence_binding_issue(
    *,
    request: KernelRelationClaimCreateRequest,
    source_entity: KernelEntity,
    target_entity: KernelEntity,
) -> SourceEvidenceWriteValidationIssue | None:
    """Run the write path's source-evidence gate for the advisory verdict.

    `routers/claims.py` runs this on every claim write and it is not
    authorship-gated -- it skips only when `source_evidence` is absent. The
    advisory endpoint had no counterpart, so a MANUAL claim whose quote was
    detached from its endpoints was rejected by `/claims` and reported
    PERSISTABLE by `/validate/claim`. The two paths must not disagree about the
    same payload.
    """

    return _SOURCE_EVIDENCE_WRITE_VALIDATION.validate(
        request,
        subject_names=entity_names(source_entity),
        object_names=entity_names(target_entity),
    )


__all__ = [
    "entity_names",
    "has_bound_evidence",
    "has_evidence",
    "source_evidence_binding_issue",
]
