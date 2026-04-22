"""
Version-controlled system prompts for AI agents.

Prompts are organized by agent type and source to enable:
- Version control and review of prompt changes
- Centralized prompt management
- Easy A/B testing of prompt variations
"""

from src.infrastructure.llm.prompts.base_prompts import (
    BIOMEDICAL_CONTEXT_TEMPLATE,
    EVIDENCE_INSTRUCTION,
)
from src.infrastructure.llm.prompts.content_enrichment import (
    CONTENT_ENRICHMENT_SYSTEM_PROMPT,
)
from src.infrastructure.llm.prompts.entity_recognition import (
    CLINVAR_ENTITY_RECOGNITION_SYSTEM_PROMPT,
    PUBMED_ENTITY_RECOGNITION_SYSTEM_PROMPT,
)
from src.infrastructure.llm.prompts.extraction import (
    CLINVAR_EXTRACTION_SYSTEM_PROMPT,
    PUBMED_EXTRACTION_SYSTEM_PROMPT,
)
from src.infrastructure.llm.prompts.graph_connection import (
    CLINVAR_GRAPH_CONNECTION_SYSTEM_PROMPT,
    PUBMED_GRAPH_CONNECTION_SYSTEM_PROMPT,
)
from src.infrastructure.llm.prompts.graph_search import GRAPH_SEARCH_SYSTEM_PROMPT
from src.infrastructure.llm.prompts.pubmed_relevance import (
    PUBMED_RELEVANCE_SYSTEM_PROMPT,
)
from src.infrastructure.llm.prompts.query.pubmed import PUBMED_QUERY_SYSTEM_PROMPT

__all__ = [
    "BIOMEDICAL_CONTEXT_TEMPLATE",
    "CONTENT_ENRICHMENT_SYSTEM_PROMPT",
    "CLINVAR_EXTRACTION_SYSTEM_PROMPT",
    "CLINVAR_ENTITY_RECOGNITION_SYSTEM_PROMPT",
    "CLINVAR_GRAPH_CONNECTION_SYSTEM_PROMPT",
    "PUBMED_EXTRACTION_SYSTEM_PROMPT",
    "PUBMED_ENTITY_RECOGNITION_SYSTEM_PROMPT",
    "PUBMED_GRAPH_CONNECTION_SYSTEM_PROMPT",
    "GRAPH_SEARCH_SYSTEM_PROMPT",
    "EVIDENCE_INSTRUCTION",
    "PUBMED_QUERY_SYSTEM_PROMPT",
    "PUBMED_RELEVANCE_SYSTEM_PROMPT",
]
