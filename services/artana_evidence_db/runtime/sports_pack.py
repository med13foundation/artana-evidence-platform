"""Sports example graph runtime pack for boundary validation."""

from __future__ import annotations

from artana_evidence_db.graph_domain_config import (
    BuiltinEntityTypeDefinition,
    BuiltinRelationConstraintDefinition,
    BuiltinRelationTypeDefinition,
    DictionaryDomainContextDefinition,
    GraphDictionaryLoadingConfig,
    GraphRelationSuggestionConfig,
    GraphViewConfig,
)
from artana_evidence_db.relation_autopromotion_policy import (
    RelationAutopromotionDefaults,
)
from artana_evidence_db.runtime.contracts import (
    FeatureFlagDefinition,
    GraphAgentCapabilities,
    GraphAgentCapability,
    GraphDomainContextPolicy,
    GraphDomainPack,
    GraphFeatureFlags,
    GraphRuntimeIdentity,
    SourceTypeDomainContextDefault,
)

SPORTS_DICTIONARY_LOADING_CONFIG = GraphDictionaryLoadingConfig(
    builtin_domain_contexts=(
        DictionaryDomainContextDefinition(
            id="general",
            display_name="General",
            description="Domain-agnostic defaults for shared graph terms.",
        ),
        DictionaryDomainContextDefinition(
            id="competition",
            display_name="Competition",
            description="Matches, seasons, leagues, and standings.",
        ),
        DictionaryDomainContextDefinition(
            id="roster",
            display_name="Roster",
            description="Teams, players, positions, and roster movement.",
        ),
    ),
    builtin_entity_types=(
        BuiltinEntityTypeDefinition(
            entity_type="TEAM",
            display_name="Team",
            description="Sports team or club.",
            domain_context="roster",
        ),
        BuiltinEntityTypeDefinition(
            entity_type="PLAYER",
            display_name="Player",
            description="Athlete or rostered player.",
            domain_context="roster",
        ),
        BuiltinEntityTypeDefinition(
            entity_type="MATCH",
            display_name="Match",
            description="Game, match, fixture, or competition event.",
            domain_context="competition",
        ),
        BuiltinEntityTypeDefinition(
            entity_type="SEASON",
            display_name="Season",
            description="Competition season or campaign.",
            domain_context="competition",
        ),
        BuiltinEntityTypeDefinition(
            entity_type="LEAGUE",
            display_name="League",
            description="Sports league or competition organizer.",
            domain_context="competition",
        ),
        BuiltinEntityTypeDefinition(
            entity_type="POSITION",
            display_name="Position",
            description="Player position or tactical role.",
            domain_context="roster",
        ),
    ),
    builtin_relation_types=(
        BuiltinRelationTypeDefinition(
            relation_type="PLAYS_FOR",
            display_name="Plays For",
            description="Player is rostered for or plays for a team.",
            domain_context="roster",
            category="extended_scientific",
            inverse_label="HAS_PLAYER",
        ),
        BuiltinRelationTypeDefinition(
            relation_type="PARTICIPATED_IN",
            display_name="Participated In",
            description="Entity participated in a match or competition event.",
            domain_context="competition",
            category="extended_scientific",
            inverse_label="HAD_PARTICIPANT",
        ),
        BuiltinRelationTypeDefinition(
            relation_type="WON_AGAINST",
            display_name="Won Against",
            description="Team defeated another team.",
            domain_context="competition",
            category="extended_scientific",
            inverse_label="LOST_TO",
        ),
        BuiltinRelationTypeDefinition(
            relation_type="PART_OF",
            display_name="Part Of",
            description="Entity is part of a larger sports competition unit.",
            domain_context="general",
            category="extended_scientific",
            inverse_label="HAS_PART",
        ),
        BuiltinRelationTypeDefinition(
            relation_type="MEMBER_OF",
            display_name="Member Of",
            description="Team or player belongs to a league or group.",
            domain_context="general",
            category="extended_scientific",
            inverse_label="HAS_MEMBER",
        ),
        BuiltinRelationTypeDefinition(
            relation_type="POSITIONED_AS",
            display_name="Positioned As",
            description="Player is assigned or commonly used in a position.",
            domain_context="roster",
            category="extended_scientific",
            inverse_label="HAS_POSITION_PLAYER",
        ),
    ),
    builtin_relation_constraints=(
        BuiltinRelationConstraintDefinition(
            source_type="PLAYER",
            relation_type="PLAYS_FOR",
            target_type="TEAM",
        ),
        BuiltinRelationConstraintDefinition(
            source_type="PLAYER",
            relation_type="PARTICIPATED_IN",
            target_type="MATCH",
        ),
        BuiltinRelationConstraintDefinition(
            source_type="TEAM",
            relation_type="PARTICIPATED_IN",
            target_type="MATCH",
        ),
        BuiltinRelationConstraintDefinition(
            source_type="TEAM",
            relation_type="WON_AGAINST",
            target_type="TEAM",
        ),
        BuiltinRelationConstraintDefinition(
            source_type="MATCH",
            relation_type="PART_OF",
            target_type="SEASON",
        ),
        BuiltinRelationConstraintDefinition(
            source_type="TEAM",
            relation_type="MEMBER_OF",
            target_type="LEAGUE",
        ),
        BuiltinRelationConstraintDefinition(
            source_type="SEASON",
            relation_type="PART_OF",
            target_type="LEAGUE",
        ),
        BuiltinRelationConstraintDefinition(
            source_type="PLAYER",
            relation_type="POSITIONED_AS",
            target_type="POSITION",
        ),
    ),
)

SPORTS_VIEW_CONFIG = GraphViewConfig(
    entity_view_types={
        "team": "TEAM",
        "player": "PLAYER",
        "match": "MATCH",
    },
    document_view_types=frozenset({"report"}),
    claim_view_types=frozenset({"claim"}),
    mechanism_relation_types=frozenset(
        {
            "PARTICIPATED_IN",
            "PLAYS_FOR",
            "WON_AGAINST",
        },
    ),
)

SPORTS_DOMAIN_CONTEXT_POLICY = GraphDomainContextPolicy(
    source_type_defaults=(
        SourceTypeDomainContextDefault(
            source_type="match_report",
            domain_context="competition",
        ),
        SourceTypeDomainContextDefault(
            source_type="roster",
            domain_context="roster",
        ),
    ),
)

SPORTS_AGENT_CAPABILITIES = GraphAgentCapabilities(
    entity_recognition=GraphAgentCapability(
        name="entity_recognition",
        supported_source_types=("match_report", "roster"),
        default_source_type="match_report",
        step_key_prefix="entity.recognition",
    ),
    extraction=GraphAgentCapability(
        name="extraction",
        supported_source_types=("match_report", "roster"),
        default_source_type="match_report",
        step_key_prefix="extraction",
    ),
    graph_connection=GraphAgentCapability(
        name="graph_connection",
        supported_source_types=("match_report", "roster"),
        default_source_type="match_report",
        step_key_prefix="graph.connection",
    ),
    graph_search=GraphAgentCapability(
        name="graph_search",
        supported_source_types=("graph",),
        default_source_type="graph",
        step_key_prefix="graph.search",
    ),
)

SPORTS_FEATURE_FLAGS = GraphFeatureFlags(
    entity_embeddings=FeatureFlagDefinition(
        primary_env_name="GRAPH_ENABLE_ENTITY_EMBEDDINGS",
    ),
    relation_suggestions=FeatureFlagDefinition(
        primary_env_name="GRAPH_ENABLE_RELATION_SUGGESTIONS",
    ),
    hypothesis_generation=FeatureFlagDefinition(
        primary_env_name="GRAPH_ENABLE_HYPOTHESIS_GENERATION",
    ),
    search_agent=FeatureFlagDefinition(
        primary_env_name="GRAPH_ENABLE_SEARCH_AGENT",
    ),
)

SPORTS_GRAPH_DOMAIN_PACK = GraphDomainPack(
    name="sports",
    version="1.0.0",
    runtime_identity=GraphRuntimeIdentity(
        service_name="Sports Graph Service",
        jwt_issuer="graph-sports",
    ),
    view_extension=SPORTS_VIEW_CONFIG,
    feature_flags=SPORTS_FEATURE_FLAGS,
    dictionary_loading_extension=SPORTS_DICTIONARY_LOADING_CONFIG,
    domain_context_policy=SPORTS_DOMAIN_CONTEXT_POLICY,
    agent_capabilities=SPORTS_AGENT_CAPABILITIES,
    relation_suggestion_extension=GraphRelationSuggestionConfig(),
    relation_autopromotion_defaults=RelationAutopromotionDefaults(),
)


def create_graph_domain_pack() -> GraphDomainPack:
    """Return the sports example runtime pack."""
    return SPORTS_GRAPH_DOMAIN_PACK


__all__ = [
    "SPORTS_AGENT_CAPABILITIES",
    "SPORTS_DICTIONARY_LOADING_CONFIG",
    "SPORTS_DOMAIN_CONTEXT_POLICY",
    "SPORTS_GRAPH_DOMAIN_PACK",
    "SPORTS_VIEW_CONFIG",
    "create_graph_domain_pack",
]
