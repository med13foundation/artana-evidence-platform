"""V13-local verification of the unchanged frozen dual-lane grader."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.generalization.grading import (
    policy as shared_policy,
)
from scripts.validation.public_gold.staged_event.generalization.grading.agreement import (
    canonical_review_sha256,
)
from scripts.validation.public_gold.staged_event.generalization.grading.artifacts import (
    load_review,
)
from scripts.validation.public_gold.staged_event.generalization.grading.contracts import (
    FrozenDualLanePolicy,
    GraderReviewBatch,
    PrimarySourceEvidence,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.grading.config import (
        GradingArtifactPaths,
    )
    from scripts.validation.public_gold.staged_event.generalization.panel import (
        GeneralizationCase,
    )

V12_GRADING_SOURCE_SHA256 = {
    "scripts/validation/public_gold/staged_event/generalization/grading/artifacts.py": (
        "4bbd831cae66dafac9f0be32693edd393de76cefb72b487cd3b4ef6542240759"
    ),
    "scripts/validation/public_gold/staged_event/generalization/grading/policy.py": (
        "cd630f3c4dc8a7725a53ab0fec063413ec932fc39b4cc3dccf279a53da795e4b"
    ),
    "scripts/validation/public_gold/staged_event/generalization/grading/evaluation.py": (
        "6dc6186cb262d3494e3decc8143790bcbb1132ad62173b807155c5eb905dc1e9"
    ),
    "scripts/validation/public_gold/staged_event/generalization/repair_v12/contracts.py": (
        "321e32c0a74cc889e08bf06f5320e0c8f7f560db1592b818e55317e9ddddda05"
    ),
    "scripts/validation/public_gold/staged_event/generalization/repair_v12/evaluation.py": (
        "0dc2d8a0c20f681d868598822a090a42c5e96c4ccb3c44affa0cd244cecf8993"
    ),
}
V12_GRADING_POLICY_SHA256 = (
    "da315ef20300e669fbbfb2565f26faad7ba2ba1336de5d7939a7b22b34a2420c"
)
_REVIEW_COUNT_WITH_TIEBREAKER = 3


class V13FrozenPolicyError(RuntimeError):
    """The V13 adapter cannot prove the historical grader remains frozen."""


def verify_v13_frozen_policy(
    paths: GradingArtifactPaths,
    *,
    cases: tuple[GeneralizationCase, ...],
) -> FrozenDualLanePolicy:
    """Verify the V12 grader against tracked cases without rebuilding raw data."""

    verify_shared_grader_sources()
    if len({case.case_id for case in cases}) != len(cases):
        raise V13FrozenPolicyError("frozen panel case IDs are not unique")
    panel = {case.case_id: case for case in cases}
    policy = FrozenDualLanePolicy.model_validate_json(
        paths.policy.read_text(encoding="utf-8")
    )
    if shared_policy.policy_sha256(policy) != V12_GRADING_POLICY_SHA256:
        raise V13FrozenPolicyError("frozen grading policy hash changed")

    reviews = _load_reviews(paths)
    _verify_review_evidence(paths.evidence, reviews)
    _verify_review_and_policy_identity(policy, reviews, panel)
    _verify_policy_cases(policy, panel)
    return policy


def verify_shared_grader_sources() -> None:
    """Require the shared grader implementation to remain byte-identical to V12."""

    repo = Path(__file__).resolve().parents[6]
    observed = {name: _sha256(repo / name) for name in V12_GRADING_SOURCE_SHA256}
    if observed != V12_GRADING_SOURCE_SHA256:
        raise V13FrozenPolicyError("shared frozen grader sources changed after V12")


def _load_reviews(
    paths: GradingArtifactPaths,
) -> tuple[GraderReviewBatch, GraderReviewBatch, GraderReviewBatch | None]:
    return (
        load_review(paths.first_review),
        load_review(paths.second_review),
        load_review(paths.tiebreaker_review)
        if paths.tiebreaker_review.exists()
        else None,
    )


def _verify_review_and_policy_identity(
    policy: FrozenDualLanePolicy,
    reviews: tuple[
        GraderReviewBatch,
        GraderReviewBatch,
        GraderReviewBatch | None,
    ],
    panel: dict[str, GeneralizationCase],
) -> None:
    batches = tuple(review for review in reviews if review is not None)
    if policy.primary_reviewers != (batches[0].reviewer, batches[1].reviewer):
        raise V13FrozenPolicyError("frozen policy primary reviewer identities changed")
    expected_tiebreaker = (
        batches[2].reviewer if len(batches) == _REVIEW_COUNT_WITH_TIEBREAKER else None
    )
    if policy.tiebreaker_reviewer != expected_tiebreaker:
        raise V13FrozenPolicyError("frozen policy tiebreaker identity changed")
    expected_review_hashes = {
        batch.reviewer.reviewer_id: canonical_review_sha256(batch) for batch in batches
    }
    if policy.review_artifact_sha256 != expected_review_hashes:
        raise V13FrozenPolicyError("frozen policy review artifact hashes changed")

    merged_evidence = _merge_evidence(batches)
    if policy.evidence != merged_evidence:
        raise V13FrozenPolicyError("frozen policy primary-source evidence changed")
    expected_case_ids = set(panel)
    for batch in batches:
        if {case.case_id for case in batch.cases} != expected_case_ids:
            raise V13FrozenPolicyError("grader batch panel coverage changed")
        for review in batch.cases:
            case = panel[review.case_id]
            if (
                review.source_id != case.source_id
                or review.source_sha256 != case.source_sha256
            ):
                raise V13FrozenPolicyError("grader review source custody changed")


def _verify_policy_cases(
    policy: FrozenDualLanePolicy,
    panel: dict[str, GeneralizationCase],
) -> None:
    if {case.case_id for case in policy.cases} != set(panel):
        raise V13FrozenPolicyError("frozen policy panel coverage changed")
    for frozen in policy.cases:
        case = panel[frozen.case_id]
        if frozen.source_id != case.source_id:
            raise V13FrozenPolicyError("frozen policy source identity changed")
        if frozen.source_sha256 != case.source_sha256:
            raise V13FrozenPolicyError("frozen policy source hash changed")
        if frozen.core_reference_sha256 != _core_reference_sha256(case):
            raise V13FrozenPolicyError("frozen policy core reference changed")
        try:
            shared_policy._validate_contextual_participants(  # noqa: SLF001
                case,
                frozen.contextual_participants,
            )
        except ValueError as exc:
            raise V13FrozenPolicyError(
                "frozen policy contextual participants changed"
            ) from exc


def _verify_review_evidence(
    manifest_path: Path,
    reviews: tuple[
        GraderReviewBatch,
        GraderReviewBatch,
        GraderReviewBatch | None,
    ],
) -> None:
    loaded: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not isinstance(loaded.get("sources"), list):
        raise V13FrozenPolicyError("primary-source evidence manifest is malformed")
    fields = set(PrimarySourceEvidence.model_fields)
    manifest = tuple(
        PrimarySourceEvidence.model_validate(
            {key: value for key, value in item.items() if key in fields}
        )
        for item in loaded["sources"]
        if isinstance(item, dict)
    )
    manifest_by_id = {item.evidence_id: item for item in manifest}
    for review in reviews:
        if review is None:
            continue
        for evidence in review.evidence:
            if manifest_by_id.get(evidence.evidence_id) != evidence:
                raise V13FrozenPolicyError(
                    "grader evidence differs from primary-source manifest"
                )


def _merge_evidence(
    batches: tuple[GraderReviewBatch, ...],
) -> tuple[PrimarySourceEvidence, ...]:
    by_id: dict[str, PrimarySourceEvidence] = {}
    for batch in batches:
        for item in batch.evidence:
            previous = by_id.get(item.evidence_id)
            if previous is not None and previous != item:
                raise V13FrozenPolicyError(
                    "grader evidence conflicts across frozen reviews"
                )
            by_id[item.evidence_id] = item
    return tuple(by_id[key] for key in sorted(by_id))


def _core_reference_sha256(case: GeneralizationCase) -> str:
    raw = json.dumps(
        asdict(case.reference),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "V12_GRADING_POLICY_SHA256",
    "V12_GRADING_SOURCE_SHA256",
    "V13FrozenPolicyError",
    "verify_shared_grader_sources",
    "verify_v13_frozen_policy",
]
