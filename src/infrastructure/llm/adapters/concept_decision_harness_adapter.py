"""Deterministic harness adapter for Concept Manager AI decisions."""

from __future__ import annotations

from artana_evidence_db.governance_ports import ConceptDecisionHarnessPort
from artana_evidence_db.kernel_domain_models import (
    ConceptDecisionProposal,
    ConceptHarnessCheck,
    ConceptHarnessVerdict,
)

_MIN_CONFIDENCE_FOR_PASS = 0.55


class DeterministicConceptDecisionHarnessAdapter(ConceptDecisionHarnessPort):
    """Deterministic pre-apply checks for concept decision proposals.

    This adapter is intentionally conservative: missing rationale/evidence
    downgrades to `NEEDS_REVIEW`, and malformed payloads hard-fail.
    """

    def evaluate(
        self,
        proposal: ConceptDecisionProposal,
    ) -> ConceptHarnessVerdict:
        checks: list[ConceptHarnessCheck] = []

        has_payload = bool(proposal.decision_payload)
        checks.append(
            ConceptHarnessCheck(
                check_id="payload_present",
                passed=has_payload,
                detail=(
                    "Decision payload contains structured fields"
                    if has_payload
                    else "Decision payload is empty"
                ),
            ),
        )
        if not has_payload:
            return ConceptHarnessVerdict(
                outcome="FAIL",
                rationale="Decision payload is required",
                checks=checks,
                errors=["missing_decision_payload"],
            )

        has_rationale = bool(proposal.rationale and proposal.rationale.strip())
        checks.append(
            ConceptHarnessCheck(
                check_id="rationale_present",
                passed=has_rationale,
                detail=(
                    "Rationale provided"
                    if has_rationale
                    else "Rationale missing; requires manual review"
                ),
            ),
        )

        confidence = proposal.confidence
        confidence_pass = confidence is None or confidence >= _MIN_CONFIDENCE_FOR_PASS
        checks.append(
            ConceptHarnessCheck(
                check_id="confidence_floor",
                passed=confidence_pass,
                detail=(
                    (
                        "Confidence meets floor"
                        if confidence_pass
                        else f"Confidence {confidence:.2f} below floor {_MIN_CONFIDENCE_FOR_PASS:.2f}"
                    )
                    if confidence is not None
                    else "Confidence omitted; manual review recommended"
                ),
            ),
        )
        if not confidence_pass:
            return ConceptHarnessVerdict(
                outcome="FAIL",
                rationale="Confidence below minimum floor",
                checks=checks,
                errors=["confidence_below_floor"],
            )

        if not has_rationale or confidence is None:
            return ConceptHarnessVerdict(
                outcome="NEEDS_REVIEW",
                rationale="Proposal requires review due to incomplete explanatory fields",
                checks=checks,
                metadata={"review_reason": "missing_rationale_or_confidence"},
            )

        return ConceptHarnessVerdict(
            outcome="PASS",
            rationale="Deterministic harness checks passed",
            checks=checks,
        )
