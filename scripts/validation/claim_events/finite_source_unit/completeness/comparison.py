"""Deterministic paired metrics for a preregistered completeness experiment."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimArgumentRole,
    ClaimEventRole,
    InventoryAssertionScope,
)

from scripts.validation.claim_events.finite_source_unit.contracts import (
    EntailmentDecision,
    EventStructureDecision,
    SemanticValidityDecision,
    SourceUnitCoverageDecision,
    SourceUnitVerificationOutput,
)
from scripts.validation.claim_events.finite_source_unit.normalization.review import (
    LocalReviewDisposition,
    SourceUnitNormalizedReviewResult,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.claim_frames import (
        BoundClaimInventoryItem,
        BoundControlledEventLink,
        ClaimEventType,
    )

    from scripts.validation.claim_events.finite_source_unit.completeness.service import (
        SourceUnitCompletenessResult,
    )
    from scripts.validation.claim_events.finite_source_unit.normalization.service import (
        SourceUnitNormalizationResult,
    )
    from scripts.validation.claim_events.finite_source_unit.service import (
        VerifiedEventCandidate,
    )


class PairedCompletenessDecision(StrEnum):
    """Deterministic stop or continue result for one visible comparison."""

    SCIENTIFIC_IMPROVEMENT = "SCIENTIFIC_IMPROVEMENT"
    NO_PAIRED_IMPROVEMENT = "NO_PAIRED_IMPROVEMENT"
    REVIEW_ONLY_DISCOVERY = "REVIEW_ONLY_DISCOVERY"
    STOP_AND_RECALIBRATE = "STOP_AND_RECALIBRATE"


@dataclass(frozen=True, slots=True)
class ControlledEventObligation:
    """A preregistered source structure, not an inferred benchmark match."""

    obligation_id: str
    target_event_type: ClaimEventType
    target_participant_span: str
    target_cue_span: str
    target_destination_span: str
    controller_event_type: ClaimEventType
    controller_cause_span: str
    controller_cue_fragment: str


@dataclass(frozen=True, slots=True)
class PairedCompletenessResult:
    """Counts and identities calculated only from categorical outputs."""

    decision: PairedCompletenessDecision
    a_covered_obligations: tuple[str, ...]
    c_covered_obligations: tuple[str, ...]
    a_plus_c_covered_obligations: tuple[str, ...]
    recovered_obligations: tuple[str, ...]
    preserved_obligations: tuple[str, ...]
    regressed_obligations: tuple[str, ...]
    c_only_entailed_event_count: int
    c_only_review_event_count: int
    c_rejected_or_unresolved_event_count: int


@dataclass(frozen=True, slots=True)
class VerifiedCompletenessArm:
    """C inventory and its independent ordered source verification."""

    completeness: SourceUnitCompletenessResult
    verification_output: SourceUnitVerificationOutput
    verified_events: tuple[VerifiedEventCandidate, ...]

    def __post_init__(self) -> None:
        if (
            self.verification_output.eligibility_category
            is not self.completeness.output.eligibility_category
        ):
            raise ValueError("C verification changed the source eligibility category")
        if tuple(item.claim for item in self.verified_events) != self.completeness.accepted:
            raise ValueError("C verification must cover the completeness inventory exactly")
        if len(self.verification_output.decisions) != len(self.verified_events):
            raise ValueError("C verification output must cover every inventory item")
        if tuple(item.verification for item in self.verified_events) != (
            self.verification_output.decisions
        ):
            raise ValueError("C verified decisions must match the categorical output")


@dataclass(frozen=True, slots=True)
class _Coverage:
    obligation_ids: frozenset[str]
    contributing_inventory_ids: frozenset[str]


def compare_completeness_arms(
    *,
    a_normalization: SourceUnitNormalizationResult,
    a_review: SourceUnitNormalizedReviewResult,
    c_arm: VerifiedCompletenessArm,
    obligations: tuple[ControlledEventObligation, ...],
) -> PairedCompletenessResult:
    """Compare A and B without assigning any new biomedical category."""

    _require_comparison_lineage(
        a_normalization=a_normalization,
        a_review=a_review,
    )
    a_entailed_ids = frozenset(
        candidate.inventory_id
        for candidate, review in zip(
            a_normalization.accepted,
            a_review.output.candidate_reviews,
            strict=True,
        )
        if review.source_entailment is EntailmentDecision.ENTAILED
    )
    c_entailed_ids = frozenset(
        item.claim.inventory_id
        for item in c_arm.verified_events
        if _is_complete_entailed(item)
    )
    a_coverage = _covered_obligations(
        inventory=a_normalization.accepted,
        links=a_normalization.controlled_event_links,
        eligible_inventory_ids=a_entailed_ids,
        obligations=obligations,
    )
    c_coverage = _covered_obligations(
        inventory=c_arm.completeness.accepted,
        links=c_arm.completeness.controlled_event_links,
        eligible_inventory_ids=c_entailed_ids,
        obligations=obligations,
    )

    union_coverage = a_coverage.obligation_ids | c_coverage.obligation_ids
    recovered = c_coverage.obligation_ids - a_coverage.obligation_ids
    preserved = frozenset(a_coverage.obligation_ids)
    regressed: frozenset[str] = frozenset()
    a_semantics = {_scientific_identity(item) for item in a_normalization.accepted}
    c_only = tuple(
        item
        for item in c_arm.verified_events
        if _scientific_identity(item.claim) not in a_semantics
    )
    c_only_entailed = tuple(
        item
        for item in c_only
        if _is_complete_entailed(item)
        and item.claim.inventory_id not in c_coverage.contributing_inventory_ids
    )
    c_only_review = tuple(
        item
        for item in c_only
        if item.verification.decision is EntailmentDecision.ENTAILED
        and not _is_complete_entailed(item)
    )
    rejected_or_unresolved = tuple(
        item
        for item in c_arm.verified_events
        if item.verification.decision is not EntailmentDecision.ENTAILED
        or item.verification.structure_decision
        in {EventStructureDecision.INVALID, EventStructureDecision.ABSTAIN}
        or item.verification.event_type_decision
        in {SemanticValidityDecision.INVALID, SemanticValidityDecision.ABSTAIN}
        or any(
            argument.type_decision
            in {SemanticValidityDecision.INVALID, SemanticValidityDecision.ABSTAIN}
            or argument.event_role_decision
            in {SemanticValidityDecision.INVALID, SemanticValidityDecision.ABSTAIN}
            for argument in item.verification.argument_semantic_decisions
        )
    )

    if (
        a_review.local_review_disposition is not LocalReviewDisposition.PASS
        or c_arm.verification_output.coverage_decision
        is not SourceUnitCoverageDecision.CANDIDATES_COMPLETE
        or rejected_or_unresolved
    ):
        decision = PairedCompletenessDecision.STOP_AND_RECALIBRATE
    elif c_only_entailed or c_only_review:
        decision = PairedCompletenessDecision.REVIEW_ONLY_DISCOVERY
    elif recovered:
        decision = PairedCompletenessDecision.SCIENTIFIC_IMPROVEMENT
    else:
        decision = PairedCompletenessDecision.NO_PAIRED_IMPROVEMENT

    return PairedCompletenessResult(
        decision=decision,
        a_covered_obligations=tuple(sorted(a_coverage.obligation_ids)),
        c_covered_obligations=tuple(sorted(c_coverage.obligation_ids)),
        a_plus_c_covered_obligations=tuple(sorted(union_coverage)),
        recovered_obligations=tuple(sorted(recovered)),
        preserved_obligations=tuple(sorted(preserved)),
        regressed_obligations=tuple(sorted(regressed)),
        c_only_entailed_event_count=len(c_only_entailed),
        c_only_review_event_count=len(c_only_review),
        c_rejected_or_unresolved_event_count=len(rejected_or_unresolved),
    )


def _require_comparison_lineage(
    *,
    a_normalization: SourceUnitNormalizationResult,
    a_review: SourceUnitNormalizedReviewResult,
) -> None:
    if a_review.normalization_envelope_sha256 != a_normalization.envelope_sha256:
        raise ValueError("A review is not bound to the supplied normalization")


def _is_complete_entailed(item: VerifiedEventCandidate) -> bool:
    verification = item.verification
    return (
        verification.decision is EntailmentDecision.ENTAILED
        and verification.structure_decision is EventStructureDecision.COMPLETE
        and verification.event_type_decision is SemanticValidityDecision.VALID
        and all(
            argument.type_decision is SemanticValidityDecision.VALID
            and argument.event_role_decision is SemanticValidityDecision.VALID
            for argument in verification.argument_semantic_decisions
        )
    )


def _covered_obligations(
    *,
    inventory: tuple[BoundClaimInventoryItem, ...],
    links: tuple[BoundControlledEventLink, ...],
    eligible_inventory_ids: frozenset[str],
    obligations: tuple[ControlledEventObligation, ...],
) -> _Coverage:
    inventory_by_id = {item.inventory_id: item for item in inventory}
    covered: set[str] = set()
    contributors: set[str] = set()
    for obligation in obligations:
        for link in links:
            controller = inventory_by_id[link.controller_inventory_id]
            target = inventory_by_id[link.controlled_inventory_id]
            if not {
                controller.inventory_id,
                target.inventory_id,
            }.issubset(eligible_inventory_ids):
                continue
            if not _matches_obligation(
                controller=controller,
                target=target,
                obligation=obligation,
            ):
                continue
            covered.add(obligation.obligation_id)
            contributors.update((controller.inventory_id, target.inventory_id))
            break
    return _Coverage(
        obligation_ids=frozenset(covered),
        contributing_inventory_ids=frozenset(contributors),
    )


def _matches_obligation(
    *,
    controller: BoundClaimInventoryItem,
    target: BoundClaimInventoryItem,
    obligation: ControlledEventObligation,
) -> bool:
    return (
        target.item.event_type is obligation.target_event_type
        and target.item.assertion_scope
        is InventoryAssertionScope.CONTROLLED_TARGET
        and target.item.relation_cue_span == obligation.target_cue_span
        and any(
            argument.argument.role is ClaimArgumentRole.GENE_OR_PROTEIN
            and argument.argument.event_role is ClaimEventRole.THEME
            and argument.argument.exact_span == obligation.target_participant_span
            for argument in target.bound_arguments
        )
        and any(
            argument.argument.event_role is ClaimEventRole.TOLOC
            and argument.argument.exact_span == obligation.target_destination_span
            for argument in target.bound_arguments
        )
        and controller.item.event_type is obligation.controller_event_type
        and controller.item.assertion_scope
        is InventoryAssertionScope.SOURCE_ASSERTED
        and obligation.controller_cue_fragment
        in controller.item.relation_cue_span.casefold()
        and any(
            argument.argument.event_role is ClaimEventRole.CAUSE
            and argument.argument.exact_span == obligation.controller_cause_span
            for argument in controller.bound_arguments
        )
    )


def _scientific_identity(item: BoundClaimInventoryItem) -> tuple[object, ...]:
    claim = item.item
    return (
        claim.exact_span,
        claim.relation_cue_span,
        claim.claim_kind,
        claim.event_type,
        claim.assertion_scope,
        claim.polarity,
        claim.epistemic_status,
        tuple(
            (
                argument.role,
                argument.event_role,
                argument.exact_span,
                argument.controlled_event_ref is not None,
            )
            for argument in claim.arguments
        ),
    )


__all__ = [
    "ControlledEventObligation",
    "PairedCompletenessDecision",
    "PairedCompletenessResult",
    "VerifiedCompletenessArm",
    "compare_completeness_arms",
]
