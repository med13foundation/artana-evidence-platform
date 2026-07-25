"""Bounded source-general claim verification orchestration."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

from artana_evidence_api.document_extraction_contracts import (
    ExtractedRelationCandidate,
)
from artana_evidence_api.document_extraction_support.claim_frames.falsification import (
    ClaimVerificationTerminal,
    ValidatedClaimVerification,
    VerificationModelRelationship,
    verifier_model_relationship,
)
from artana_evidence_api.document_extraction_support.claim_frames.verification_budget import (
    ClaimVerificationBudgetExhaustedError,
    ClaimVerificationBudgetLimits,
    ClaimVerificationBudgetTracker,
)
from artana_evidence_api.document_extraction_support.llm_extraction.claim_falsification import (
    ClaimFalsificationStageResult,
    run_claim_falsification_stage,
)
from artana_evidence_api.document_extraction_support.llm_extraction.claim_repair import (
    ClaimRepairStageResult,
    run_claim_repair_stage,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    ModelAttemptAuditRecord,
    ModelStepRunner,
    current_model_attempt_audit,
)
from artana_evidence_api.runtime.config import normalize_litellm_model_id


@dataclass(frozen=True, slots=True)
class ClaimVerificationRuntimeConfig:
    enabled: bool
    framing_model_id: str
    verification_model_id: str
    repair_model_id: str
    reverification_model_id: str
    budget_limits: ClaimVerificationBudgetLimits

    @classmethod
    def from_environment(
        cls,
        *,
        default_model_id: str,
    ) -> ClaimVerificationRuntimeConfig:
        enabled = _environment_bool(
            "ARTANA_CLAIM_VERIFICATION_EXPERIMENT",
            default=False,
        )
        normalized_default = normalize_litellm_model_id(default_model_id)
        if not enabled:
            return cls(
                enabled=False,
                framing_model_id=normalized_default,
                verification_model_id=normalized_default,
                repair_model_id=normalized_default,
                reverification_model_id=normalized_default,
                budget_limits=ClaimVerificationBudgetLimits(),
            )
        verification_model = _model_from_environment(
            "ARTANA_CLAIM_VERIFICATION_MODEL",
            default_model_id,
        )
        return cls(
            enabled=True,
            framing_model_id=_model_from_environment(
                "ARTANA_CLAIM_FRAMING_MODEL",
                default_model_id,
            ),
            verification_model_id=verification_model,
            repair_model_id=_model_from_environment(
                "ARTANA_CLAIM_REPAIR_MODEL",
                default_model_id,
            ),
            reverification_model_id=_model_from_environment(
                "ARTANA_CLAIM_REVERIFICATION_MODEL",
                verification_model,
            ),
            budget_limits=ClaimVerificationBudgetLimits(
                max_verifier_calls=_environment_int(
                    "ARTANA_CLAIM_MAX_VERIFIER_CALLS",
                    128,
                ),
                max_repairs=_environment_int("ARTANA_CLAIM_MAX_REPAIRS", 32),
                max_tokens=_environment_int("ARTANA_CLAIM_MAX_TOKENS", 500_000),
                max_latency_seconds=_environment_float(
                    "ARTANA_CLAIM_MAX_LATENCY_SECONDS",
                    900.0,
                ),
                max_cost_usd=_environment_float(
                    "ARTANA_CLAIM_MAX_COST_USD",
                    5.0,
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class ClaimVerificationLoopOutcome:
    candidate: ExtractedRelationCandidate
    terminal: ClaimVerificationTerminal
    terminal_reason: str
    state_transitions: tuple[str, ...]
    original_claim_sha256: str | None
    final_claim_sha256: str | None
    initial_verification: ValidatedClaimVerification | None = None
    initial_attempt: ModelAttemptAuditRecord | None = None
    repair: ClaimRepairStageResult | None = None
    repair_attempt: ModelAttemptAuditRecord | None = None
    reverification: ValidatedClaimVerification | None = None
    reverification_attempt: ModelAttemptAuditRecord | None = None
    verifier_relationship: VerificationModelRelationship | None = None
    budget_usage: dict[str, object] | None = None

    def as_json(self) -> dict[str, object]:
        return {
            "terminal": self.terminal.value,
            "terminal_reason": self.terminal_reason,
            "state_transitions": self.state_transitions,
            "qualification_complete": False,
            "trusted_graph_promotion_allowed": False,
            "original_claim_sha256": self.original_claim_sha256,
            "final_claim_sha256": self.final_claim_sha256,
            "initial_verification": (
                self.initial_verification.finding.model_dump(mode="json")
                if self.initial_verification is not None
                else None
            ),
            "initial_prompt_sha256": (
                self.initial_attempt.prompt_sha256
                if self.initial_attempt is not None
                else None
            ),
            "initial_evidence_offsets": (
                self.initial_verification.evidence_offsets
                if self.initial_verification is not None
                else None
            ),
            "initial_source_region_sha256": (
                self.initial_verification.source_region_sha256
                if self.initial_verification is not None
                else None
            ),
            "initial_statistical_evidence_offsets": (
                self.initial_verification.statistical_evidence_offsets
                if self.initial_verification is not None
                else None
            ),
            "initial_statistical_cue_offsets": (
                self.initial_verification.statistical_cue_offsets
                if self.initial_verification is not None
                else None
            ),
            "initial_statistical_literal_offsets": (
                self.initial_verification.statistical_literal_offsets
                if self.initial_verification is not None
                else None
            ),
            "initial_author_claim_evidence_offsets": (
                self.initial_verification.author_claim_evidence_offsets
                if self.initial_verification is not None
                else None
            ),
            "initial_attempt": (
                self.initial_attempt.as_json()
                if self.initial_attempt is not None
                else None
            ),
            "repair_patch": (
                self.repair.patch.model_dump(mode="json")
                if self.repair is not None
                else None
            ),
            "repair_prompt_version": (
                self.repair.prompt_version if self.repair is not None else None
            ),
            "repair_changed_fields": (
                self.repair.repair.changed_fields if self.repair is not None else None
            ),
            "repair_evidence_offsets": (
                self.repair.repair.evidence_offsets
                if self.repair is not None
                else None
            ),
            "repair_source_region_sha256": (
                self.repair.repair.source_region_sha256
                if self.repair is not None
                else None
            ),
            "repair_attempt": (
                self.repair_attempt.as_json()
                if self.repair_attempt is not None
                else None
            ),
            "reverification": (
                self.reverification.finding.model_dump(mode="json")
                if self.reverification is not None
                else None
            ),
            "reverification_prompt_sha256": (
                self.reverification_attempt.prompt_sha256
                if self.reverification_attempt is not None
                else None
            ),
            "reverification_evidence_offsets": (
                self.reverification.evidence_offsets
                if self.reverification is not None
                else None
            ),
            "reverification_source_region_sha256": (
                self.reverification.source_region_sha256
                if self.reverification is not None
                else None
            ),
            "reverification_statistical_evidence_offsets": (
                self.reverification.statistical_evidence_offsets
                if self.reverification is not None
                else None
            ),
            "reverification_statistical_cue_offsets": (
                self.reverification.statistical_cue_offsets
                if self.reverification is not None
                else None
            ),
            "reverification_statistical_literal_offsets": (
                self.reverification.statistical_literal_offsets
                if self.reverification is not None
                else None
            ),
            "reverification_author_claim_evidence_offsets": (
                self.reverification.author_claim_evidence_offsets
                if self.reverification is not None
                else None
            ),
            "reverification_attempt": (
                self.reverification_attempt.as_json()
                if self.reverification_attempt is not None
                else None
            ),
            "verifier_relationship": (
                self.verifier_relationship.value
                if self.verifier_relationship is not None
                else None
            ),
            "budget_usage": self.budget_usage,
        }


async def run_claim_verification_loop(  # noqa: PLR0911, PLR0912, PLR0915
    *,
    candidate: ExtractedRelationCandidate,
    source_region: str,
    source_sha256: str,
    semantic_unit_id: str,
    client: object,
    tenant: object,
    config: ClaimVerificationRuntimeConfig,
    budget: ClaimVerificationBudgetTracker,
    step_runner: ModelStepRunner,
    execution_namespace: str,
) -> ClaimVerificationLoopOutcome:
    """Verify, optionally repair once, and freshly reverify one claim."""

    frame = candidate.claim_frame
    if frame is None:
        return _terminal_outcome(
            candidate=candidate,
            terminal=ClaimVerificationTerminal.INVALID_VERIFICATION,
            reason="candidate_missing_claim_frame",
            transitions=("FRAMED", "INVALID_VERIFICATION"),
            original_claim_sha256=None,
            final_claim_sha256=None,
            budget=budget,
        )
    original_hash = frame.semantic_fingerprint
    if candidate.framing_decision != "SINGLE_FRAME":
        return _terminal_outcome(
            candidate=candidate,
            terminal=ClaimVerificationTerminal.REVIEW_ONLY,
            reason="framing_decision_not_single_frame",
            transitions=("FRAMED", "REVIEW_ONLY"),
            original_claim_sha256=original_hash,
            final_claim_sha256=original_hash,
            budget=budget,
        )
    initial: ClaimFalsificationStageResult | None = None
    initial_charged = False
    initial_record_start = _audit_record_count()
    try:
        budget.reserve_verifier()
        initial = await run_claim_falsification_stage(
            claim_frame=frame,
            source_region=source_region,
            source_sha256=source_sha256,
            semantic_unit_id=semantic_unit_id,
            client=client,
            tenant=tenant,
            model_id=config.verification_model_id,
            step_runner=step_runner,
            execution_namespace=execution_namespace,
        )
        budget.charge_verifier(initial.attempt_record)
        initial_charged = True
        _require_complete_usage_receipts(budget)
        _require_new_provider_execution(initial.attempt_record)
    except ClaimVerificationBudgetExhaustedError as exc:
        return _terminal_outcome(
            candidate=candidate,
            terminal=ClaimVerificationTerminal.REVIEW_ONLY,
            reason=str(exc),
            transitions=("FRAMED", "REVIEW_ONLY"),
            original_claim_sha256=original_hash,
            final_claim_sha256=original_hash,
            budget=budget,
            initial=initial,
        )
    except Exception as exc:  # noqa: BLE001 - provider failures terminalize claims
        if not initial_charged:
            initial_attempt = _charge_failed_attempt(
                budget=budget,
                attempt_role="claim_verification",
                semantic_unit_id=semantic_unit_id,
                first_record_index=initial_record_start,
                repair=False,
            )
        else:
            initial_attempt = initial.attempt_record if initial is not None else None
        return _terminal_outcome(
            candidate=candidate,
            terminal=ClaimVerificationTerminal.INVALID_VERIFICATION,
            reason=(
                f"initial_verification_invalid:{type(exc).__name__}:{exc}"
            ),
            transitions=("FRAMED", "INVALID_VERIFICATION"),
            original_claim_sha256=original_hash,
            final_claim_sha256=original_hash,
            budget=budget,
            initial=initial,
            initial_attempt=initial_attempt,
        )

    if initial.verification.fully_verified:
        return _terminal_outcome(
            candidate=candidate,
            terminal=ClaimVerificationTerminal.VERIFIED_UNREPAIRED,
            reason="source_only_verification_passed_qualification_locked",
            transitions=("FRAMED", "VERIFIED_UNREPAIRED"),
            original_claim_sha256=original_hash,
            final_claim_sha256=original_hash,
            budget=budget,
            initial=initial,
        )
    if not initial.verification.repairable:
        return _terminal_outcome(
            candidate=candidate,
            terminal=ClaimVerificationTerminal.REVIEW_ONLY,
            reason="verification_failed_nonrepairable",
            transitions=("FRAMED", "REVIEW_ONLY"),
            original_claim_sha256=original_hash,
            final_claim_sha256=original_hash,
            budget=budget,
            initial=initial,
        )

    repair: ClaimRepairStageResult | None = None
    repair_charged = False
    repair_record_start = _audit_record_count()
    try:
        budget.reserve_repair()
        repair = await run_claim_repair_stage(
            claim_frame=frame,
            source_region=source_region,
            source_sha256=source_sha256,
            failure_axes=initial.verification.finding.failure_axes,
            failure_evidence_spans=initial.verification.finding.evidence_spans,
            semantic_unit_id=semantic_unit_id,
            client=client,
            tenant=tenant,
            model_id=config.repair_model_id,
            step_runner=step_runner,
            execution_namespace=execution_namespace,
        )
        budget.charge_repair(repair.attempt_record)
        repair_charged = True
        _require_complete_usage_receipts(budget)
    except ClaimVerificationBudgetExhaustedError as exc:
        return _terminal_outcome(
            candidate=candidate,
            terminal=ClaimVerificationTerminal.REVIEW_ONLY,
            reason=str(exc),
            transitions=("FRAMED", "REPAIR_REQUIRED", "REVIEW_ONLY"),
            original_claim_sha256=original_hash,
            final_claim_sha256=original_hash,
            budget=budget,
            initial=initial,
            repair=repair,
        )
    except Exception as exc:  # noqa: BLE001 - provider failures terminalize claims
        if not repair_charged:
            repair_attempt = _charge_failed_attempt(
                budget=budget,
                attempt_role="claim_repair",
                semantic_unit_id=semantic_unit_id,
                first_record_index=repair_record_start,
                repair=True,
            )
        else:
            repair_attempt = repair.attempt_record if repair is not None else None
        return _terminal_outcome(
            candidate=candidate,
            terminal=ClaimVerificationTerminal.INVALID_VERIFICATION,
            reason=f"repair_invalid:{type(exc).__name__}:{exc}",
            transitions=(
                "FRAMED",
                "REPAIR_REQUIRED",
                "INVALID_VERIFICATION",
            ),
            original_claim_sha256=original_hash,
            final_claim_sha256=original_hash,
            budget=budget,
            initial=initial,
            repair_attempt=repair_attempt,
        )

    repaired_frame = repair.repair.repaired_frame
    repaired_candidate = replace(
        candidate,
        subject_label=repaired_frame.subject,
        relation_type=repaired_frame.predicate,
        object_label=repaired_frame.object,
        claim_frame=repaired_frame,
    )
    relationship = verifier_model_relationship(
        first_model_id=config.verification_model_id,
        second_model_id=config.reverification_model_id,
    )
    reverified: ClaimFalsificationStageResult | None = None
    reverification_charged = False
    reverification_record_start = _audit_record_count()
    try:
        budget.reserve_verifier()
        reverified = await run_claim_falsification_stage(
            claim_frame=repaired_frame,
            source_region=source_region,
            source_sha256=source_sha256,
            semantic_unit_id=semantic_unit_id,
            client=client,
            tenant=tenant,
            model_id=config.reverification_model_id,
            step_runner=step_runner,
            execution_namespace=execution_namespace,
            phase="reverification",
        )
        budget.charge_verifier(reverified.attempt_record)
        reverification_charged = True
        _require_complete_usage_receipts(budget)
        _require_fresh_reverification(
            initial_attempt=initial.attempt_record,
            reverification_attempt=reverified.attempt_record,
        )
    except ClaimVerificationBudgetExhaustedError as exc:
        return _terminal_outcome(
            candidate=repaired_candidate,
            terminal=ClaimVerificationTerminal.REVIEW_ONLY,
            reason=str(exc),
            transitions=(
                "FRAMED",
                "REPAIR_REQUIRED",
                "REPAIRED",
                "REVIEW_ONLY",
            ),
            original_claim_sha256=original_hash,
            final_claim_sha256=repaired_frame.semantic_fingerprint,
            budget=budget,
            initial=initial,
            repair=repair,
            relationship=relationship,
            reverification=reverified,
        )
    except Exception as exc:  # noqa: BLE001 - provider failures terminalize claims
        if not reverification_charged:
            reverification_attempt = _charge_failed_attempt(
                budget=budget,
                attempt_role="claim_reverification",
                semantic_unit_id=semantic_unit_id,
                first_record_index=reverification_record_start,
                repair=False,
            )
        else:
            reverification_attempt = (
                reverified.attempt_record if reverified is not None else None
            )
        return _terminal_outcome(
            candidate=repaired_candidate,
            terminal=ClaimVerificationTerminal.INVALID_VERIFICATION,
            reason=f"reverification_invalid:{type(exc).__name__}:{exc}",
            transitions=(
                "FRAMED",
                "REPAIR_REQUIRED",
                "REPAIRED",
                "INVALID_VERIFICATION",
            ),
            original_claim_sha256=original_hash,
            final_claim_sha256=repaired_frame.semantic_fingerprint,
            budget=budget,
            initial=initial,
            repair=repair,
            relationship=relationship,
            reverification=reverified,
            reverification_attempt=reverification_attempt,
        )

    terminal = (
        ClaimVerificationTerminal.VERIFIED_AFTER_REPAIR
        if reverified.verification.fully_verified
        else ClaimVerificationTerminal.REVIEW_ONLY
    )
    return _terminal_outcome(
        candidate=repaired_candidate,
        terminal=terminal,
        reason=(
            "fresh_reverification_passed_qualification_locked"
            if terminal is ClaimVerificationTerminal.VERIFIED_AFTER_REPAIR
            else "fresh_reverification_failed"
        ),
        transitions=(
            "FRAMED",
            "REPAIR_REQUIRED",
            "REPAIRED",
            terminal.value,
        ),
        original_claim_sha256=original_hash,
        final_claim_sha256=repaired_frame.semantic_fingerprint,
        budget=budget,
        initial=initial,
        repair=repair,
        reverification=reverified,
        relationship=relationship,
    )


def _terminal_outcome(
    *,
    candidate: ExtractedRelationCandidate,
    terminal: ClaimVerificationTerminal,
    reason: str,
    transitions: tuple[str, ...],
    original_claim_sha256: str | None,
    final_claim_sha256: str | None,
    budget: ClaimVerificationBudgetTracker,
    initial: ClaimFalsificationStageResult | None = None,
    initial_attempt: ModelAttemptAuditRecord | None = None,
    repair: ClaimRepairStageResult | None = None,
    repair_attempt: ModelAttemptAuditRecord | None = None,
    reverification: ClaimFalsificationStageResult | None = None,
    reverification_attempt: ModelAttemptAuditRecord | None = None,
    relationship: VerificationModelRelationship | None = None,
) -> ClaimVerificationLoopOutcome:
    review_reason = f"claim_verification_{terminal.value.casefold()}"
    review_only_candidate = replace(
        candidate,
        review_status="review_only",
        review_reason_codes=tuple(
            dict.fromkeys((*candidate.review_reason_codes, review_reason)),
        ),
        claim_verification_terminal=terminal.value,
        claim_verification_qualification_complete=False,
    )
    return ClaimVerificationLoopOutcome(
        candidate=review_only_candidate,
        terminal=terminal,
        terminal_reason=reason,
        state_transitions=transitions,
        original_claim_sha256=original_claim_sha256,
        final_claim_sha256=final_claim_sha256,
        initial_verification=(initial.verification if initial is not None else None),
        initial_attempt=(
            initial.attempt_record if initial is not None else initial_attempt
        ),
        repair=repair,
        repair_attempt=(
            repair.attempt_record if repair is not None else repair_attempt
        ),
        reverification=(
            reverification.verification if reverification is not None else None
        ),
        reverification_attempt=(
            reverification.attempt_record
            if reverification is not None
            else reverification_attempt
        ),
        verifier_relationship=relationship,
        budget_usage=budget.usage.as_json(),
    )


def _audit_record_count() -> int:
    session = current_model_attempt_audit()
    return len(session.records) if session is not None else 0


def _last_stage_attempt(
    *,
    attempt_role: str,
    semantic_unit_id: str,
    first_record_index: int,
) -> ModelAttemptAuditRecord | None:
    session = current_model_attempt_audit()
    if session is None:
        return None
    return next(
        (
            record
            for record in reversed(session.records[first_record_index:])
            if record.attempt_role == attempt_role
            and record.semantic_unit_id == semantic_unit_id
        ),
        None,
    )


def _charge_failed_attempt(
    *,
    budget: ClaimVerificationBudgetTracker,
    attempt_role: str,
    semantic_unit_id: str,
    first_record_index: int,
    repair: bool,
) -> ModelAttemptAuditRecord | None:
    record = _last_stage_attempt(
        attempt_role=attempt_role,
        semantic_unit_id=semantic_unit_id,
        first_record_index=first_record_index,
    )
    if record is None:
        return None
    try:
        if repair:
            budget.charge_repair(record)
        else:
            budget.charge_verifier(record)
    except ClaimVerificationBudgetExhaustedError:
        # The over-budget usage remains recorded; terminalization still reports
        # the original invalid scientific stage rather than masking it.
        pass
    return record


def _require_new_provider_execution(record: ModelAttemptAuditRecord) -> None:
    if record.replayed is not False or record.provider_response_id is None:
        raise ValueError("verification requires a new provider execution receipt")


def _require_fresh_reverification(
    *,
    initial_attempt: ModelAttemptAuditRecord,
    reverification_attempt: ModelAttemptAuditRecord,
) -> None:
    _require_new_provider_execution(initial_attempt)
    _require_new_provider_execution(reverification_attempt)
    if initial_attempt.invocation_id == reverification_attempt.invocation_id:
        raise ValueError("reverification reused the initial invocation")
    if initial_attempt.provider_response_id == reverification_attempt.provider_response_id:
        raise ValueError("reverification reused the initial provider response")


def _require_complete_usage_receipts(
    budget: ClaimVerificationBudgetTracker,
) -> None:
    if not budget.usage.usage_receipts_complete:
        raise ValueError("verification model usage receipt is incomplete")


def _environment_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be an explicit boolean value")


def _environment_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw is not None else default


def _environment_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw is not None else default


def _model_from_environment(name: str, default: str) -> str:
    """Resolve one verifier model id, refusing an unknown override.

    These four variables previously accepted any string with no registry check
    at all, so a typo silently sent formal traffic to a model nobody chose and
    a deliberate override bypassed `allow_runtime_model_overrides` entirely.
    An override must name a model the registry knows; anything else is a
    configuration error and fails closed rather than guessing
    (D8, ART-MODEL-004).
    """

    raw = os.getenv(name)
    if raw is None:
        return normalize_litellm_model_id(default)
    # Registry keys use the `provider:model` form; `normalize_litellm_model_id`
    # rewrites that to `provider/model` for the client.  Look up the raw value
    # and return the normalised one, or every valid override is rejected.
    if not _is_registered_model(raw.strip()):
        message = (
            f"{name}={raw!r} is not a registered model. Add it to the model "
            f"registry in artana.toml, or unset the variable to use {default!r}."
        )
        raise ValueError(message)
    return normalize_litellm_model_id(raw)


def _is_registered_model(model_id: str) -> bool:
    """Return whether the registry knows this model id."""

    from artana_evidence_api.runtime.model_registry import get_model_registry

    try:
        get_model_registry().get_model(model_id)
    except KeyError:
        return False
    return True


__all__ = [
    "ClaimVerificationLoopOutcome",
    "ClaimVerificationRuntimeConfig",
    "run_claim_verification_loop",
]
