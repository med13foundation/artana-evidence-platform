"""
Evidence-First Output Schemas for AI Agents.

Agents must not expose internal chain-of-thought. Instead, use
Evidence-First schemas that separate:
- the decision
- the confidence
- the human-readable justification
- and the structured evidence supporting that decision

Design rule: If a decision cannot be supported by structured evidence,
it must not be auto-approved.
"""

from src.domain.agents.contracts.base import (
    AgentDecision,
    BaseAgentContract,
    EvidenceBackedAgentContract,
    EvidenceItem,
)
from src.domain.agents.contracts.content_enrichment import ContentEnrichmentContract
from src.domain.agents.contracts.entity_recognition import (
    EntityRecognitionContract,
    RecognizedEntityCandidate,
    RecognizedObservationCandidate,
)
from src.domain.agents.contracts.extraction import (
    ExtractedEntityCandidate,
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
from src.domain.agents.contracts.fact_assessment import (
    FactAssessment,
    GroundingLevel,
    MappingStatus,
    SpeculationLevel,
    SupportBand,
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
from src.domain.agents.contracts.graph_search_assessment import (
    GraphSearchAssessment,
    GraphSearchGroundingLevel,
    GraphSearchSupportBand,
)
from src.domain.agents.contracts.mapping_judge import (
    MappingJudgeCandidate,
    MappingJudgeContract,
)
from src.domain.agents.contracts.mapping_judge_assessment import (
    CandidateSeparation,
    MappingJudgeAssessment,
    MappingResolutionStatus,
    MappingSupportBand,
)
from src.domain.agents.contracts.pubmed_relevance import PubMedRelevanceContract
from src.domain.agents.contracts.query_generation import QueryGenerationContract
from src.domain.agents.contracts.recognition_assessment import (
    AmbiguityStatus,
    BoundaryQuality,
    NormalizationStatus,
    RecognitionAssessment,
    RecognitionBand,
)

__all__ = [
    "AgentDecision",
    "BaseAgentContract",
    "ContentEnrichmentContract",
    "EvidenceBackedAgentContract",
    "EntityRecognitionContract",
    "EvidenceItem",
    "ExtractedEntityCandidate",
    "ExtractedObservation",
    "ExtractedRelation",
    "ExtractionContract",
    "ExtractionPolicyContract",
    "FactAssessment",
    "GraphConnectionContract",
    "GraphSearchContract",
    "GraphSearchResultEntry",
    "GroundingLevel",
    "BoundaryQuality",
    "RecognitionAssessment",
    "RecognitionBand",
    "NormalizationStatus",
    "AmbiguityStatus",
    "MappingJudgeAssessment",
    "MappingSupportBand",
    "MappingResolutionStatus",
    "CandidateSeparation",
    "MappingStatus",
    "MappingJudgeCandidate",
    "MappingJudgeContract",
    "PubMedRelevanceContract",
    "EvidenceChainItem",
    "GraphSearchAssessment",
    "ProposedRelation",
    "QueryGenerationContract",
    "RejectedCandidate",
    "RejectedFact",
    "SpeculationLevel",
    "RelationConstraintProposal",
    "RelationTypeMappingProposal",
    "RecognizedEntityCandidate",
    "RecognizedObservationCandidate",
    "GraphSearchGroundingLevel",
    "GraphSearchSupportBand",
    "SupportBand",
    "UnknownRelationPattern",
]
