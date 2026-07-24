"""V16-local, occurrence-aware source reference for one scope boundary.

This is a prospective reference contract.  It does not alter the V9 panel or
the shared historical grader, and it is deliberately separate from provider
prompt construction.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.panel import (
        GeneralizationCase,
    )

UNCERTAINTY_CASE_ID = "generalization-uncertainty"
_EVIDENCE = (
    "A total of 947 variants were detected in the SLC12A3 gene, the majority "
    "of which were classified as of uncertain significance."
)


class V16ReferenceError(ValueError):
    """A frozen V16 source occurrence no longer resolves exactly."""


@dataclass(frozen=True, slots=True)
class ExpectedOccurrence:
    """One end-exclusive source occurrence bound to a V16 reference rule."""

    exact_text: str
    start: int
    end: int

    def verify(self, case: GeneralizationCase) -> None:
        if case.source[self.start : self.end] != self.exact_text:
            raise V16ReferenceError(f"source occurrence changed: {self.exact_text}")


@dataclass(frozen=True, slots=True)
class UncertaintyScopeReference:
    """Required structure for the source's cohort, locus, and majority claim."""

    case_id: str
    evidence: ExpectedOccurrence
    cohort: ExpectedOccurrence
    locus_full: ExpectedOccurrence
    locus_identifier: ExpectedOccurrence
    partitive: ExpectedOccurrence
    relation_type: str
    partitive_kind: str

    def verify(self, case: GeneralizationCase) -> None:
        if case.case_id != self.case_id:
            raise V16ReferenceError("scope reference case identity changed")
        for occurrence in (
            self.evidence,
            self.cohort,
            self.locus_full,
            self.locus_identifier,
            self.partitive,
        ):
            occurrence.verify(case)
        if not (
            self.evidence.start
            <= self.cohort.start
            < self.cohort.end
            <= self.evidence.end
        ):
            raise V16ReferenceError("cohort leaves source evidence")
        if not (
            self.evidence.start
            <= self.locus_full.start
            < self.locus_full.end
            <= self.evidence.end
        ):
            raise V16ReferenceError("locus leaves source evidence")
        if not (
            self.evidence.start
            <= self.partitive.start
            < self.partitive.end
            <= self.evidence.end
        ):
            raise V16ReferenceError("partitive leaves source evidence")

    @property
    def allowed_locus_texts(self) -> frozenset[str]:
        """Preserve V14's independently lexicalized-identifier boundary."""

        return frozenset((self.locus_full.exact_text, self.locus_identifier.exact_text))

    @property
    def allowed_evidence_texts(self) -> frozenset[str]:
        """Accept the sentence, with an optional literal source section label."""

        sentence = self.evidence.exact_text
        return frozenset((sentence, f"RESULTS: {sentence}"))

    def accepts_evidence(self, exact_evidence: str) -> bool:
        return exact_evidence in self.allowed_evidence_texts

    def as_json(self) -> dict[str, object]:
        return asdict(self)


UNCERTAINTY_SCOPE_REFERENCE = UncertaintyScopeReference(
    case_id=UNCERTAINTY_CASE_ID,
    evidence=ExpectedOccurrence(_EVIDENCE, 960, 1086),
    cohort=ExpectedOccurrence("947 variants", 971, 983),
    locus_full=ExpectedOccurrence("SLC12A3 gene", 1005, 1017),
    locus_identifier=ExpectedOccurrence("SLC12A3", 1005, 1012),
    partitive=ExpectedOccurrence("the majority of which", 1019, 1040),
    relation_type="IDENTITY_OR_SCOPE_RESTRICTION",
    partitive_kind="MAJORITY",
)


def reference_sha256(
    reference: UncertaintyScopeReference = UNCERTAINTY_SCOPE_REFERENCE,
) -> str:
    """Hash the versioned reference without depending on JSON presentation."""

    raw = json.dumps(
        reference.as_json(), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "ExpectedOccurrence",
    "UNCERTAINTY_CASE_ID",
    "UNCERTAINTY_SCOPE_REFERENCE",
    "UncertaintyScopeReference",
    "V16ReferenceError",
    "reference_sha256",
]
