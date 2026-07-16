"""Closed contracts for agent-reviewed claim-inventory completeness."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from artana_evidence_api.document_extraction_support.claim_frames.inventory import (
    BoundClaimInventoryItem,
    ClaimInventoryBindingError,
    ClaimInventoryItem,
    bind_claim_inventory,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InventoryCompletenessDecision(str, Enum):
    """Closed decision returned by the inventory-review agent."""

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class ClaimInventoryCompletenessReview(BaseModel):
    """Agent judgment over one frozen chunk and its complete inventory."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    decision: InventoryCompletenessDecision = Field(..., strict=False)
    missing_claims: tuple[ClaimInventoryItem, ...] = Field(
        default=(),
        max_length=64,
    )
    review_rationale: str = Field(..., min_length=1, max_length=4000)

    @field_validator("missing_claims", mode="before")
    @classmethod
    def restore_missing_claim_tuple(cls, value: object) -> object:
        """Freeze the JSON array after schema validation."""

        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_decision_payload(self) -> ClaimInventoryCompletenessReview:
        """Require missing descriptors only for an incomplete decision."""

        if self.decision is InventoryCompletenessDecision.COMPLETE:
            if self.missing_claims:
                raise ValueError("COMPLETE cannot include missing claims")
        elif not self.missing_claims:
            raise ValueError("INCOMPLETE requires at least one missing claim")
        return self


class MissingClaimRecoveryResult(BaseModel):
    """One missing-only recovery inventory returned by the agent."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    claims: tuple[ClaimInventoryItem, ...] = Field(..., min_length=1, max_length=64)

    @field_validator("claims", mode="before")
    @classmethod
    def restore_claim_tuple(cls, value: object) -> object:
        """Freeze the JSON array after schema validation."""

        return tuple(value) if isinstance(value, list) else value


@dataclass(frozen=True, slots=True)
class BoundInventoryCompletenessReview:
    """A completeness decision whose missing descriptors bind to source."""

    decision: InventoryCompletenessDecision
    missing_claims: tuple[BoundClaimInventoryItem, ...]
    review_rationale: str


def bind_inventory_completeness_review(
    review: ClaimInventoryCompletenessReview,
    *,
    source_text: str,
    source_sha256: str,
    chunk_index: int,
    source_start_offset: int,
    current_inventory: tuple[BoundClaimInventoryItem, ...],
) -> BoundInventoryCompletenessReview:
    """Bind missing descriptors and reject claims already in the inventory."""

    missing_claims = bind_claim_inventory(
        review.missing_claims,
        source_text=source_text,
        source_sha256=source_sha256,
        chunk_index=chunk_index,
        source_start_offset=source_start_offset,
    )
    current_ids = {claim.inventory_id for claim in current_inventory}
    duplicated_ids = current_ids.intersection(
        claim.inventory_id for claim in missing_claims
    )
    if duplicated_ids:
        raise ClaimInventoryBindingError(
            "inventory completeness review marked an existing claim as missing",
        )
    return BoundInventoryCompletenessReview(
        decision=review.decision,
        missing_claims=missing_claims,
        review_rationale=review.review_rationale,
    )


def require_recovery_matches_review(
    *,
    recovered_claims: tuple[BoundClaimInventoryItem, ...],
    reviewed_missing_claims: tuple[BoundClaimInventoryItem, ...],
) -> None:
    """Require recovery to return exactly the claims named by the review agent."""

    recovered_ids = {claim.inventory_id for claim in recovered_claims}
    reviewed_ids = {claim.inventory_id for claim in reviewed_missing_claims}
    if recovered_ids != reviewed_ids:
        raise ClaimInventoryBindingError(
            "missing-claim recovery did not exactly match the completeness review",
        )


__all__ = [
    "BoundInventoryCompletenessReview",
    "ClaimInventoryCompletenessReview",
    "InventoryCompletenessDecision",
    "MissingClaimRecoveryResult",
    "bind_inventory_completeness_review",
    "require_recovery_matches_review",
]
