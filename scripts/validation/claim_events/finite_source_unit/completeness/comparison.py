"""Deterministic paired metrics for a preregistered completeness experiment."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimArgumentRole,
    ClaimEventRole,
    ClaimKind,
    InventoryAssertionScope,
    InventoryEpistemicStatus,
    InventoryPolarity,
)

from scripts.validation.claim_events.finite_source_unit.contracts import (
    EntailmentDecision,
    ProjectionEligibilityDecision,
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
    target_allowed_participant_spans: tuple[str, ...]
    target_cue_span: str
    target_destination_span: str
    controller_event_type: ClaimEventType
    controller_cause_span: str
    controller_cue_span: str


@dataclass(frozen=True, slots=True)
class ArgumentObligation:
    """One exact typed argument allowed in a frozen scientific event."""

    role: ClaimArgumentRole
    event_role: ClaimEventRole
    exact_span: str
    controlled_event_ref: bool = False


@dataclass(frozen=True, slots=True)
class DiagnosticClauseObligation:
    """A source-explicit clause required to prevent a narrow metric win."""

    obligation_id: str
    event_type: ClaimEventType
    cue_span: str
    polarity: InventoryPolarity
    exact_arguments: tuple[ArgumentObligation, ...]
    controlled_target_event_type: ClaimEventType | None = None
    controlled_target_cue_span: str | None = None
    controlled_target_exact_arguments: tuple[ArgumentObligation, ...] = ()


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
    covered_diagnostics: tuple[str, ...]
    missing_diagnostics: tuple[str, ...]
    metric_improved: bool
    whole_source_complete: bool
    ready_for_confirmatory_run: bool
    a_c_conflict_count: int
    c_only_entailed_event_count: int
    c_only_review_event_count: int
    c_rejected_or_unresolved_event_count: int

    def as_json(self) -> dict[str, object]:
        """Serialize every deterministic scientific result field."""

        return {
            "decision": self.decision.value,
            "a_covered_obligations": self.a_covered_obligations,
            "c_covered_obligations": self.c_covered_obligations,
            "a_plus_c_covered_obligations": self.a_plus_c_covered_obligations,
            "recovered_obligations": self.recovered_obligations,
            "preserved_obligations": self.preserved_obligations,
            "regressed_obligations": self.regressed_obligations,
            "covered_diagnostics": self.covered_diagnostics,
            "missing_diagnostics": self.missing_diagnostics,
            "metric_improved": self.metric_improved,
            "whole_source_complete": self.whole_source_complete,
            "ready_for_confirmatory_run": self.ready_for_confirmatory_run,
            "a_c_conflict_count": self.a_c_conflict_count,
            "c_only_entailed_event_count": self.c_only_entailed_event_count,
            "c_only_review_event_count": self.c_only_review_event_count,
            "c_rejected_or_unresolved_event_count": (
                self.c_rejected_or_unresolved_event_count
            ),
        }


@dataclass(frozen=True, slots=True)
class VerifiedCompletenessArm:
    """C inventory and its independent ordered source verification."""

    completeness: SourceUnitCompletenessResult
    verification_output: SourceUnitVerificationOutput
    verified_events: tuple[VerifiedEventCandidate, ...]

    def __post_init__(self) -> None:
        if self.completeness.output.context_dimensions:
            raise ValueError(
                "the frozen completeness experiment does not verify context dimensions"
            )
        if (
            self.verification_output.eligibility_category
            is not self.completeness.output.eligibility_category
        ):
            raise ValueError("C verification changed the source eligibility category")
        if (
            tuple(item.claim for item in self.verified_events)
            != self.completeness.accepted
        ):
            raise ValueError(
                "C verification must cover the completeness inventory exactly"
            )
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
    diagnostics: tuple[DiagnosticClauseObligation, ...],
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
    diagnostic_coverage = _covered_diagnostics(
        inventory=c_arm.completeness.accepted,
        links=c_arm.completeness.controlled_event_links,
        eligible_inventory_ids=c_entailed_ids,
        obligations=diagnostics,
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
    a_by_axis = {
        _scientific_axis_identity(item): item
        for item in a_normalization.accepted
        if item.inventory_id in a_entailed_ids
    }
    a_c_conflicts = tuple(
        item
        for item in c_arm.verified_events
        if _is_complete_entailed(item)
        and (a_item := a_by_axis.get(_scientific_axis_identity(item.claim))) is not None
        and (
            a_item.item.polarity is not item.claim.item.polarity
            or a_item.item.epistemic_status is not item.claim.item.epistemic_status
        )
    )
    c_only_entailed = tuple(
        item
        for item in c_only
        if _is_complete_entailed(item)
        and item.claim.inventory_id not in c_coverage.contributing_inventory_ids
        and item.claim.inventory_id
        not in diagnostic_coverage.contributing_inventory_ids
    )
    c_only_review = tuple(
        item
        for item in c_only
        if item.verification.decision is EntailmentDecision.ENTAILED
        and not _is_complete_entailed(item)
    )
    rejected_or_unresolved = tuple(
        item for item in c_arm.verified_events if not _is_complete_entailed(item)
    )

    safety_gate_passed = (
        a_review.local_review_disposition is LocalReviewDisposition.PASS
        and c_arm.verification_output.coverage_decision
        is SourceUnitCoverageDecision.CANDIDATES_COMPLETE
        and not rejected_or_unresolved
        and not a_c_conflicts
    )
    expected_diagnostics = frozenset(item.obligation_id for item in diagnostics)
    missing_diagnostics = expected_diagnostics - diagnostic_coverage.obligation_ids
    metric_improved = bool(recovered)
    whole_source_complete = (
        safety_gate_passed
        and not missing_diagnostics
        and c_coverage.obligation_ids
        == frozenset(item.obligation_id for item in obligations)
    )

    if not safety_gate_passed or missing_diagnostics:
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
        covered_diagnostics=tuple(sorted(diagnostic_coverage.obligation_ids)),
        missing_diagnostics=tuple(sorted(missing_diagnostics)),
        metric_improved=metric_improved,
        whole_source_complete=whole_source_complete,
        ready_for_confirmatory_run=(
            decision is PairedCompletenessDecision.SCIENTIFIC_IMPROVEMENT
            and whole_source_complete
        ),
        a_c_conflict_count=len(a_c_conflicts),
        c_only_entailed_event_count=len(c_only_entailed),
        c_only_review_event_count=len(c_only_review),
        c_rejected_or_unresolved_event_count=len(rejected_or_unresolved),
    )


def _covered_diagnostics(
    *,
    inventory: tuple[BoundClaimInventoryItem, ...],
    links: tuple[BoundControlledEventLink, ...],
    eligible_inventory_ids: frozenset[str],
    obligations: tuple[DiagnosticClauseObligation, ...],
) -> _Coverage:
    inventory_by_id = {item.inventory_id: item for item in inventory}
    covered: set[str] = set()
    contributors: set[str] = set()
    for obligation in obligations:
        for item in inventory:
            if item.inventory_id not in eligible_inventory_ids:
                continue
            observed_arguments = _argument_identities(item)
            expected_arguments = {
                _argument_obligation_identity(argument)
                for argument in obligation.exact_arguments
            }
            if not (
                item.item.event_type is obligation.event_type
                and item.item.claim_kind is ClaimKind.SCIENTIFIC_FINDING
                and item.item.assertion_scope is InventoryAssertionScope.SOURCE_ASSERTED
                and item.item.polarity is obligation.polarity
                and item.item.epistemic_status is InventoryEpistemicStatus.ASSERTED
                and item.item.relation_cue_span == obligation.cue_span
                and observed_arguments == expected_arguments
            ):
                continue
            matched_ids = {item.inventory_id}
            if obligation.controlled_target_event_type is not None:
                target_ids = {
                    link.controlled_inventory_id
                    for link in links
                    if link.controller_inventory_id == item.inventory_id
                    and link.controller_event_role is ClaimEventRole.THEME
                    and _matches_diagnostic_target(
                        target=inventory_by_id[link.controlled_inventory_id],
                        obligation=obligation,
                    )
                    and link.controlled_inventory_id in eligible_inventory_ids
                }
                if not target_ids:
                    continue
                matched_ids.update(target_ids)
            covered.add(obligation.obligation_id)
            contributors.update(matched_ids)
            break
    return _Coverage(
        obligation_ids=frozenset(covered),
        contributing_inventory_ids=frozenset(contributors),
    )


def _matches_diagnostic_target(
    *,
    target: BoundClaimInventoryItem,
    obligation: DiagnosticClauseObligation,
) -> bool:
    expected_arguments = {
        _argument_obligation_identity(argument)
        for argument in obligation.controlled_target_exact_arguments
    }
    return (
        target.item.event_type is obligation.controlled_target_event_type
        and target.item.claim_kind is ClaimKind.SCIENTIFIC_FINDING
        and target.item.assertion_scope is InventoryAssertionScope.CONTROLLED_TARGET
        and target.item.polarity is InventoryPolarity.UNSCOPED
        and target.item.epistemic_status is InventoryEpistemicStatus.UNASSERTED
        and target.item.relation_cue_span == obligation.controlled_target_cue_span
        and _argument_identities(target) == expected_arguments
    )


def _argument_identities(
    item: BoundClaimInventoryItem,
) -> set[tuple[ClaimArgumentRole, ClaimEventRole, str, bool]]:
    return {
        (
            argument.argument.role,
            argument.argument.event_role,
            argument.argument.exact_span,
            argument.controlled_event_ref is not None,
        )
        for argument in item.bound_arguments
    }


def _argument_obligation_identity(
    argument: ArgumentObligation,
) -> tuple[ClaimArgumentRole, ClaimEventRole, str, bool]:
    return (
        argument.role,
        argument.event_role,
        argument.exact_span,
        argument.controlled_event_ref,
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
        verification.trusted_projection_eligible
        and verification.projection_eligibility
        is ProjectionEligibilityDecision.ELIGIBLE
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
                link=link,
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
    link: BoundControlledEventLink,
    obligation: ControlledEventObligation,
) -> bool:
    target_arguments = {
        (
            argument.argument.role,
            argument.argument.event_role,
            argument.argument.exact_span,
        )
        for argument in target.bound_arguments
    }
    expected_target_arguments = {
        (ClaimArgumentRole.GENE_OR_PROTEIN, ClaimEventRole.THEME, participant)
        for participant in obligation.target_allowed_participant_spans
        if participant
        in {argument.argument.exact_span for argument in target.bound_arguments}
    }
    expected_target_arguments.add(
        (
            ClaimArgumentRole.OTHER_ENTITY,
            ClaimEventRole.TOLOC,
            obligation.target_destination_span,
        )
    )
    controller_arguments = _argument_identities(controller)
    expected_controller_arguments = {
        (
            ClaimArgumentRole.OTHER_ENTITY,
            ClaimEventRole.CAUSE,
            obligation.controller_cause_span,
            False,
        ),
        (
            ClaimArgumentRole.BIOLOGICAL_PROCESS,
            ClaimEventRole.THEME,
            target.item.exact_span,
            True,
        ),
    }
    return (
        target.item.event_type is obligation.target_event_type
        and target.item.claim_kind is ClaimKind.SCIENTIFIC_FINDING
        and target.item.assertion_scope is InventoryAssertionScope.CONTROLLED_TARGET
        and target.item.polarity is InventoryPolarity.UNSCOPED
        and target.item.epistemic_status is InventoryEpistemicStatus.UNASSERTED
        and target.item.relation_cue_span == obligation.target_cue_span
        and obligation.target_participant_span in {item[2] for item in target_arguments}
        and target_arguments == expected_target_arguments
        and controller.item.event_type is obligation.controller_event_type
        and controller.item.claim_kind is ClaimKind.SCIENTIFIC_FINDING
        and controller.item.assertion_scope is InventoryAssertionScope.SOURCE_ASSERTED
        and controller.item.polarity is InventoryPolarity.SUPPORT
        and controller.item.epistemic_status is InventoryEpistemicStatus.ASSERTED
        and controller.item.relation_cue_span == obligation.controller_cue_span
        and link.controller_event_role is ClaimEventRole.THEME
        and controller_arguments == expected_controller_arguments
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
            sorted(
                (
                    argument.role.value,
                    argument.event_role.value,
                    argument.exact_span,
                    argument.controlled_event_ref is not None,
                )
                for argument in claim.arguments
            )
        ),
    )


def _scientific_axis_identity(item: BoundClaimInventoryItem) -> tuple[object, ...]:
    claim = item.item
    return (
        claim.claim_kind,
        claim.event_type,
        claim.assertion_scope,
        tuple(
            sorted(
                (
                    argument.role.value,
                    argument.event_role.value,
                    argument.exact_span,
                    argument.controlled_event_ref is not None,
                )
                for argument in claim.arguments
            )
        ),
    )


def comparison_runtime_fingerprints() -> dict[str, object]:
    """Return runtime identities for every scientific qualification helper."""

    from scripts.validation.claim_events.finite_source_unit.normalization.execution_custody import (
        callable_source_fingerprint,
    )

    return {
        name: callable_source_fingerprint(value)
        for name, value in (
            ("compare_completeness_arms", compare_completeness_arms),
            ("covered_diagnostics", _covered_diagnostics),
            ("covered_obligations", _covered_obligations),
            ("is_complete_entailed", _is_complete_entailed),
            ("matches_diagnostic_target", _matches_diagnostic_target),
            ("matches_obligation", _matches_obligation),
            ("scientific_axis_identity", _scientific_axis_identity),
            ("scientific_identity", _scientific_identity),
        )
    }


def comparison_module_sha256() -> str:
    """Bind the issued policy to this module's complete scientific logic."""

    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


__all__ = [
    "ArgumentObligation",
    "ControlledEventObligation",
    "DiagnosticClauseObligation",
    "PairedCompletenessDecision",
    "PairedCompletenessResult",
    "VerifiedCompletenessArm",
    "compare_completeness_arms",
    "comparison_module_sha256",
    "comparison_runtime_fingerprints",
]
