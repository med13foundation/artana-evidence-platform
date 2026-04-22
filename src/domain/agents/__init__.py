"""
Domain layer for AI agents.

This module defines the contracts, contexts, model specifications, and port
interfaces for AI agents. Contracts are the architecture - they define what
agents can output, how decisions are justified, and when humans must intervene.
"""

from src.domain.agents.contexts.base import BaseAgentContext
from src.domain.agents.contexts.content_enrichment_context import (
    ContentEnrichmentContext,
)
from src.domain.agents.contexts.entity_recognition_context import (
    EntityRecognitionContext,
)
from src.domain.agents.contexts.extraction_context import ExtractionContext
from src.domain.agents.contexts.extraction_policy_context import (
    ExtractionPolicyContext,
)
from src.domain.agents.contexts.graph_connection_context import (
    GraphConnectionContext,
)
from src.domain.agents.contexts.graph_search_context import GraphSearchContext
from src.domain.agents.contexts.query_context import QueryGenerationContext
from src.domain.agents.contracts.base import (
    AgentDecision,
    BaseAgentContract,
    EvidenceItem,
)
from src.domain.agents.contracts.content_enrichment import ContentEnrichmentContract
from src.domain.agents.contracts.entity_recognition import (
    EntityRecognitionContract,
    RecognizedEntityCandidate,
    RecognizedObservationCandidate,
)
from src.domain.agents.contracts.extraction import (
    ExtractedObservation,
    ExtractedRelation,
    ExtractionContract,
    RejectedFact,
)
from src.domain.agents.contracts.extraction_policy import (
    ExtractionPolicyContract,
    RelationConstraintProposal,
    RelationTypeMappingProposal,
    UnknownRelationPattern,
)
from src.domain.agents.contracts.graph_connection import (
    GraphConnectionContract,
    ProposedRelation,
    RejectedCandidate,
)
from src.domain.agents.contracts.graph_search import (
    EvidenceChainItem,
    GraphSearchContract,
    GraphSearchResultEntry,
)
from src.domain.agents.contracts.query_generation import QueryGenerationContract
from src.domain.agents.models import (
    ModelCapability,
    ModelCostTier,
    ModelReasoningSettings,
    ModelSpec,
)

__all__ = [
    # Contracts
    "AgentDecision",
    "BaseAgentContract",
    "ContentEnrichmentContract",
    "EntityRecognitionContract",
    "EvidenceItem",
    "ExtractedObservation",
    "ExtractedRelation",
    "ExtractionContract",
    "ExtractionPolicyContract",
    "GraphConnectionContract",
    "GraphSearchContract",
    "GraphSearchResultEntry",
    "EvidenceChainItem",
    "ProposedRelation",
    "QueryGenerationContract",
    "RejectedCandidate",
    "RejectedFact",
    "RelationConstraintProposal",
    "RelationTypeMappingProposal",
    "RecognizedEntityCandidate",
    "RecognizedObservationCandidate",
    "UnknownRelationPattern",
    # Contexts
    "BaseAgentContext",
    "ContentEnrichmentContext",
    "EntityRecognitionContext",
    "ExtractionContext",
    "ExtractionPolicyContext",
    "GraphConnectionContext",
    "GraphSearchContext",
    "QueryGenerationContext",
    # Models
    "ModelCapability",
    "ModelCostTier",
    "ModelReasoningSettings",
    "ModelSpec",
]
