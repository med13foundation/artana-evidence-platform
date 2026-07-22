"""Load, freeze, and independently verify V5 grader artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.generalization.grading.contracts import (
    FrozenDualLanePolicy,
    GraderReviewBatch,
    PrimarySourceEvidence,
)
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    build_policy,
    verify_policy_artifact,
    write_policy,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.grading.config import (
        GradingArtifactPaths,
    )


def load_review(path: Path) -> GraderReviewBatch:
    return GraderReviewBatch.model_validate_json(path.read_text(encoding="utf-8"))


def freeze_policy(
    paths: GradingArtifactPaths,
    *,
    policy_id: str,
    frozen_at: str,
) -> FrozenDualLanePolicy:
    first = load_review(paths.first_review)
    second = load_review(paths.second_review)
    tiebreaker = (
        load_review(paths.tiebreaker_review)
        if paths.tiebreaker_review.exists()
        else None
    )
    _validate_review_evidence(paths.evidence, (first, second, tiebreaker))
    policy = build_policy(
        first,
        second,
        tiebreaker=tiebreaker,
        policy_id=policy_id,
        frozen_at=frozen_at,
    )
    write_policy(paths.policy, policy)
    return policy


def verify_frozen_policy(paths: GradingArtifactPaths) -> FrozenDualLanePolicy:
    first = load_review(paths.first_review)
    second = load_review(paths.second_review)
    tiebreaker = (
        load_review(paths.tiebreaker_review)
        if paths.tiebreaker_review.exists()
        else None
    )
    _validate_review_evidence(paths.evidence, (first, second, tiebreaker))
    return verify_policy_artifact(
        paths.policy,
        first,
        second,
        tiebreaker=tiebreaker,
    )


def write_contract_artifacts(
    *,
    packet_path: Path,
    schema_path: Path,
    packet: dict[str, object],
) -> None:
    packet_path.parent.mkdir(parents=True, exist_ok=True)
    packet_path.write_text(
        json.dumps(packet, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    schema_path.write_text(
        json.dumps(GraderReviewBatch.model_json_schema(), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def _validate_review_evidence(
    manifest_path: Path,
    reviews: tuple[
        GraderReviewBatch,
        GraderReviewBatch,
        GraderReviewBatch | None,
    ],
) -> None:
    manifest = _load_evidence_manifest(manifest_path)
    manifest_by_id = {item.evidence_id: item for item in manifest}
    for review in reviews:
        if review is None:
            continue
        for evidence in review.evidence:
            if manifest_by_id.get(evidence.evidence_id) != evidence:
                raise ValueError(
                    "grader evidence differs from the frozen primary-source manifest"
                )


def _load_evidence_manifest(path: Path) -> tuple[PrimarySourceEvidence, ...]:
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not isinstance(loaded.get("sources"), list):
        raise TypeError("primary-source evidence manifest is malformed")
    fields = set(PrimarySourceEvidence.model_fields)
    return tuple(
        PrimarySourceEvidence.model_validate(
            {key: value for key, value in item.items() if key in fields}
        )
        for item in loaded["sources"]
        if isinstance(item, dict)
    )


__all__ = [
    "freeze_policy",
    "load_review",
    "verify_frozen_policy",
    "write_contract_artifacts",
]
