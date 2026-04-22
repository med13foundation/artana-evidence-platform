"""
Centralized skill registration for AI agents.

Provides a registry for all agent skills with governance
metadata and runtime gating support.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.infrastructure.llm.config.governance import GovernanceConfig

from .core_tools import (
    extract_citations_stub,
    search_pubmed_stub,
    suggest_mesh_terms,
    validate_pubmed_query,
)
from .dictionary_tools import (
    make_create_entity_type_tool,
    make_create_relation_constraint_tool,
    make_create_relation_type_tool,
    make_create_synonym_tool,
    make_create_variable_tool,
    make_dictionary_search_by_domain_tool,
    make_dictionary_search_tool,
)
from .enrichment_tools import (
    make_check_open_access_tool,
    make_fetch_europe_pmc_tool,
    make_fetch_pmc_oa_tool,
    make_pass_through_tool,
)
from .extraction_tools import (
    make_lookup_transform_tool,
    make_validate_observation_tool,
    make_validate_triple_tool,
)
from .graph_tools import (
    make_graph_aggregate_tool,
    make_graph_query_by_observation_tool,
    make_graph_query_entities_tool,
    make_graph_query_neighbourhood_tool,
    make_graph_query_observations_tool,
    make_graph_query_relation_evidence_tool,
    make_graph_query_relations_tool,
    make_graph_query_shared_subjects_tool,
    make_upsert_relation_tool,
)

if TYPE_CHECKING:
    from artana_evidence_db.kernel_repositories import (
        KernelRelationRepository,
    )
    from artana_evidence_db.query_ports import GraphQueryPort
    from artana_evidence_db.semantic_ports import DictionaryPort

    from src.type_definitions.common import JSONObject, ResearchSpaceSettings

logger = logging.getLogger(__name__)

# Type alias for skill callables.
SkillCallable = Callable[..., object]
SkillFactory = Callable[..., SkillCallable]

_ENTITY_RECOGNITION_DICTIONARY_DISCOVERY_SKILL_IDS: tuple[str, ...] = (
    "dictionary_search",
    "dictionary_search_by_domain",
)
_ENTITY_RECOGNITION_DICTIONARY_POLICY_SKILL_IDS: tuple[str, ...] = (
    "dictionary_search",
    "dictionary_search_by_domain",
    "create_variable",
    "create_synonym",
    "create_entity_type",
    "create_relation_type",
    "create_relation_constraint",
)
_EXTRACTION_SKILL_IDS: tuple[str, ...] = (
    "validate_observation",
    "validate_triple",
    "lookup_transform",
)
_CONTENT_ENRICHMENT_SKILL_IDS: tuple[str, ...] = (
    "fetch_pmc_oa",
    "fetch_europe_pmc",
    "check_open_access",
    "pass_through",
)
_GRAPH_CONNECTION_SKILL_IDS: tuple[str, ...] = (
    "graph_query_neighbourhood",
    "graph_query_shared_subjects",
    "graph_query_observations",
    "graph_query_relation_evidence",
    "upsert_relation",
    "validate_triple",
)
_GRAPH_SEARCH_SKILL_IDS: tuple[str, ...] = (
    "graph_query_entities",
    "graph_query_relations",
    "graph_query_observations",
    "graph_query_by_observation",
    "graph_aggregate",
    "graph_query_relation_evidence",
)


@dataclass
class SkillDefinition:
    """
    Definition of a registered skill.

    Contains all metadata required for skill governance
    and execution.
    """

    id: str
    factory: SkillFactory
    description: str
    side_effects: bool = False
    input_schema: JSONObject = field(default_factory=dict)
    output_schema: JSONObject = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


class SkillRegistry:
    """
    Registry for AI agent skills.

    Provides centralized management of all skills with:
    - Namespace-based organization
    - Governance integration
    - Runtime gating
    """

    def __init__(self, governance: GovernanceConfig | None = None) -> None:
        """
        Initialize the skill registry.

        Args:
            governance: Optional governance configuration
        """
        self._skills: dict[str, SkillDefinition] = {}
        self._governance = governance or GovernanceConfig.from_environment()

    def register(  # noqa: PLR0913
        self,
        skill_id: str,
        factory: SkillFactory,
        description: str,
        *,
        side_effects: bool = False,
        input_schema: JSONObject | None = None,
        output_schema: JSONObject | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """
        Register a skill with the registry.

        Args:
            skill_id: Unique namespaced skill ID (e.g., "pubmed.search")
            factory: Callable that returns the skill implementation
            description: Human-readable description
            side_effects: Whether the skill has side effects
            input_schema: JSON schema for input validation
            output_schema: JSON schema for output validation
            tags: Optional tags for categorization
        """
        if skill_id in self._skills:
            logger.warning("Overwriting existing skill: %s", skill_id)

        self._skills[skill_id] = SkillDefinition(
            id=skill_id,
            factory=factory,
            description=description,
            side_effects=side_effects,
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            tags=tags or [],
        )
        logger.debug("Registered skill: %s", skill_id)

    def get(self, skill_id: str) -> SkillDefinition | None:
        """
        Get a skill definition by ID.

        Args:
            skill_id: The skill ID to look up

        Returns:
            SkillDefinition if found, None otherwise
        """
        return self._skills.get(skill_id)

    def get_callable(self, skill_id: str, **kwargs: object) -> SkillCallable | None:
        """
        Get a skill's callable implementation.

        Args:
            skill_id: The skill ID to look up
            **kwargs: Arguments to pass to the factory

        Returns:
            The skill callable if found and allowed, None otherwise

        Raises:
            PermissionError: If skill is not in governance allowlist
        """
        skill = self._skills.get(skill_id)
        if skill is None:
            return None

        if not self._governance.is_tool_allowed(skill_id):
            msg = f"Skill '{skill_id}' is not in the governance allowlist"
            raise PermissionError(msg)

        return skill.factory(**kwargs)

    def list_skills(self) -> list[str]:
        """List all registered skill IDs."""
        return list(self._skills.keys())

    def list_allowed_skills(self) -> list[str]:
        """List skill IDs that pass governance checks."""
        return [
            skill_id
            for skill_id in self._skills
            if self._governance.is_tool_allowed(skill_id)
        ]

    def get_skills_by_tag(self, tag: str) -> list[SkillDefinition]:
        """Get all skills with a specific tag."""
        return [skill for skill in self._skills.values() if tag in skill.tags]


# Global registry instance
_global_registry: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    """
    Get the global skill registry instance.

    Creates the registry on first access.
    """
    global _global_registry  # noqa: PLW0603
    if _global_registry is None:
        _global_registry = SkillRegistry()
    return _global_registry


def register_all_skills() -> None:
    """
    Register all application skills.

    Call this during application startup to ensure all
    skills are available for agents.
    """
    registry = get_skill_registry()
    if (
        registry.get("query.validate_pubmed") is not None
        and registry.get(
            "dictionary_search",
        )
        is not None
        and registry.get("graph_query_neighbourhood") is not None
    ):
        return

    # --- Query Validation Skills ---
    registry.register(
        skill_id="query.validate_pubmed",
        factory=lambda **_: validate_pubmed_query,
        description="Validate a PubMed Boolean query syntax. Read-only.",
        side_effects=False,
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "PubMed query to validate"},
            },
            "required": ["query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "valid": {"type": "boolean"},
                "query": {"type": "string"},
                "issues": {"type": "array", "items": {"type": "string"}},
                "suggestions": {"type": "array", "items": {"type": "string"}},
            },
        },
        tags=["query", "pubmed", "validation"],
    )

    # --- Search Skills ---
    registry.register(
        skill_id="search.pubmed",
        factory=lambda **_: search_pubmed_stub,
        description="Execute a PubMed search query. Read-only API call.",
        side_effects=False,
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "PubMed search query"},
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
                "results": {"type": "array"},
                "total_count": {"type": "integer"},
            },
        },
        tags=["search", "pubmed", "api"],
    )

    # --- Query Building Skills ---
    registry.register(
        skill_id="query.suggest_mesh_terms",
        factory=lambda **_: suggest_mesh_terms,
        description="Suggest MeSH terms for a given concept. Read-only.",
        side_effects=False,
        input_schema={
            "type": "object",
            "properties": {
                "concept": {
                    "type": "string",
                    "description": "Medical concept to look up",
                },
            },
            "required": ["concept"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "concept": {"type": "string"},
                "mesh_terms": {"type": "array", "items": {"type": "string"}},
                "found": {"type": "boolean"},
            },
        },
        tags=["query", "mesh", "vocabulary"],
    )

    # --- Evidence Skills ---
    registry.register(
        skill_id="evidence.extract_citations",
        factory=lambda **_: extract_citations_stub,
        description="Extract citations from text. Read-only.",
        side_effects=False,
        input_schema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to extract citations from",
                },
            },
            "required": ["text"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "citations": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
        tags=["evidence", "citations", "extraction"],
    )

    # --- Dictionary Skills ---
    registry.register(
        skill_id="dictionary_search",
        factory=make_dictionary_search_tool,
        description="Search dictionary definitions across dimensions. Read-only.",
        side_effects=False,
        input_schema={
            "type": "object",
            "properties": {
                "terms": {"type": "array", "items": {"type": "string"}},
                "dimensions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "domain_context": {"type": "string"},
                "limit": {"type": "integer", "default": 25},
            },
            "required": ["terms"],
        },
        output_schema={
            "type": "array",
            "items": {"type": "object"},
        },
        tags=["dictionary", "semantic-layer", "search"],
    )
    registry.register(
        skill_id="dictionary_search_by_domain",
        factory=make_dictionary_search_by_domain_tool,
        description="List dictionary entries scoped to one domain context.",
        side_effects=False,
        input_schema={
            "type": "object",
            "properties": {
                "domain_context": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["domain_context"],
        },
        output_schema={
            "type": "array",
            "items": {"type": "object"},
        },
        tags=["dictionary", "semantic-layer", "search"],
    )
    registry.register(
        skill_id="create_variable",
        factory=make_create_variable_tool,
        description="Create a dictionary variable definition.",
        side_effects=True,
        input_schema={
            "type": "object",
            "properties": {
                "variable_id": {"type": "string"},
                "canonical_name": {"type": "string"},
                "display_name": {"type": "string"},
                "data_type": {"type": "string"},
                "options": {
                    "type": "string",
                    "description": (
                        "Optional JSON object string with domain_context, "
                        "sensitivity, preferred_unit, constraints, description."
                    ),
                },
            },
            "required": ["variable_id", "canonical_name", "display_name", "data_type"],
        },
        output_schema={"type": "object"},
        tags=["dictionary", "semantic-layer", "write"],
    )
    registry.register(
        skill_id="create_synonym",
        factory=make_create_synonym_tool,
        description="Create a synonym for an existing dictionary variable.",
        side_effects=True,
        input_schema={
            "type": "object",
            "properties": {
                "variable_id": {"type": "string"},
                "synonym": {"type": "string"},
                "source": {"type": "string"},
            },
            "required": ["variable_id", "synonym"],
        },
        output_schema={"type": "object"},
        tags=["dictionary", "semantic-layer", "write"],
    )
    registry.register(
        skill_id="create_entity_type",
        factory=make_create_entity_type_tool,
        description="Create a first-class dictionary entity type.",
        side_effects=True,
        input_schema={
            "type": "object",
            "properties": {
                "entity_type": {"type": "string"},
                "display_name": {"type": "string"},
                "description": {"type": "string"},
                "domain_context": {"type": "string"},
                "external_ontology_ref": {"type": "string"},
                "expected_properties": {
                    "type": "string",
                    "description": "JSON object string for entity-type properties.",
                },
            },
            "required": [
                "entity_type",
                "display_name",
                "description",
                "domain_context",
            ],
        },
        output_schema={"type": "object"},
        tags=["dictionary", "semantic-layer", "write"],
    )
    registry.register(
        skill_id="create_relation_type",
        factory=make_create_relation_type_tool,
        description="Create a first-class dictionary relation type.",
        side_effects=True,
        input_schema={
            "type": "object",
            "properties": {
                "relation_type": {"type": "string"},
                "display_name": {"type": "string"},
                "description": {"type": "string"},
                "domain_context": {"type": "string"},
                "is_directional": {"type": "boolean", "default": True},
                "inverse_label": {"type": "string"},
            },
            "required": [
                "relation_type",
                "display_name",
                "description",
                "domain_context",
            ],
        },
        output_schema={"type": "object"},
        tags=["dictionary", "semantic-layer", "write"],
    )
    registry.register(
        skill_id="create_relation_constraint",
        factory=make_create_relation_constraint_tool,
        description="Create a relation constraint triple for graph validation.",
        side_effects=True,
        input_schema={
            "type": "object",
            "properties": {
                "source_type": {"type": "string"},
                "relation_type": {"type": "string"},
                "target_type": {"type": "string"},
                "is_allowed": {"type": "boolean", "default": True},
                "requires_evidence": {"type": "boolean", "default": True},
            },
            "required": ["source_type", "relation_type", "target_type"],
        },
        output_schema={"type": "object"},
        tags=["dictionary", "semantic-layer", "write"],
    )

    # --- Extraction Validation Skills ---
    registry.register(
        skill_id="validate_observation",
        factory=make_validate_observation_tool,
        description="Validate an extracted observation against dictionary constraints.",
        side_effects=False,
        input_schema={
            "type": "object",
            "properties": {
                "variable_id": {"type": "string"},
                "value": {},
                "unit": {"type": "string"},
            },
            "required": ["variable_id", "value"],
        },
        output_schema={"type": "object"},
        tags=["extraction", "validation", "semantic-layer"],
    )
    registry.register(
        skill_id="validate_triple",
        factory=make_validate_triple_tool,
        description="Validate a relation triple against dictionary constraints.",
        side_effects=False,
        input_schema={
            "type": "object",
            "properties": {
                "source_type": {"type": "string"},
                "relation_type": {"type": "string"},
                "target_type": {"type": "string"},
            },
            "required": ["source_type", "relation_type", "target_type"],
        },
        output_schema={"type": "object"},
        tags=["extraction", "validation", "semantic-layer"],
    )
    registry.register(
        skill_id="lookup_transform",
        factory=make_lookup_transform_tool,
        description="Look up a registered transform between two units.",
        side_effects=False,
        input_schema={
            "type": "object",
            "properties": {
                "input_unit": {"type": "string"},
                "output_unit": {"type": "string"},
            },
            "required": ["input_unit", "output_unit"],
        },
        output_schema={"type": "object"},
        tags=["extraction", "normalization", "semantic-layer"],
    )
    registry.register(
        skill_id="fetch_pmc_oa",
        factory=make_fetch_pmc_oa_tool,
        description="Fetch open-access XML metadata/content using the PMC OA API.",
        side_effects=False,
        input_schema={
            "type": "object",
            "properties": {
                "pmcid": {"type": "string"},
            },
            "required": ["pmcid"],
        },
        output_schema={"type": "object"},
        tags=["enrichment", "pmc", "read"],
    )
    registry.register(
        skill_id="fetch_europe_pmc",
        factory=make_fetch_europe_pmc_tool,
        description="Fetch Europe PMC full-text XML when available.",
        side_effects=False,
        input_schema={
            "type": "object",
            "properties": {
                "identifier": {"type": "string"},
            },
            "required": ["identifier"],
        },
        output_schema={"type": "object"},
        tags=["enrichment", "europe-pmc", "read"],
    )
    registry.register(
        skill_id="check_open_access",
        factory=make_check_open_access_tool,
        description="Run a coarse open-access eligibility check.",
        side_effects=False,
        input_schema={
            "type": "object",
            "properties": {
                "pmcid": {"type": "string"},
                "doi": {"type": "string"},
            },
        },
        output_schema={"type": "object"},
        tags=["enrichment", "open-access", "read"],
    )
    registry.register(
        skill_id="pass_through",
        factory=make_pass_through_tool,
        description="Mark structured payloads as enrichment-complete without fetching.",
        side_effects=False,
        input_schema={
            "type": "object",
            "properties": {
                "payload": {
                    "type": "string",
                    "description": (
                        "JSON-encoded object payload for deterministic pass-through."
                    ),
                },
                "content_text": {
                    "type": "string",
                    "description": "Plain-text payload for deterministic pass-through.",
                },
            },
        },
        output_schema={"type": "object"},
        tags=["enrichment", "pass-through", "read"],
    )
    registry.register(
        skill_id="graph_query_entities",
        factory=make_graph_query_entities_tool,
        description="Query entities in a research space with optional text/type filters.",
        side_effects=False,
        input_schema={
            "type": "object",
            "properties": {
                "entity_type": {"type": "string"},
                "query_text": {"type": "string"},
                "limit": {"type": "integer", "default": 200},
            },
        },
        output_schema={"type": "array", "items": {"type": "object"}},
        tags=["graph", "query", "read"],
    )
    registry.register(
        skill_id="graph_query_neighbourhood",
        factory=make_graph_query_neighbourhood_tool,
        description="Query relation neighbourhood around an entity in one space.",
        side_effects=False,
        input_schema={
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "depth": {"type": "integer", "default": 1},
                "relation_types": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "default": 200},
            },
            "required": ["entity_id"],
        },
        output_schema={"type": "array", "items": {"type": "object"}},
        tags=["graph", "query", "read"],
    )
    registry.register(
        skill_id="graph_query_relations",
        factory=make_graph_query_relations_tool,
        description="Traverse graph relations from one entity with direction/depth.",
        side_effects=False,
        input_schema={
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "relation_types": {"type": "array", "items": {"type": "string"}},
                "direction": {"type": "string", "default": "both"},
                "depth": {"type": "integer", "default": 1},
                "limit": {"type": "integer", "default": 200},
            },
            "required": ["entity_id"],
        },
        output_schema={"type": "array", "items": {"type": "object"}},
        tags=["graph", "query", "read"],
    )
    registry.register(
        skill_id="graph_query_shared_subjects",
        factory=make_graph_query_shared_subjects_tool,
        description=(
            "Find entities whose observation profiles overlap with both seed entities."
        ),
        side_effects=False,
        input_schema={
            "type": "object",
            "properties": {
                "entity_id_a": {"type": "string"},
                "entity_id_b": {"type": "string"},
                "limit": {"type": "integer", "default": 100},
            },
            "required": ["entity_id_a", "entity_id_b"],
        },
        output_schema={"type": "array", "items": {"type": "object"}},
        tags=["graph", "query", "read"],
    )
    registry.register(
        skill_id="graph_query_observations",
        factory=make_graph_query_observations_tool,
        description="Return observations for one entity in the scoped space.",
        side_effects=False,
        input_schema={
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "variable_ids": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "default": 200},
            },
            "required": ["entity_id"],
        },
        output_schema={"type": "array", "items": {"type": "object"}},
        tags=["graph", "query", "read"],
    )
    registry.register(
        skill_id="graph_query_by_observation",
        factory=make_graph_query_by_observation_tool,
        description="Find entities matching one observation predicate.",
        side_effects=False,
        input_schema={
            "type": "object",
            "properties": {
                "variable_id": {"type": "string"},
                "operator": {"type": "string", "default": "eq"},
                "value": {},
                "limit": {"type": "integer", "default": 200},
            },
            "required": ["variable_id"],
        },
        output_schema={"type": "array", "items": {"type": "object"}},
        tags=["graph", "query", "read"],
    )
    registry.register(
        skill_id="graph_query_relation_evidence",
        factory=make_graph_query_relation_evidence_tool,
        description="Return all evidence rows for one canonical relation edge.",
        side_effects=False,
        input_schema={
            "type": "object",
            "properties": {
                "relation_id": {"type": "string"},
                "limit": {"type": "integer", "default": 200},
            },
            "required": ["relation_id"],
        },
        output_schema={"type": "array", "items": {"type": "object"}},
        tags=["graph", "query", "read"],
    )
    registry.register(
        skill_id="graph_aggregate",
        factory=make_graph_aggregate_tool,
        description="Compute aggregate metrics for a variable within a space.",
        side_effects=False,
        input_schema={
            "type": "object",
            "properties": {
                "variable_id": {"type": "string"},
                "entity_type": {"type": "string"},
                "aggregation": {"type": "string", "default": "count"},
            },
            "required": ["variable_id"],
        },
        output_schema={"type": "object"},
        tags=["graph", "query", "read"],
    )
    registry.register(
        skill_id="upsert_relation",
        factory=make_upsert_relation_tool,
        description="Canonical relation upsert with evidence accumulation.",
        side_effects=True,
        input_schema={
            "type": "object",
            "properties": {
                "source_id": {"type": "string"},
                "relation_type": {"type": "string"},
                "target_id": {"type": "string"},
                "confidence": {"type": "number", "default": 0.5},
                "evidence_summary": {"type": "string"},
                "evidence_tier": {"type": "string", "default": "COMPUTATIONAL"},
                "provenance_id": {"type": "string"},
            },
            "required": ["source_id", "relation_type", "target_id"],
        },
        output_schema={"type": "object"},
        tags=["graph", "truth-layer", "write"],
    )

    logger.info("Registered %d skills", len(registry.list_skills()))


def build_entity_recognition_dictionary_tools(  # noqa: PLR0913
    *,
    dictionary_service: DictionaryPort,
    created_by: str,
    source_ref: str | None = None,
    research_space_settings: ResearchSpaceSettings | None = None,
    include_mutation_tools: bool = True,
) -> list[SkillCallable]:
    """
    Build the dictionary toolset required by Entity Recognition Agent workflows.

    Tool access is filtered through governance allowlists at registry lookup time.
    When include_mutation_tools=False, only read/search dictionary tools are bound.
    """
    register_all_skills()
    registry = get_skill_registry()

    skill_ids = (
        _ENTITY_RECOGNITION_DICTIONARY_POLICY_SKILL_IDS
        if include_mutation_tools
        else _ENTITY_RECOGNITION_DICTIONARY_DISCOVERY_SKILL_IDS
    )
    tools: list[SkillCallable] = []
    for skill_id in skill_ids:
        skill = registry.get_callable(
            skill_id,
            dictionary_service=dictionary_service,
            created_by=created_by,
            source_ref=source_ref,
            research_space_settings=research_space_settings,
        )
        if skill is None:
            msg = f"Required skill '{skill_id}' is not registered"
            raise LookupError(msg)
        tools.append(skill)
    return tools


def build_extraction_validation_tools(
    *,
    dictionary_service: DictionaryPort,
    research_space_settings: ResearchSpaceSettings | None = None,
) -> list[SkillCallable]:
    """
    Build toolset used by the Extraction Agent for validation and normalization.
    """
    register_all_skills()
    registry = get_skill_registry()

    tools: list[SkillCallable] = []
    for skill_id in _EXTRACTION_SKILL_IDS:
        skill = registry.get_callable(
            skill_id,
            dictionary_service=dictionary_service,
            research_space_settings=research_space_settings,
        )
        if skill is None:
            msg = f"Required skill '{skill_id}' is not registered"
            raise LookupError(msg)
        tools.append(skill)
    return tools


def build_content_enrichment_tools() -> list[SkillCallable]:
    """Build the toolset used by Tier-2 content-enrichment agent workflows."""
    register_all_skills()
    registry = get_skill_registry()

    tools: list[SkillCallable] = []
    for skill_id in _CONTENT_ENRICHMENT_SKILL_IDS:
        skill = registry.get_callable(skill_id)
        if skill is None:
            msg = f"Required skill '{skill_id}' is not registered"
            raise LookupError(msg)
        tools.append(skill)
    return tools


def build_graph_connection_tools(  # noqa: PLR0913
    *,
    dictionary_service: DictionaryPort,
    graph_query_service: GraphQueryPort,
    relation_repository: KernelRelationRepository,
    research_space_id: str,
) -> list[SkillCallable]:
    """
    Build toolset for Graph Connection Agent workflows.
    """
    register_all_skills()
    registry = get_skill_registry()

    tools: list[SkillCallable] = []
    for skill_id in _GRAPH_CONNECTION_SKILL_IDS:
        skill = registry.get_callable(
            skill_id,
            dictionary_service=dictionary_service,
            graph_query_service=graph_query_service,
            relation_repository=relation_repository,
            research_space_id=research_space_id,
        )
        if skill is None:
            msg = f"Required skill '{skill_id}' is not registered"
            raise LookupError(msg)
        tools.append(skill)
    return tools


def build_graph_search_tools(
    *,
    graph_query_service: GraphQueryPort,
    research_space_id: str,
) -> list[SkillCallable]:
    """
    Build read-only graph toolset for Graph Search Agent workflows.
    """
    register_all_skills()
    registry = get_skill_registry()

    tools: list[SkillCallable] = []
    for skill_id in _GRAPH_SEARCH_SKILL_IDS:
        skill = registry.get_callable(
            skill_id,
            graph_query_service=graph_query_service,
            research_space_id=research_space_id,
        )
        if skill is None:
            msg = f"Required skill '{skill_id}' is not registered"
            raise LookupError(msg)
        tools.append(skill)
    return tools
