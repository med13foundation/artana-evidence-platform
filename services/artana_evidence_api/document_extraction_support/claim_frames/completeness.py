"""Closed contracts for agent-reviewed claim-inventory completeness."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from artana_evidence_api.document_extraction_support.claim_frames.inventory import (
    BoundClaimInventoryItem,
    ClaimInventoryBindingDisposition,
    ClaimInventoryBindingRejection,
    ClaimInventoryItem,
    bind_claim_inventory_items,
    build_claim_inventory_binding_rejection,
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
        if any(not claim.claim_kind.relation_eligible for claim in self.missing_claims):
            raise ValueError("missing claims must be scientific findings or hypotheses")
        return self


class MissingClaimRecoveryDisposition(str, Enum):
    """Closed source-only decision for one reviewed missing descriptor."""

    RECOVER_EXPLICIT_CLAIM = "RECOVER_EXPLICIT_CLAIM"
    EXCLUDE_PROCEDURAL_METHOD = "EXCLUDE_PROCEDURAL_METHOD"
    EXCLUDE_NOT_EXPLICIT = "EXCLUDE_NOT_EXPLICIT"
    ABSTAIN = "ABSTAIN"


class MissingClaimRecoveryDecision(BaseModel):
    """Categorical adjudication of one already source-bound descriptor."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    decision: MissingClaimRecoveryDisposition = Field(..., strict=False)
    decision_rationale: str = Field(..., min_length=1, max_length=2000)


@dataclass(frozen=True, slots=True)
class BoundInventoryCompletenessReview:
    """A completeness decision whose missing descriptors bind to source."""

    decision: InventoryCompletenessDecision
    missing_claims: tuple[BoundClaimInventoryItem, ...]
    binding_rejections: tuple[ClaimInventoryBindingRejection, ...]
    review_rationale: str


def bind_inventory_completeness_review(
    review: ClaimInventoryCompletenessReview,
    *,
    source_text: str,
    source_sha256: str,
    chunk_index: int,
    source_start_offset: int,
    current_inventory: tuple[BoundClaimInventoryItem, ...],
    excluded_inventory: tuple[BoundClaimInventoryItem, ...] = (),
) -> BoundInventoryCompletenessReview:
    """Bind missing descriptors and reject already adjudicated identities."""

    binding_result = bind_claim_inventory_items(
        review.missing_claims,
        source_text=source_text,
        source_sha256=source_sha256,
        chunk_index=chunk_index,
        source_start_offset=source_start_offset,
    )
    adjudicated_ids = {
        claim.inventory_id for claim in (*current_inventory, *excluded_inventory)
    }
    accepted: list[BoundClaimInventoryItem] = []
    duplicate_rejections: list[ClaimInventoryBindingRejection] = []
    for claim in binding_result.accepted:
        if claim.inventory_id not in adjudicated_ids:
            accepted.append(claim)
            continue
        batch_index = review.missing_claims.index(claim.item)
        duplicate_rejections.append(
            build_claim_inventory_binding_rejection(
                batch_index=batch_index,
                item=claim.item,
                source_sha256=source_sha256,
                chunk_index=chunk_index,
                disposition=(ClaimInventoryBindingDisposition.DUPLICATE_SEMANTIC_CLAIM),
                validation_evidence=(
                    "inventory completeness review repeated an adjudicated claim"
                ),
            ),
        )
    rejections = tuple(
        sorted(
            (*binding_result.rejected, *duplicate_rejections),
            key=lambda rejection: rejection.batch_index,
        ),
    )
    return BoundInventoryCompletenessReview(
        decision=review.decision,
        missing_claims=tuple(accepted),
        binding_rejections=rejections,
        review_rationale=review.review_rationale,
    )


__all__ = [
    "BoundInventoryCompletenessReview",
    "ClaimInventoryCompletenessReview",
    "InventoryCompletenessDecision",
    "MissingClaimRecoveryDecision",
    "MissingClaimRecoveryDisposition",
    "bind_inventory_completeness_review",
]
