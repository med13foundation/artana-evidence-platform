"""Fail-closed contracts for deterministic ranking and calibrated probability."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

ReviewRankingSourceKind = Literal["proposal", "review_item"]
ReviewRankingOutcome = Literal["positive", "negative", "abstained"]

_IDENTIFIER_PATTERN = r"^[a-z][a-z0-9_.:-]*$"
_SHA256_PATTERN = r"^[a-f0-9]{64}$"


def _required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        msg = f"{field_name} must not be blank"
        raise ValueError(msg)
    return normalized


def _normalized_string_tuple(value: object) -> object:
    return tuple(value) if isinstance(value, list) else value


class RankingCategoricalInput(BaseModel):
    """One atomic categorical input consumed by a ranking policy."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    field: str = Field(pattern=_IDENTIFIER_PATTERN)
    value: str = Field(pattern=_IDENTIFIER_PATTERN)


class DeterministicRankingWeight(BaseModel):
    """An operational ranking weight derived only from categorical findings."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        json_schema_extra={"x-artana-numeric-origin": "deterministic_policy"},
    )

    origin: Literal["deterministic_policy"] = "deterministic_policy"
    value: float = Field(ge=0.0)
    policy_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    policy_version: str = Field(pattern=_IDENTIFIER_PATTERN)
    mapping_version: str = Field(pattern=_IDENTIFIER_PATTERN)
    categorical_inputs: tuple[RankingCategoricalInput, ...] = Field(min_length=1)
    caps: tuple[str, ...] = ()
    vetoes: tuple[str, ...] = ()
    blocking_categories: tuple[str, ...] = ()

    @field_validator(
        "categorical_inputs",
        "caps",
        "vetoes",
        "blocking_categories",
        mode="before",
    )
    @classmethod
    def _accept_json_arrays(cls, value: object) -> object:
        return _normalized_string_tuple(value)

    @field_validator("value")
    @classmethod
    def _require_finite_weight(cls, value: float) -> float:
        if not math.isfinite(value):
            msg = "deterministic ranking weight must be finite"
            raise ValueError(msg)
        return value

    @field_validator("caps", "vetoes", "blocking_categories")
    @classmethod
    def _normalize_policy_labels(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(
            _required_text(item, field_name="ranking policy label") for item in value
        )
        if len(set(normalized)) != len(normalized):
            msg = "ranking policy labels must be unique"
            raise ValueError(msg)
        return normalized

    @model_validator(mode="after")
    def _categorical_input_fields_must_be_unique(
        self,
    ) -> DeterministicRankingWeight:
        fields = tuple(item.field for item in self.categorical_inputs)
        if len(set(fields)) != len(fields):
            msg = "deterministic ranking categorical input fields must be unique"
            raise ValueError(msg)
        return self


class RankingCalibrationIdentity(BaseModel):
    """Complete version identity for one fitted calibration mapping."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    input_policy_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    input_policy_version: str = Field(pattern=_IDENTIFIER_PATTERN)
    input_mapping_version: str = Field(pattern=_IDENTIFIER_PATTERN)
    categorical_schema_version: str = Field(pattern=_IDENTIFIER_PATTERN)
    selector_model_id: str = Field(min_length=1)
    selector_prompt_version: str = Field(pattern=_IDENTIFIER_PATTERN)
    objective_schema_version: str = Field(pattern=_IDENTIFIER_PATTERN)
    corpus_version: str = Field(pattern=_IDENTIFIER_PATTERN)
    calibration_algorithm: str = Field(pattern=_IDENTIFIER_PATTERN)
    calibration_version: str = Field(pattern=_IDENTIFIER_PATTERN)


class CalibratedRankingProbability(BaseModel):
    """A candidate probability emitted by one versioned calibration mapping.

    Validation is an outcome of the held-out gate. Input artifacts cannot grant
    that status to themselves.
    """

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        json_schema_extra={"x-artana-numeric-origin": "calibration_model"},
    )

    origin: Literal["calibration_model"] = "calibration_model"
    value: float = Field(ge=0.0, le=1.0)
    calibration_status: Literal["diagnostic"] = "diagnostic"
    identity: RankingCalibrationIdentity
    training_set_sha256: str = Field(pattern=_SHA256_PATTERN)
    partition_manifest_sha256: str = Field(pattern=_SHA256_PATTERN)
    held_out_protocol: str = Field(min_length=1)

    @field_validator("value")
    @classmethod
    def _require_finite_probability(cls, value: float) -> float:
        if not math.isfinite(value):
            msg = "calibrated probability must be finite"
            raise ValueError(msg)
        return value


class ReviewRankingCalibrationProtocol(BaseModel):
    """Predeclared research-question partitions for calibration validation."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    identity: RankingCalibrationIdentity
    partition_manifest_sha256: str = Field(pattern=_SHA256_PATTERN)
    training_set_sha256: str = Field(pattern=_SHA256_PATTERN)
    held_out_set_sha256: str = Field(pattern=_SHA256_PATTERN)
    training_research_question_ids: tuple[str, ...] = Field(min_length=1)
    held_out_research_question_ids: tuple[str, ...] = Field(min_length=1)
    independent_expert_labels: bool
    held_out_protocol: str = Field(min_length=1)
    producer_signature: str | None = Field(default=None, pattern=_SHA256_PATTERN)

    @field_validator(
        "training_research_question_ids",
        "held_out_research_question_ids",
        mode="before",
    )
    @classmethod
    def _accept_json_question_arrays(cls, value: object) -> object:
        return _normalized_string_tuple(value)

    @field_validator(
        "training_research_question_ids",
        "held_out_research_question_ids",
    )
    @classmethod
    def _normalize_question_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(
            _required_text(item, field_name="research question ID") for item in value
        )
        if len(set(normalized)) != len(normalized):
            msg = "calibration research question IDs must be unique within a partition"
            raise ValueError(msg)
        return normalized

    @model_validator(mode="after")
    def _partitions_must_be_disjoint(self) -> ReviewRankingCalibrationProtocol:
        overlap = set(self.training_research_question_ids).intersection(
            self.held_out_research_question_ids,
        )
        if overlap:
            msg = (
                "calibration training and held-out research-question partitions "
                f"must be disjoint: {', '.join(sorted(overlap))}"
            )
            raise ValueError(msg)
        return self


class ReviewRankingCalibrationDecision(BaseModel):
    """One expert outcome paired with governed ranking outputs."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    source_kind: ReviewRankingSourceKind
    item_id: str = Field(min_length=1)
    research_question_id: str = Field(min_length=1)
    operational_ranking: DeterministicRankingWeight
    calibrated_probability: CalibratedRankingProbability | None = None
    outcome: ReviewRankingOutcome
    reviewer_id: str | None = None
    goal: str | None = None
    evidence_shape: str | None = None

    @field_validator("item_id", "research_question_id")
    @classmethod
    def _normalize_required_ids(cls, value: str, info: ValidationInfo) -> str:
        return _required_text(value, field_name=info.field_name or "identifier")

    @model_validator(mode="after")
    def _calibration_must_match_operational_policy(
        self,
    ) -> ReviewRankingCalibrationDecision:
        probability = self.calibrated_probability
        if probability is None:
            return self
        identity = probability.identity
        operational = self.operational_ranking
        if (
            identity.input_policy_id != operational.policy_id
            or identity.input_policy_version != operational.policy_version
            or identity.input_mapping_version != operational.mapping_version
        ):
            msg = "calibrated probability identity must match operational ranking policy"
            raise ValueError(msg)
        return self


class ReviewRankingCalibrationGateThresholds(BaseModel):
    """Fail-closed thresholds for a production ranking/calibration claim."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    min_sample_count: int = Field(default=10, ge=1)
    max_expected_calibration_error: float = Field(default=0.05, ge=0.0, le=1.0)
    min_roc_auc: float = Field(default=0.7, ge=0.0, le=1.0)
    min_mean_operational_weight_separation: float = Field(default=0.1, ge=0.0)
    min_distinct_goals: int = Field(default=3, ge=0)
    min_distinct_evidence_shapes: int = Field(default=3, ge=0)
    min_training_research_questions: int = Field(default=12, ge=1)
    min_held_out_research_questions: int = Field(default=8, ge=1)
    min_observed_held_out_research_questions: int = Field(default=8, ge=1)
    require_calibrated_probabilities: bool = True
    require_authenticated_protocol: bool = True
    require_independent_expert_labels: bool = True
    require_reviewer_ids: bool = True
    require_adjudication_note: bool = True
    require_positive_and_negative_outcomes: bool = True
    require_proposal_and_review_item_sources: bool = True
    require_positive_and_negative_per_source: bool = True
    bin_count: int = Field(default=10, ge=1)


class ReviewRankingCalibrationStudyInput(BaseModel):
    """Strict v2 study envelope separating rank from calibrated probability."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_review_ranking_calibration.v2"]
    study_id: str
    decisions: tuple[ReviewRankingCalibrationDecision, ...]
    calibration_protocol: ReviewRankingCalibrationProtocol | None = None
    adjudication_note: str | None = None
    description: str | None = Field(default=None, min_length=1)

    @field_validator("decisions", mode="before")
    @classmethod
    def _accept_json_decision_array(cls, value: object) -> object:
        return _normalized_string_tuple(value)

    @field_validator("study_id")
    @classmethod
    def _normalize_study_id(cls, value: str) -> str:
        return _required_text(value, field_name="study_id")

    @model_validator(mode="after")
    def _probabilities_must_match_protocol(
        self,
    ) -> ReviewRankingCalibrationStudyInput:
        probabilities = tuple(
            decision.calibrated_probability
            for decision in self.decisions
            if decision.calibrated_probability is not None
        )
        if not probabilities:
            return self
        protocol = self.calibration_protocol
        if protocol is None:
            msg = "calibrated probabilities require a calibration_protocol"
            raise ValueError(msg)
        for probability in probabilities:
            if (
                probability.identity != protocol.identity
                or probability.training_set_sha256 != protocol.training_set_sha256
                or probability.partition_manifest_sha256
                != protocol.partition_manifest_sha256
                or probability.held_out_protocol != protocol.held_out_protocol
            ):
                msg = "calibrated probability provenance must match study protocol"
                raise ValueError(msg)
        return self


__all__ = [
    "CalibratedRankingProbability",
    "DeterministicRankingWeight",
    "RankingCalibrationIdentity",
    "RankingCategoricalInput",
    "ReviewRankingCalibrationDecision",
    "ReviewRankingCalibrationGateThresholds",
    "ReviewRankingCalibrationProtocol",
    "ReviewRankingCalibrationStudyInput",
    "ReviewRankingOutcome",
    "ReviewRankingSourceKind",
]
