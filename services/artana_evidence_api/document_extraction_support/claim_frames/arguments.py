"""Source-bound n-ary argument contracts for biomedical claims."""

from __future__ import annotations

from enum import Enum

from artana_evidence_api.document_extraction_support.claim_frames.event_types import (
    ClaimEventRole,
)
from pydantic import BaseModel, ConfigDict, Field


class ClaimArgumentRole(str, Enum):
    """Closed source-local role assigned before graph endpoints are selected."""

    INTERVENTION = "INTERVENTION"
    CONDITION = "CONDITION"
    POPULATION = "POPULATION"
    VARIANT = "VARIANT"
    OUTCOME = "OUTCOME"
    COMPARATOR = "COMPARATOR"
    TIMEFRAME = "TIMEFRAME"
    STUDY_DESIGN = "STUDY_DESIGN"
    TREATMENT_SETTING = "TREATMENT_SETTING"
    GENE_OR_PROTEIN = "GENE_OR_PROTEIN"
    CHEMICAL_OR_DRUG = "CHEMICAL_OR_DRUG"
    BIOMARKER = "BIOMARKER"
    EXPOSURE = "EXPOSURE"
    BIOLOGICAL_PROCESS = "BIOLOGICAL_PROCESS"
    ANATOMY = "ANATOMY"
    MEASUREMENT = "MEASUREMENT"
    OTHER_ENTITY = "OTHER_ENTITY"


class ClaimArgument(BaseModel):
    """One exact source span with an agent-assigned biomedical role."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    role: ClaimArgumentRole = Field(..., strict=False)
    event_role: ClaimEventRole = Field(..., strict=False)
    exact_span: str = Field(..., min_length=1, max_length=1000)
    role_rationale: str = Field(..., min_length=1, max_length=1000)


__all__ = ["ClaimArgument", "ClaimArgumentRole", "ClaimEventRole"]
