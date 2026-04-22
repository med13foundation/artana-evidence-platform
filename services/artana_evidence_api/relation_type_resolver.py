"""AI-powered relation type and entity resolution for the evidence API.

Uses the ArtanaKernel agent with full graph tool access to resolve unknown
relation types and entity labels with research-space context.

**Relation types** — When the LLM extraction step produces a relation type not
in the known dictionary (e.g. typos like ``REPRESSS`` or novel types like
``PROTECTS_AGAINST``), the agent queries the graph dictionary and decides:

1. **map_to_existing** — synonym / variant of an existing canonical type.
2. **typo_correction** — misspelling of an existing type.
3. **register_new** — genuinely new concept to add to the dictionary.

**Entities** — When a candidate entity label cannot be matched deterministically,
the agent uses graph tools (``suggest_relations``, ``list_claims_by_entity``,
entity search) to decide:

1. **match_existing** — the label is a synonym / alias of an existing entity.
2. **create_new** — the label represents a genuinely new entity.

Resolution results are cached in-process so the same unknown type / label is
never evaluated twice during a single server lifetime.
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from contextlib import suppress
from enum import Enum
from typing import TYPE_CHECKING, Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from uuid import UUID

    from artana_evidence_api.graph_client import GraphTransportBundle

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Heuristic entity type inference (fallback when LLM is unavailable)
# ═══════════════════════════════════════════════════════════════════════════

# Well-known HGNC gene symbols and common biomedical terms.
_KNOWN_GENE_SYMBOLS = frozenset(
    {
        "TP53",
        "BRCA1",
        "BRCA2",
        "EGFR",
        "KRAS",
        "BRAF",
        "MYC",
        "RB1",
        "PTEN",
        "PIK3CA",
        "AKT1",
        "CDKN2A",
        "NF1",
        "NF2",
        "KDR",
        "VEGFR2",
        "PTPRB",
        "PLCG1",
        "FLT1",
        "FLT4",
        "PDGFRA",
        "KIT",
        "ALK",
        "ROS1",
        "MET",
        "RET",
        "FGFR1",
        "FGFR2",
        "FGFR3",
        "JAK2",
        "IDH1",
        "IDH2",
        "ARID1A",
        "ATM",
        "ERBB2",
        "HER2",
        "APC",
        "VHL",
        "WT1",
        "MDM2",
        "SNCA",
        "LRRK2",
        "PARK2",
        "GBA",
        "SOD1",
        "FUS",
        "TARDBP",
        "HTT",
        "CFTR",
        "SMN1",
        "DMD",
        "FMR1",
    },
)

_DRUG_SUFFIXES = (
    "nib",
    "mab",
    "zumab",
    "ximab",
    "tinib",
    "rafenib",
    "ciclib",
    "lisib",
    "parin",
    "statin",
    "olol",
    "pril",
    "sartan",
    "floxacin",
    "mycin",
    "cillin",
    "azole",
    "vir",
    "navir",
    "previr",
)

_DISEASE_SUFFIXES = (
    "oma",
    "emia",
    "itis",
    "osis",
    "pathy",
    "trophy",
    "plasia",
    "ectomy",
)

_PATHWAY_KEYWORDS = frozenset(
    {
        "pathway",
        "signaling",
        "cascade",
        "axis",
        "network",
    },
)


_MAX_GENE_SYMBOL_LENGTH = 10


def _infer_entity_type_heuristic(label: str) -> str:  # noqa: PLR0911
    """Infer the most likely entity type from a label using simple heuristics.

    Used as a fallback when the LLM agent is unavailable or when there are
    no candidate entities to resolve against.  Returns UPPER_SNAKE_CASE
    entity type strings matching the graph schema.
    """
    normalized = label.strip()
    upper = normalized.upper()
    lower = normalized.lower()

    # Gene symbols: uppercase alphanumeric, 2-8 chars (e.g. TP53, BRCA1)
    if upper in _KNOWN_GENE_SYMBOLS:
        return "GENE"
    if (
        len(normalized) <= _MAX_GENE_SYMBOL_LENGTH
        and normalized.isascii()
        and normalized == upper
        and any(c.isalpha() for c in normalized)
        and any(c.isdigit() for c in normalized)
    ):
        return "GENE"

    # Drug names: characteristic suffixes
    for suffix in _DRUG_SUFFIXES:
        if lower.endswith(suffix):
            return "DRUG"

    # Pathway keywords
    if any(kw in lower for kw in _PATHWAY_KEYWORDS):
        return "SIGNALING_PATHWAY"

    # Disease names: characteristic suffixes
    for suffix in _DISEASE_SUFFIXES:
        if lower.endswith(suffix) and len(normalized) > len(suffix) + 2:
            return "DISEASE"

    # Syndrome
    if "syndrome" in lower:
        return "SYNDROME"

    # Default to PHENOTYPE for genuinely ambiguous labels
    return "PHENOTYPE"


# ═══════════════════════════════════════════════════════════════════════════
# Shared: ArtanaKernel agent runner
# ═══════════════════════════════════════════════════════════════════════════


async def _run_kernel_agent(
    *,
    system_prompt: str,
    prompt: str,
    output_schema: type[BaseModel],
    run_id_prefix: str,
    tenant_id: str,
    budget_usd: float = 0.50,
    timeout_seconds: float = 60.0,
    max_iterations: int = 3,
) -> BaseModel:
    """Run a full ArtanaKernel agent with graph tool access.

    The agent has access to the complete graph harness tool registry
    (``suggest_relations``, ``list_graph_claims``, ``list_claims_by_entity``,
    entity search, etc.) so it can query the graph for context before making
    resolution decisions.
    """
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
    from artana.ports.model import LiteLLMAdapter
    from artana_evidence_api.composition import (
        build_graph_harness_kernel_middleware,
    )
    from artana_evidence_api.policy import build_graph_harness_policy
    from artana_evidence_api.runtime_skill_agent import (
        GraphHarnessSkillAutonomousAgent,
        GraphHarnessSkillContextBuilder,
    )
    from artana_evidence_api.runtime_skill_registry import (
        load_graph_harness_skill_registry,
    )
    from artana_evidence_api.runtime_support import (
        ModelCapability,
        create_artana_postgres_store,
        get_model_registry,
        normalize_litellm_model_id,
    )
    from artana_evidence_api.tool_registry import (
        build_graph_harness_tool_registry,
    )

    registry = get_model_registry()
    model_spec = registry.get_default_model(ModelCapability.CURATION)
    model_id = normalize_litellm_model_id(model_spec.model_id)

    kernel: ArtanaKernel | None = None
    store = None

    skill_registry = load_graph_harness_skill_registry()
    context_builder = GraphHarnessSkillContextBuilder(
        skill_registry=skill_registry,
        preloaded_skill_names=(),
        identity="You are a biomedical knowledge-graph ontology expert.",
        task_category="ontology_resolution",
    )

    tenant = TenantContext(
        tenant_id=tenant_id,
        capabilities=frozenset(),
        budget_usd_limit=budget_usd,
    )

    run_id = f"{run_id_prefix}:{uuid4()}"

    try:
        store = create_artana_postgres_store()
        kernel = ArtanaKernel(
            store=store,
            model_port=LiteLLMAdapter(timeout_seconds=timeout_seconds),
            tool_port=build_graph_harness_tool_registry(),
            middleware=build_graph_harness_kernel_middleware(),
            policy=build_graph_harness_policy(),
        )
        agent = GraphHarnessSkillAutonomousAgent(
            kernel,
            skill_registry=skill_registry,
            preloaded_skill_names=(),
            allowed_skill_names=(),
            context_builder=context_builder,
            replay_policy="fork_on_drift",
        )
        contract = await agent.run(
            run_id=run_id,
            tenant=tenant,
            model=model_id,
            system_prompt=system_prompt,
            prompt=prompt,
            output_schema=output_schema,
            max_iterations=max_iterations,
        )
        return (
            contract
            if isinstance(contract, output_schema)
            else output_schema.model_validate(contract)
        )
    finally:
        if kernel is not None:
            with suppress(Exception):
                await kernel.close()
        if store is not None:
            with suppress(Exception):
                await store.close()


# ═══════════════════════════════════════════════════════════════════════════
# RELATION TYPE RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════

# ---------------------------------------------------------------------------
# Decision schema
# ---------------------------------------------------------------------------


class RelationTypeAction(str, Enum):
    MAP_TO_EXISTING = "map_to_existing"
    REGISTER_NEW = "register_new"
    TYPO_CORRECTION = "typo_correction"


class RelationTypeDecision(BaseModel):
    """Structured output from the kernel agent relation-type resolver."""

    model_config = ConfigDict(strict=True)

    action: RelationTypeAction
    canonical_type: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description=(
            "The resolved canonical relation type ID (UPPER_SNAKE_CASE). "
            "For map_to_existing / typo_correction this is the existing type. "
            "For register_new this is the clean new type to register."
        ),
    )
    reasoning: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Brief justification for the decision.",
    )


# ---------------------------------------------------------------------------
# In-process cache (bounded to prevent unbounded memory growth)
# ---------------------------------------------------------------------------

_RELATION_CACHE_MAX_SIZE = 2000
_ENTITY_CACHE_MAX_SIZE = 5000


_V = TypeVar("_V")


class _BoundedCache(Generic[_V]):
    """Dict-like cache that evicts the oldest entry when ``maxsize`` is reached."""

    def __init__(self, maxsize: int) -> None:
        self._maxsize = maxsize
        self._data: OrderedDict[str, _V] = OrderedDict()

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __getitem__(self, key: str) -> _V:
        return self._data[key]

    def __setitem__(self, key: str, value: _V) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        if len(self._data) > self._maxsize:
            self._data.popitem(last=False)

    def get(self, key: str) -> _V | None:
        return self._data.get(key)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


_relation_cache: _BoundedCache[RelationTypeDecision] = _BoundedCache(
    _RELATION_CACHE_MAX_SIZE,
)


def _relation_cache_key(relation_type: str, space_id: str | None = None) -> str:
    normalized = relation_type.strip().upper().replace(" ", "_")
    if isinstance(space_id, str) and space_id.strip():
        return f"{space_id.strip()}:{normalized}"
    return f"*:{normalized}"


def clear_relation_cache() -> None:
    """Clear the in-process relation type resolution cache."""
    _relation_cache.clear()


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_RELATION_RESOLUTION_SYSTEM_PROMPT = """\
You are a biomedical knowledge-graph ontology expert working inside the
ArtanaKernel. Your task is to resolve an UNKNOWN relation type that was
extracted from a scientific paper.

You have access to graph tools. Use them to understand the current state of
the knowledge graph:
- Use ``suggest_relations`` to see what relation types the dictionary supports
  between different entity types.
- Use ``list_graph_claims`` to see examples of how existing relation types
  are used in practice.

After examining the graph context, decide ONE of:

• **map_to_existing** — The unknown type is semantically equivalent to (or a
  common synonym / abbreviation of) an existing canonical type. Set
  ``canonical_type`` to that existing type's ID.

• **typo_correction** — The unknown type is clearly a misspelling of an
  existing type (e.g. ``REPRESSS`` → ``REPRESSES``, ``ASSOCATED_WITH`` →
  ``ASSOCIATED_WITH``). Set ``canonical_type`` to the correctly-spelled
  existing type.

• **register_new** — The unknown type represents a genuinely distinct
  relationship concept not covered by ANY existing type. Set
  ``canonical_type`` to a clean UPPER_SNAKE_CASE identifier.

Guidelines:
- Prefer mapping to existing types whenever the semantic overlap is ≥80%.
- Only choose register_new when the relationship truly has no adequate
  existing representation.
- For typo_correction, you must be certain the intended word is an existing
  type — not a new concept with a coincidental resemblance.
"""


# ---------------------------------------------------------------------------
# Core resolution function
# ---------------------------------------------------------------------------


async def resolve_relation_type(
    unknown_type: str,
    *,
    known_types: list[str],
    space_context: str = "",
    space_id: str | None = None,
    live_candidate_types: list[str] | None = None,
    live_relation_synonyms: list[str] | None = None,
    allowed_relation_suggestions: list[str] | None = None,
) -> RelationTypeDecision:
    """Resolve a single unknown relation type using the ArtanaKernel agent."""
    normalized = unknown_type.strip().upper().replace(" ", "_")
    cache_key = _relation_cache_key(unknown_type, space_id)

    # Fast path: cache hit
    if cache_key in _relation_cache:
        return _relation_cache[cache_key]

    # Fast path: already a known type
    if normalized in {t.strip().upper() for t in known_types}:
        decision = RelationTypeDecision(
            action=RelationTypeAction.MAP_TO_EXISTING,
            canonical_type=normalized,
            reasoning="Already a known canonical relation type.",
        )
        _relation_cache[cache_key] = decision
        return decision

    # Build prompt with context
    known_types_block = "\n".join(f"  • {t}" for t in sorted(known_types))
    context_block = f"\nRESEARCH CONTEXT:\n{space_context}\n" if space_context else ""
    candidate_types_block = ""
    if live_candidate_types:
        candidate_types_block = (
            "\nACTIVE GRAPH RELATION TYPE CANDIDATES:\n"
            + "\n".join(f"  • {item}" for item in sorted(set(live_candidate_types)))
            + "\n"
        )
    synonym_block = ""
    if live_relation_synonyms:
        synonym_block = (
            "\nACTIVE GRAPH RELATION SYNONYMS:\n"
            + "\n".join(f"  • {item}" for item in sorted(set(live_relation_synonyms)))
            + "\n"
        )
    allowed_block = ""
    if allowed_relation_suggestions:
        allowed_block = (
            "\nALLOWED RELATION SUGGESTIONS FOR THE CURRENT TRIPLE:\n"
            + "\n".join(
                f"  • {item}" for item in sorted(set(allowed_relation_suggestions))
            )
            + "\n"
        )
    prompt = (
        f"CANONICAL RELATION TYPES IN DICTIONARY:\n{known_types_block}\n"
        f"{candidate_types_block}"
        f"{synonym_block}"
        f"{allowed_block}"
        f"{context_block}\n"
        f"UNKNOWN RELATION TYPE TO RESOLVE: {normalized}\n\n"
        f"Use your graph tools to examine how existing relation types are used, "
        f"then return your decision as JSON."
    )

    try:
        raw = await _run_kernel_agent(
            system_prompt=_RELATION_RESOLUTION_SYSTEM_PROMPT,
            prompt=prompt,
            output_schema=RelationTypeDecision,
            run_id_prefix="relation-type-resolution",
            tenant_id="relation-type-resolution",
            max_iterations=3,
        )
        decision = (
            raw
            if isinstance(raw, RelationTypeDecision)
            else RelationTypeDecision.model_validate(raw)
        )

    except Exception:
        logger.exception(
            "Failed to resolve relation type '%s' via kernel agent, "
            "passing through as-is",
            normalized,
        )
        fallback = RelationTypeDecision(
            action=RelationTypeAction.REGISTER_NEW,
            canonical_type=normalized,
            reasoning="Kernel agent resolution failed; defaulting to register_new.",
        )
        _relation_cache[cache_key] = fallback
        return fallback

    decision = decision.model_copy(
        update={
            "canonical_type": decision.canonical_type.strip().upper().replace(" ", "_"),
        },
    )

    _relation_cache[cache_key] = decision
    logger.info(
        "Relation type resolved: %s → %s (%s) — %s",
        normalized,
        decision.canonical_type,
        decision.action.value,
        decision.reasoning,
    )
    return decision


# ---------------------------------------------------------------------------
# Batch resolution
# ---------------------------------------------------------------------------


async def resolve_relation_types_batch(
    unknown_types: list[str],
    *,
    known_types: list[str],
    space_context: str = "",
    space_id: str | None = None,
    live_candidate_types: list[str] | None = None,
    live_relation_synonyms: list[str] | None = None,
    allowed_relation_suggestions: list[str] | None = None,
) -> dict[str, RelationTypeDecision]:
    """Resolve multiple unknown relation types (deduplicates + caches)."""
    results: dict[str, RelationTypeDecision] = {}
    to_resolve: list[str] = []

    for raw in unknown_types:
        key = _relation_cache_key(raw, space_id)
        if key in _relation_cache:
            results[key] = _relation_cache[key]
        elif key not in {_relation_cache_key(t, space_id) for t in to_resolve}:
            to_resolve.append(raw)

    for raw in to_resolve:
        decision = await resolve_relation_type(
            raw,
            known_types=known_types,
            space_context=space_context,
            space_id=space_id,
            live_candidate_types=live_candidate_types,
            live_relation_synonyms=live_relation_synonyms,
            allowed_relation_suggestions=allowed_relation_suggestions,
        )
        results[_relation_cache_key(raw, space_id)] = decision

    return results


# ═══════════════════════════════════════════════════════════════════════════
# ENTITY RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════

# ---------------------------------------------------------------------------
# Decision schema
# ---------------------------------------------------------------------------


class EntityAction(str, Enum):
    MATCH_EXISTING = "match_existing"
    CREATE_NEW = "create_new"


class EntityDecision(BaseModel):
    """Structured output from the kernel agent entity resolver."""

    model_config = ConfigDict(strict=True)

    action: EntityAction
    matched_entity_id: str | None = Field(
        default=None,
        description=(
            "The ID of the existing entity this label matches. "
            "Required when action is match_existing, null otherwise."
        ),
    )
    matched_entity_label: str | None = Field(
        default=None,
        description=(
            "The display_label of the matched entity for logging. "
            "Required when action is match_existing, null otherwise."
        ),
    )
    entity_type: str | None = Field(
        default=None,
        description=(
            "Suggested entity type when creating a new entity "
            "(UPPER_SNAKE_CASE, e.g. GENE, PROTEIN, DISEASE). "
            "Required when action is create_new, null otherwise."
        ),
    )
    reasoning: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Brief justification for the decision.",
    )


# ---------------------------------------------------------------------------
# In-process cache
# ---------------------------------------------------------------------------

_entity_cache: _BoundedCache[EntityDecision] = _BoundedCache(_ENTITY_CACHE_MAX_SIZE)


def _entity_cache_key(label: str, space_id: str) -> str:
    return f"{space_id}:{label.strip().casefold()}"


def clear_entity_cache() -> None:
    """Clear the in-process entity resolution cache."""
    _entity_cache.clear()


def clear_all_caches() -> None:
    """Clear all resolution caches (useful for tests)."""
    clear_relation_cache()
    clear_entity_cache()


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_ENTITY_RESOLUTION_SYSTEM_PROMPT = """\
You are a biomedical knowledge-graph entity resolution expert working inside
the ArtanaKernel. Your task is to decide whether a newly extracted entity label
matches an EXISTING entity in the graph or should be created as a new entity.

You have access to graph tools. Use them to investigate:
- Use ``list_claims_by_entity`` to see how candidate entities participate in
  existing claims — this reveals context about what each entity represents.
- Use ``suggest_relations`` to see what relation types are valid between
  entity types — this helps confirm entity type assignment.
- Use ``list_graph_claims`` to understand the broader graph context.

You will also be given a list of candidate entities returned by the graph
search. After examining them with tools, decide ONE of:

• **match_existing** — The extracted label refers to the SAME real-world
  entity as one of the candidates. Common cases:
  - Synonyms: "alpha-synuclein" ↔ "SNCA"
  - Abbreviations: "PD" ↔ "Parkinson's Disease"
  - Case / spelling variants: "TP53" ↔ "p53"
  - Full name vs symbol: "tumor protein p53" ↔ "TP53"
  Set ``matched_entity_id`` to the ID of the matching entity.

• **create_new** — The label refers to an entity that does NOT exist in the
  graph yet. Set ``entity_type`` to the most appropriate type
  (GENE, PROTEIN, DISEASE, DRUG, PHENOTYPE, SYNDROME, SIGNALING_PATHWAY,
  PROTEIN_COMPLEX, MOLECULAR_FUNCTION, VARIANT, PUBLICATION, or a new type
  in UPPER_SNAKE_CASE).

Guidelines:
- In biomedical contexts, gene symbols and protein names often refer to the
  same entity (e.g. BRCA1 the gene and BRCA1 the protein). Match them unless
  the distinction is critical.
- Prefer matching to existing entities when there is strong semantic overlap.
- Only choose create_new when you are confident the entity is genuinely absent.
- Consider aliases carefully — an entity might have a display_label that
  looks different but be the same thing (e.g. "CDK8 module" and "CKM").
"""


# ---------------------------------------------------------------------------
# Core resolution function
# ---------------------------------------------------------------------------


async def resolve_entity_label(
    label: str,
    *,
    space_id: str,
    candidate_entities: list[dict[str, str | list[str]]],
    space_context: str = "",
) -> EntityDecision:
    """Resolve a single entity label against existing graph entities.

    Uses the ArtanaKernel agent with graph tool access to make an informed
    decision based on the actual graph content.
    """
    cache_key = _entity_cache_key(label, space_id)

    if cache_key in _entity_cache:
        return _entity_cache[cache_key]

    # If there are no candidates at all, skip the agent call
    if not candidate_entities:
        inferred_type = _infer_entity_type_heuristic(label)
        decision = EntityDecision(
            action=EntityAction.CREATE_NEW,
            entity_type=inferred_type,
            reasoning=f"No candidate entities found in graph; inferred type '{inferred_type}' from label heuristic.",
        )
        _entity_cache[cache_key] = decision
        return decision

    # Build candidates block
    entities_lines: list[str] = []
    for ent in candidate_entities:
        aliases = ent.get("aliases", [])
        alias_str = f" (aliases: {', '.join(aliases)})" if aliases else ""
        entities_lines.append(
            f'  • ID={ent["id"]}  label="{ent["display_label"]}"  '
            f'type={ent.get("entity_type", "UNKNOWN")}{alias_str}',
        )
    entities_block = "\n".join(entities_lines)

    context_block = f"\nRESEARCH CONTEXT:\n{space_context}\n" if space_context else ""

    prompt = (
        f"EXISTING ENTITIES IN GRAPH (from search):\n{entities_block}\n"
        f"{context_block}\n"
        f'EXTRACTED LABEL TO RESOLVE: "{label}"\n'
        f"SPACE ID: {space_id}\n\n"
        f"Use your graph tools (e.g. list_claims_by_entity) to examine the "
        f"candidate entities and understand what they represent, then return "
        f"your decision as JSON."
    )

    try:
        raw = await _run_kernel_agent(
            system_prompt=_ENTITY_RESOLUTION_SYSTEM_PROMPT,
            prompt=prompt,
            output_schema=EntityDecision,
            run_id_prefix="entity-resolution",
            tenant_id="entity-resolution",
            max_iterations=3,
        )
        decision = (
            raw
            if isinstance(raw, EntityDecision)
            else EntityDecision.model_validate(raw)
        )

        # Normalize entity_type if present
        if decision.entity_type:
            decision = decision.model_copy(
                update={
                    "entity_type": decision.entity_type.strip()
                    .upper()
                    .replace(" ", "_"),
                },
            )

    except Exception:
        logger.exception(
            "Failed to resolve entity '%s' via kernel agent, "
            "defaulting to create_new",
            label,
        )
        inferred_type = _infer_entity_type_heuristic(label)
        fallback = EntityDecision(
            action=EntityAction.CREATE_NEW,
            entity_type=inferred_type,
            reasoning=f"Kernel agent resolution failed; inferred type '{inferred_type}' from label heuristic.",
        )
        _entity_cache[cache_key] = fallback
        return fallback

    _entity_cache[cache_key] = decision
    if decision.action == EntityAction.MATCH_EXISTING:
        logger.info(
            "Entity resolved: '%s' → existing '%s' (id=%s) — %s",
            label,
            decision.matched_entity_label,
            decision.matched_entity_id,
            decision.reasoning,
        )
    else:
        logger.info(
            "Entity resolved: '%s' → create_new (type=%s) — %s",
            label,
            decision.entity_type,
            decision.reasoning,
        )
    return decision


# ---------------------------------------------------------------------------
# Integration helper: wraps graph search + kernel agent resolution
# ---------------------------------------------------------------------------


async def resolve_entity_with_ai(  # noqa: PLR0911
    *,
    space_id: UUID | str,
    label: str,
    graph_api_gateway: GraphTransportBundle,
    space_context: str = "",
) -> dict[str, str] | None:
    """Search the graph for an entity label, using the kernel agent to
    disambiguate.

    Returns a dict with ``id`` and ``display_label`` if matched to an existing
    entity, or ``None`` if the entity should be created as new.

    This replaces the deterministic 3-tier matching in
    ``resolve_graph_entity_label`` with AI-powered semantic matching backed
    by graph tool access.
    """
    from artana_evidence_api.graph_client import GraphServiceClientError

    sid = str(space_id)

    # Check cache first
    cache_key = _entity_cache_key(label, sid)
    if cache_key in _entity_cache:
        cached = _entity_cache[cache_key]
        if cached.action == EntityAction.MATCH_EXISTING and cached.matched_entity_id:
            return {
                "id": cached.matched_entity_id,
                "display_label": cached.matched_entity_label or label,
            }
        return None

    # Search graph for candidates
    try:
        response = await asyncio.to_thread(
            graph_api_gateway.list_entities,
            space_id=space_id,
            q=label,
            limit=10,
        )
    except GraphServiceClientError:
        return None

    if not response.entities:
        # No candidates — skip agent call, cache the decision
        inferred_type = _infer_entity_type_heuristic(label)
        decision = EntityDecision(
            action=EntityAction.CREATE_NEW,
            entity_type=inferred_type,
            reasoning=f"No candidate entities found in graph search; inferred type '{inferred_type}' from label heuristic.",
        )
        _entity_cache[cache_key] = decision
        return None

    # Quick exact-match shortcut (saves an agent call for obvious matches)
    normalized_label = label.strip().casefold()
    for entity in response.entities:
        display_label = entity.display_label or ""
        exact_aliases = {alias.casefold() for alias in entity.aliases}
        if (
            display_label.casefold() == normalized_label
            or normalized_label in exact_aliases
        ):
            decision = EntityDecision(
                action=EntityAction.MATCH_EXISTING,
                matched_entity_id=str(entity.id),
                matched_entity_label=display_label or str(entity.id),
                reasoning="Exact label or alias match (deterministic).",
            )
            _entity_cache[cache_key] = decision
            return {
                "id": str(entity.id),
                "display_label": display_label or str(entity.id),
            }

    # Build candidate list for kernel agent resolution
    candidate_entities = [
        {
            "id": str(entity.id),
            "display_label": entity.display_label or str(entity.id),
            "entity_type": entity.entity_type or "UNKNOWN",
            "aliases": list(entity.aliases),
        }
        for entity in response.entities
    ]

    decision = await resolve_entity_label(
        label,
        space_id=sid,
        candidate_entities=candidate_entities,
        space_context=space_context,
    )

    if decision.action == EntityAction.MATCH_EXISTING and decision.matched_entity_id:
        return {
            "id": decision.matched_entity_id,
            "display_label": decision.matched_entity_label or label,
        }

    return None
