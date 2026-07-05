"""Adversarial checks for relation feasibility reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.validation.relation_feasibility.models import FeasibilityReport

_TRUSTED_GRAPH_GENERIC_RELATION_RATE_TARGET = 0.05


@dataclass(frozen=True, slots=True)
class AdversarialFinding:
    """One quality illusion detected in a feasibility report."""

    code: str
    message: str

    def to_json(self) -> dict[str, str]:
        """Return a JSON-compatible representation."""

        return {
            "code": self.code,
            "message": self.message,
        }


def find_quality_illusions(report: FeasibilityReport) -> tuple[AdversarialFinding, ...]:
    """Return report-level warnings that can make quality look better than it is."""

    findings: list[AdversarialFinding] = []
    summary = report.summary
    if summary.fallback_case_count > 0 and summary.agent_completed_case_count == 0:
        findings.append(
            AdversarialFinding(
                code="fallback_only_report",
                message=(
                    "All reported agent-mode candidates came from fallback or "
                    "agent-unavailable runs."
                ),
            ),
        )
    if summary.fallback_credited_as_agent_count > 0:
        findings.append(
            AdversarialFinding(
                code="fallback_candidates_look_valuable",
                message=(
                    "Fallback candidates would look valuable under all-candidate "
                    "metrics and must not be credited as completed-agent quality."
                ),
            ),
        )
    if (
        summary.entailment_required_count > 0
        and summary.entailment_checked_rate < 1.0
    ):
        findings.append(
            AdversarialFinding(
                code="entailment_not_checked",
                message=(
                    "At least one relation requiring entailment was not checked."
                ),
            ),
        )
    if summary.grounded_sentence_rate < 1.0 and summary.candidate_count > 0:
        findings.append(
            AdversarialFinding(
                code="source_sentence_not_grounded",
                message=(
                    "At least one candidate evidence sentence could not be "
                    "grounded in the source text."
                ),
            ),
        )
    if summary.raw_unknown_relation_type_count > 0:
        findings.append(
            AdversarialFinding(
                code="raw_unknown_relation_type_kept",
                message=(
                    "At least one candidate kept an unapproved raw relation type "
                    "instead of mapping it or sending it to governed review."
                ),
            ),
        )
    if summary.both_arguments_present_rate < 1.0 and summary.candidate_count > 0:
        findings.append(
            AdversarialFinding(
                code="relation_arguments_missing_from_sentence",
                message=(
                    "At least one candidate evidence sentence is missing the "
                    "subject or object argument."
                ),
            ),
        )
    if summary.generic_relation_rate > _TRUSTED_GRAPH_GENERIC_RELATION_RATE_TARGET:
        findings.append(
            AdversarialFinding(
                code="generic_relation_rate_high",
                message="Generic relation rate exceeds the trusted-graph target.",
            ),
        )
    return tuple(findings)


__all__ = ["AdversarialFinding", "find_quality_illusions"]
