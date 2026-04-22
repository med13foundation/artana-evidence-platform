"""
Typed PipelineContext extensions for AI agents.

Never use plain dict for context. Extend PipelineContext to enforce
schema validity and enable safe persistence with indexed fields.
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
from src.domain.agents.contexts.pubmed_relevance_context import (
    PubMedRelevanceContext,
)
from src.domain.agents.contexts.query_context import QueryGenerationContext

__all__ = [
    "BaseAgentContext",
    "ContentEnrichmentContext",
    "EntityRecognitionContext",
    "ExtractionContext",
    "ExtractionPolicyContext",
    "GraphConnectionContext",
    "GraphSearchContext",
    "PubMedRelevanceContext",
    "QueryGenerationContext",
]
