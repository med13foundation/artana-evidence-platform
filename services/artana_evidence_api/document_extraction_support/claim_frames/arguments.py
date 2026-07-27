"""Source-bound n-ary argument contracts for biomedical claims."""

from __future__ import annotations

from enum import Enum
from typing import Final

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


#: How long an argument's source span may be.
#:
#: The framing stage must be able to restate any span the inventory stage can
#: produce, because `_require_inventory_consistency` accepts a framed relation
#: only when its endpoints are string-equal to an inventory argument's span.
#: The framing schema capped its endpoints at 50 while this allowed 1000, so an
#: argument longer than 50 characters could not be framed at all -- not by a
#: better model, not on retry.  Recorded framing traffic showed 11 of 56
#: argument spans over the cap (longest 123) and 10 of 62 endpoints sitting
#: exactly on it, which is what truncation looks like from the outside.
#:
#: Both limits now read from here, and a test pins them equal, so the two
#: stages cannot silently disagree again.
ARGUMENT_SPAN_MAX_LENGTH: Final = 1000


class ClaimArgument(BaseModel):
    """One exact source span with an agent-assigned biomedical role."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    role: ClaimArgumentRole = Field(..., strict=False)
    event_role: ClaimEventRole = Field(..., strict=False)
    exact_span: str = Field(..., min_length=1, max_length=ARGUMENT_SPAN_MAX_LENGTH)
    role_rationale: str = Field(..., min_length=1, max_length=1000)


__all__ = [
    "ARGUMENT_SPAN_MAX_LENGTH",
    "ClaimArgument",
    "ClaimArgumentRole",
    "ClaimEventRole",
]
