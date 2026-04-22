"""
Skills registry for AI agents.

Skills are bounded capabilities that agents can invoke.
Every skill must be explicitly registered with:
- Unique namespaced ID
- Input/output schemas
- Side effects declaration
- Governance metadata
"""

from src.infrastructure.llm.skills.registry import (
    SkillRegistry,
    build_content_enrichment_tools,
    build_entity_recognition_dictionary_tools,
    build_extraction_validation_tools,
    build_graph_connection_tools,
    build_graph_search_tools,
    get_skill_registry,
    register_all_skills,
)

__all__ = [
    "build_extraction_validation_tools",
    "build_content_enrichment_tools",
    "build_entity_recognition_dictionary_tools",
    "build_graph_connection_tools",
    "build_graph_search_tools",
    "get_skill_registry",
    "register_all_skills",
    "SkillRegistry",
]
