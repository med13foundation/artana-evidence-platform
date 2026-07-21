"""Offline evaluator contracts for source-general claim verification."""

from scripts.validation.source_general_claim_verification.agreement import (
    AgreementReport,
    build_disagreement_requests,
    calculate_reviewer_agreement,
    reliability_gate,
)
from scripts.validation.source_general_claim_verification.contracts import (
    CorpusArtifact,
    ExperimentCaseResult,
    ExposedScope,
    FrozenPacketSet,
    FrozenReferencePacket,
    ReviewerPacketBatch,
    SourceDocument,
)
from scripts.validation.source_general_claim_verification.corpus import (
    load_corpus,
    validate_packet_batch,
    validate_reference_set,
)
from scripts.validation.source_general_claim_verification.hashing import (
    canonical_sha256,
)
from scripts.validation.source_general_claim_verification.malformed import (
    generate_malformed_variants,
)
from scripts.validation.source_general_claim_verification.metrics import (
    ExperimentMetrics,
    calculate_experiment_metrics,
)
from scripts.validation.source_general_claim_verification.packet_builder import (
    PacketConstructionResult,
    construct_reference_set,
)
from scripts.validation.source_general_claim_verification.preregistration import (
    ExperimentPreregistration,
    freeze_preregistration,
)

__all__ = [
    "AgreementReport",
    "CorpusArtifact",
    "ExperimentCaseResult",
    "ExperimentMetrics",
    "ExperimentPreregistration",
    "ExposedScope",
    "FrozenPacketSet",
    "FrozenReferencePacket",
    "PacketConstructionResult",
    "ReviewerPacketBatch",
    "SourceDocument",
    "build_disagreement_requests",
    "calculate_experiment_metrics",
    "calculate_reviewer_agreement",
    "canonical_sha256",
    "construct_reference_set",
    "freeze_preregistration",
    "generate_malformed_variants",
    "load_corpus",
    "reliability_gate",
    "validate_packet_batch",
    "validate_reference_set",
]
