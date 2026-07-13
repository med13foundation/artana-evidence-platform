"""Diagnostic monotonic fitter for deterministic ranking weights."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from artana_evidence_api.evidence_selection.ranking.contracts import (
    CalibratedRankingProbability,
    DeterministicRankingWeight,
    RankingCalibrationIdentity,
    ReviewRankingCalibrationProtocol,
)


@dataclass(frozen=True, slots=True)
class DiagnosticCalibrationTrainingSample:
    """One training-only adjudicated outcome for a deterministic ranking weight."""

    research_question_id: str
    operational_ranking: DeterministicRankingWeight
    outcome_positive: bool


@dataclass(frozen=True, slots=True)
class MonotonicCalibrationPoint:
    """One fitted upper-bound/probability block."""

    upper_weight: float
    probability: float
    sample_count: int


@dataclass(frozen=True, slots=True)
class DiagnosticMonotonicCalibrationArtifact:
    """A training-only mapping that cannot support a production claim."""

    schema_version: str
    calibration_status: str
    identity: RankingCalibrationIdentity
    training_set_sha256: str
    partition_manifest_sha256: str
    held_out_protocol: str
    points: tuple[MonotonicCalibrationPoint, ...]


def fit_diagnostic_monotonic_calibrator(
    *,
    samples: tuple[DiagnosticCalibrationTrainingSample, ...],
    protocol: ReviewRankingCalibrationProtocol,
) -> DiagnosticMonotonicCalibrationArtifact:
    """Fit an isotonic mapping on exactly the frozen training partition."""

    if not samples:
        msg = "diagnostic calibration requires at least one training sample"
        raise ValueError(msg)
    identity = protocol.identity
    _require_matching_policy(samples=samples, identity=identity)
    _require_frozen_training_partition(samples=samples, protocol=protocol)
    training_set_sha256 = calibration_training_set_sha256(samples)
    if training_set_sha256 != protocol.training_set_sha256:
        msg = "calibration training samples do not match the frozen training-set hash"
        raise ValueError(msg)
    grouped = _group_samples_by_weight(samples)
    blocks: list[list[float | int]] = [
        [weight, positive_count, sample_count]
        for weight, positive_count, sample_count in grouped
    ]
    index = 0
    while index < len(blocks) - 1:
        if _block_probability(blocks[index]) <= _block_probability(blocks[index + 1]):
            index += 1
            continue
        left = blocks[index]
        right = blocks[index + 1]
        blocks[index : index + 2] = [
            [
                right[0],
                int(left[1]) + int(right[1]),
                int(left[2]) + int(right[2]),
            ],
        ]
        index = max(0, index - 1)
    return DiagnosticMonotonicCalibrationArtifact(
        schema_version="evidence_selection_ranking_calibrator.v1",
        calibration_status="diagnostic",
        identity=identity,
        training_set_sha256=training_set_sha256,
        partition_manifest_sha256=protocol.partition_manifest_sha256,
        held_out_protocol=protocol.held_out_protocol,
        points=tuple(
            MonotonicCalibrationPoint(
                upper_weight=float(block[0]),
                probability=round(_block_probability(block), 6),
                sample_count=int(block[2]),
            )
            for block in blocks
        ),
    )


def predict_diagnostic_probability(
    *,
    artifact: DiagnosticMonotonicCalibrationArtifact,
    operational_ranking: DeterministicRankingWeight,
) -> CalibratedRankingProbability:
    """Apply a diagnostic mapping with explicit saturation at fitted boundaries."""

    _require_weight_identity(
        operational_ranking=operational_ranking,
        identity=artifact.identity,
    )
    point = next(
        (
            candidate
            for candidate in artifact.points
            if operational_ranking.value <= candidate.upper_weight
        ),
        artifact.points[-1],
    )
    return CalibratedRankingProbability(
        value=point.probability,
        calibration_status="diagnostic",
        identity=artifact.identity,
        training_set_sha256=artifact.training_set_sha256,
        partition_manifest_sha256=artifact.partition_manifest_sha256,
        held_out_protocol=artifact.held_out_protocol,
    )


def _group_samples_by_weight(
    samples: tuple[DiagnosticCalibrationTrainingSample, ...],
) -> tuple[tuple[float, int, int], ...]:
    grouped: dict[float, list[bool]] = {}
    for sample in samples:
        grouped.setdefault(sample.operational_ranking.value, []).append(
            sample.outcome_positive,
        )
    return tuple(
        (weight, sum(1 for outcome in outcomes if outcome), len(outcomes))
        for weight, outcomes in sorted(grouped.items())
    )


def _block_probability(block: list[float | int]) -> float:
    return int(block[1]) / int(block[2])


def _require_matching_policy(
    *,
    samples: tuple[DiagnosticCalibrationTrainingSample, ...],
    identity: RankingCalibrationIdentity,
) -> None:
    for sample in samples:
        _require_weight_identity(
            operational_ranking=sample.operational_ranking,
            identity=identity,
        )


def _require_frozen_training_partition(
    *,
    samples: tuple[DiagnosticCalibrationTrainingSample, ...],
    protocol: ReviewRankingCalibrationProtocol,
) -> None:
    observed_ids = {sample.research_question_id for sample in samples}
    training_ids = set(protocol.training_research_question_ids)
    held_out_ids = set(protocol.held_out_research_question_ids)
    leaked_ids = sorted(observed_ids.intersection(held_out_ids))
    if leaked_ids:
        msg = (
            "calibration training samples contain held-out research questions: "
            f"{', '.join(leaked_ids)}"
        )
        raise ValueError(msg)
    if observed_ids != training_ids:
        missing = sorted(training_ids - observed_ids)
        unknown = sorted(observed_ids - training_ids)
        details = []
        if missing:
            details.append(f"missing={','.join(missing)}")
        if unknown:
            details.append(f"unknown={','.join(unknown)}")
        msg = (
            "calibration training samples must exactly match the frozen training "
            f"research-question partition ({'; '.join(details)})"
        )
        raise ValueError(msg)


def _require_weight_identity(
    *,
    operational_ranking: DeterministicRankingWeight,
    identity: RankingCalibrationIdentity,
) -> None:
    if (
        operational_ranking.policy_id != identity.input_policy_id
        or operational_ranking.policy_version != identity.input_policy_version
        or operational_ranking.mapping_version != identity.input_mapping_version
    ):
        msg = "calibration input weight does not match the fitted policy identity"
        raise ValueError(msg)


def calibration_training_set_sha256(
    samples: tuple[DiagnosticCalibrationTrainingSample, ...],
) -> str:
    """Return an order-independent digest for frozen calibration samples."""

    payload = sorted(
        (
        {
            "research_question_id": sample.research_question_id,
            "operational_ranking": sample.operational_ranking.model_dump(mode="json"),
            "outcome_positive": sample.outcome_positive,
        }
        for sample in samples
        ),
        key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
    )
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "DiagnosticCalibrationTrainingSample",
    "DiagnosticMonotonicCalibrationArtifact",
    "MonotonicCalibrationPoint",
    "calibration_training_set_sha256",
    "fit_diagnostic_monotonic_calibrator",
    "predict_diagnostic_probability",
]
