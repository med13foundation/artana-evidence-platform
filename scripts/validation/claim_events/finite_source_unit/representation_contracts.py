"""Closed categorical output for TG-04 representation adjudication."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RepresentationDecision(StrEnum):
    """Scientific relationship between one candidate and sealed expert event."""

    ACCEPTABLE_ALTERNATE = "ACCEPTABLE_ALTERNATE"
    PARTIAL = "PARTIAL"
    CONTRADICTS = "CONTRADICTS"
    UNRELATED = "UNRELATED"
    ABSTAIN = "ABSTAIN"


class RepresentationSourceSupport(StrEnum):
    """Source-only support for either representation."""

    ENTAILED = "ENTAILED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT = "INSUFFICIENT"
    ABSTAIN = "ABSTAIN"


class RepresentationAxisDecision(StrEnum):
    """Categorical comparison of one material scientific dimension."""

    PRESERVED = "PRESERVED"
    COMPATIBLE_REFINEMENT = "COMPATIBLE_REFINEMENT"
    MATERIAL_MISMATCH = "MATERIAL_MISMATCH"
    ABSTAIN = "ABSTAIN"


class RepresentationAdjudicationOutput(BaseModel):
    """One model-authored comparison with no numeric judgment fields."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    decision: RepresentationDecision = Field(..., strict=False)
    expert_source_support: RepresentationSourceSupport = Field(..., strict=False)
    candidate_source_support: RepresentationSourceSupport = Field(..., strict=False)
    trigger_alignment: RepresentationAxisDecision = Field(..., strict=False)
    direction_alignment: RepresentationAxisDecision = Field(..., strict=False)
    participant_alignment: RepresentationAxisDecision = Field(..., strict=False)
    causal_role_alignment: RepresentationAxisDecision = Field(..., strict=False)
    polarity_alignment: RepresentationAxisDecision = Field(..., strict=False)
    epistemic_alignment: RepresentationAxisDecision = Field(..., strict=False)
    evidence_spans: tuple[str, ...] = Field(..., min_length=1, max_length=12)
    reasoning: str = Field(..., min_length=1, max_length=4000)
    falsification_condition: str = Field(..., min_length=1, max_length=4000)

    @field_validator("evidence_spans", mode="before")
    @classmethod
    def freeze_evidence_spans(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("evidence_spans")
    @classmethod
    def require_unique_nonempty_spans(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not span.strip() for span in value):
            raise ValueError("representation evidence spans must be nonempty")
        if len(set(value)) != len(value):
            raise ValueError("representation evidence spans must be unique")
        return value

    @model_validator(mode="after")
    def require_decision_axis_consistency(self) -> RepresentationAdjudicationOutput:
        axes = self.axes
        both_entailed = (
            self.expert_source_support is RepresentationSourceSupport.ENTAILED
            and self.candidate_source_support is RepresentationSourceSupport.ENTAILED
        )
        if self.decision is RepresentationDecision.ACCEPTABLE_ALTERNATE:
            if not both_entailed:
                raise ValueError("acceptable alternates require both claims entailed")
            if any(
                axis
                not in {
                    RepresentationAxisDecision.PRESERVED,
                    RepresentationAxisDecision.COMPATIBLE_REFINEMENT,
                }
                for axis in axes
            ):
                raise ValueError("acceptable alternates cannot contain unresolved axes")
        elif self.decision is RepresentationDecision.PARTIAL:
            if not both_entailed:
                raise ValueError("partial representations require both claims entailed")
            if RepresentationAxisDecision.MATERIAL_MISMATCH not in axes:
                raise ValueError("partial representations require a material mismatch")
        elif self.decision is RepresentationDecision.CONTRADICTS:
            contradiction_evidence = (
                self.candidate_source_support
                is RepresentationSourceSupport.CONTRADICTED
                or self.direction_alignment
                is RepresentationAxisDecision.MATERIAL_MISMATCH
                or self.polarity_alignment
                is RepresentationAxisDecision.MATERIAL_MISMATCH
            )
            if not contradiction_evidence:
                raise ValueError(
                    "contradiction requires support, direction, or polarity conflict"
                )
        elif self.decision is RepresentationDecision.UNRELATED:
            if (
                self.participant_alignment
                is not RepresentationAxisDecision.MATERIAL_MISMATCH
            ):
                raise ValueError(
                    "unrelated representations require participant mismatch"
                )
        elif RepresentationAxisDecision.ABSTAIN not in axes and (
            self.expert_source_support is not RepresentationSourceSupport.ABSTAIN
            and self.candidate_source_support is not RepresentationSourceSupport.ABSTAIN
        ):
            raise ValueError("ABSTAIN requires an unresolved support or alignment axis")
        return self

    @property
    def axes(self) -> tuple[RepresentationAxisDecision, ...]:
        """Return all comparison axes in stable protocol order."""

        return (
            self.trigger_alignment,
            self.direction_alignment,
            self.participant_alignment,
            self.causal_role_alignment,
            self.polarity_alignment,
            self.epistemic_alignment,
        )


__all__ = [
    "RepresentationAdjudicationOutput",
    "RepresentationAxisDecision",
    "RepresentationDecision",
    "RepresentationSourceSupport",
]
