"""Qualified, source-bound claim frames for document extraction."""

from artana_evidence_api.document_extraction_support.claim_frames.arguments import (
    ClaimArgument,
    ClaimArgumentRole,
)
from artana_evidence_api.document_extraction_support.claim_frames.completeness import (
    BoundInventoryCompletenessReview,
    ClaimInventoryCompletenessReview,
    InventoryCompletenessDecision,
    MissingClaimRecoveryResult,
    bind_inventory_completeness_review,
    require_recovery_matches_review,
)
from artana_evidence_api.document_extraction_support.claim_frames.contracts import (
    ClaimFrame,
    ClaimQualifier,
    ClaimSourceMeasurement,
    EpistemicStatus,
    MeasurementFieldRole,
    Polarity,
    Qualifier,
    QualifierState,
    SourceEvidenceSpan,
    SourceMeasurementNumber,
    claim_frame_dedupe_identity,
    claim_frame_semantic_fingerprint,
    is_positive_projection_eligible,
    replace_claim_frame_projection,
)
from artana_evidence_api.document_extraction_support.claim_frames.inventory import (
    CLAIM_INVENTORY_SOURCE_LOCATOR,
    BoundClaimInventoryItem,
    ClaimFramingAbstentionReason,
    ClaimFramingDecision,
    ClaimInventoryBindingError,
    ClaimInventoryItem,
    bind_claim_inventory,
    merge_bound_claim_inventories,
)
from artana_evidence_api.document_extraction_support.claim_frames.normalization import (
    ClaimFrameNormalizationError,
    bind_claim_frame,
    normalize_claim_frame,
)
from artana_evidence_api.document_extraction_support.claim_frames.promotion_policy import (
    ClaimFramePromotionError,
    require_canonical_claim_promotion,
    require_claim_frame_promotion_preflight,
)
from artana_evidence_api.document_extraction_support.claim_frames.source_regions import (
    ClaimLocalSourceRegion,
    coalesce_long_sentence_chunks,
    derive_claim_local_source_region,
)

__all__ = [
    "CLAIM_INVENTORY_SOURCE_LOCATOR",
    "BoundClaimInventoryItem",
    "BoundInventoryCompletenessReview",
    "ClaimArgument",
    "ClaimArgumentRole",
    "ClaimFrame",
    "ClaimFrameNormalizationError",
    "ClaimFramePromotionError",
    "ClaimFramingAbstentionReason",
    "ClaimFramingDecision",
    "ClaimInventoryBindingError",
    "ClaimInventoryCompletenessReview",
    "ClaimInventoryItem",
    "ClaimLocalSourceRegion",
    "ClaimQualifier",
    "ClaimSourceMeasurement",
    "EpistemicStatus",
    "InventoryCompletenessDecision",
    "MeasurementFieldRole",
    "MissingClaimRecoveryResult",
    "Polarity",
    "Qualifier",
    "QualifierState",
    "SourceEvidenceSpan",
    "SourceMeasurementNumber",
    "bind_claim_frame",
    "bind_claim_inventory",
    "bind_inventory_completeness_review",
    "claim_frame_dedupe_identity",
    "claim_frame_semantic_fingerprint",
    "coalesce_long_sentence_chunks",
    "derive_claim_local_source_region",
    "is_positive_projection_eligible",
    "merge_bound_claim_inventories",
    "normalize_claim_frame",
    "replace_claim_frame_projection",
    "require_canonical_claim_promotion",
    "require_claim_frame_promotion_preflight",
    "require_recovery_matches_review",
]
