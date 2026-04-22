"""LLM infrastructure layer for AI runtime adapters and configuration."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    # Adapters
    "ArtanaContentEnrichmentAdapter",
    "ArtanaEntityRecognitionAdapter",
    "ArtanaExtractionAdapter",
    "ArtanaExtractionPolicyAdapter",
    "ArtanaGraphConnectionAdapter",
    "ArtanaGraphSearchAdapter",
    "ArtanaMappingJudgeAdapter",
    "ArtanaQueryAgentAdapter",
    # Config
    "ArtanaModelRegistry",
    "GovernanceConfig",
    "ModelRegistry",
    "get_model_registry",
    "resolve_artana_state_uri",
    # Skills
    "build_content_enrichment_tools",
    "build_extraction_validation_tools",
    "build_entity_recognition_dictionary_tools",
    "build_graph_connection_tools",
    "build_graph_search_tools",
    "get_skill_registry",
    "register_all_skills",
    "SkillRegistry",
    # State inspection
    "ArtanaKernelRunProgressRepository",
    "SqlAlchemyAgentRunStateRepository",
]

_EXPORT_MAP: dict[str, tuple[str, str]] = {
    "ArtanaContentEnrichmentAdapter": (
        "src.infrastructure.llm.adapters.content_enrichment_agent_adapter",
        "ArtanaContentEnrichmentAdapter",
    ),
    "ArtanaEntityRecognitionAdapter": (
        "src.infrastructure.llm.adapters.entity_recognition_agent_adapter",
        "ArtanaEntityRecognitionAdapter",
    ),
    "ArtanaExtractionAdapter": (
        "src.infrastructure.llm.adapters.extraction_agent_adapter",
        "ArtanaExtractionAdapter",
    ),
    "ArtanaExtractionPolicyAdapter": (
        "src.infrastructure.llm.adapters.extraction_policy_agent_adapter",
        "ArtanaExtractionPolicyAdapter",
    ),
    "ArtanaGraphConnectionAdapter": (
        "src.infrastructure.llm.adapters.graph_connection_agent_adapter",
        "ArtanaGraphConnectionAdapter",
    ),
    "ArtanaGraphSearchAdapter": (
        "src.infrastructure.llm.adapters.graph_search_agent_adapter",
        "ArtanaGraphSearchAdapter",
    ),
    "ArtanaMappingJudgeAdapter": (
        "src.infrastructure.llm.adapters.mapping_judge_agent_adapter",
        "ArtanaMappingJudgeAdapter",
    ),
    "ArtanaQueryAgentAdapter": (
        "src.infrastructure.llm.adapters.query_agent_adapter",
        "ArtanaQueryAgentAdapter",
    ),
    "ArtanaModelRegistry": (
        "src.infrastructure.llm.config.model_registry",
        "ArtanaModelRegistry",
    ),
    "GovernanceConfig": (
        "src.infrastructure.llm.config.governance",
        "GovernanceConfig",
    ),
    "ModelRegistry": (
        "src.infrastructure.llm.config.model_registry",
        "ModelRegistry",
    ),
    "get_model_registry": (
        "src.infrastructure.llm.config.model_registry",
        "get_model_registry",
    ),
    "resolve_artana_state_uri": (
        "src.infrastructure.llm.config.artana_config",
        "resolve_artana_state_uri",
    ),
    "build_content_enrichment_tools": (
        "src.infrastructure.llm.skills.registry",
        "build_content_enrichment_tools",
    ),
    "build_extraction_validation_tools": (
        "src.infrastructure.llm.skills.registry",
        "build_extraction_validation_tools",
    ),
    "build_entity_recognition_dictionary_tools": (
        "src.infrastructure.llm.skills.registry",
        "build_entity_recognition_dictionary_tools",
    ),
    "build_graph_connection_tools": (
        "src.infrastructure.llm.skills.registry",
        "build_graph_connection_tools",
    ),
    "build_graph_search_tools": (
        "src.infrastructure.llm.skills.registry",
        "build_graph_search_tools",
    ),
    "get_skill_registry": (
        "src.infrastructure.llm.skills.registry",
        "get_skill_registry",
    ),
    "register_all_skills": (
        "src.infrastructure.llm.skills.registry",
        "register_all_skills",
    ),
    "SkillRegistry": (
        "src.infrastructure.llm.skills.registry",
        "SkillRegistry",
    ),
    "ArtanaKernelRunProgressRepository": (
        "src.infrastructure.llm.state.run_progress_repository",
        "ArtanaKernelRunProgressRepository",
    ),
    "SqlAlchemyAgentRunStateRepository": (
        "src.infrastructure.llm.state.agent_run_state_repository",
        "SqlAlchemyAgentRunStateRepository",
    ),
}


def __getattr__(name: str) -> object:
    target = _EXPORT_MAP.get(name)
    if target is None:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)
    module_name, attribute_name = target
    module = import_module(module_name)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
