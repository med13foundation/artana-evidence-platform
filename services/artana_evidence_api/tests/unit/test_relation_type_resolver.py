"""Regression tests for AI-powered relation type and entity resolution.

Tests the decision schemas, caching behaviour, and integration helpers
without requiring a live LLM or graph API — all external calls are mocked.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from artana_evidence_api import runtime_support
from artana_evidence_api.relation_type_resolver import (
    EntityAction,
    EntityDecision,
    RelationTypeAction,
    RelationTypeDecision,
    _entity_cache,
    _entity_cache_key,
    _relation_cache,
    _relation_cache_key,
    _run_kernel_agent,
    clear_all_caches,
    clear_entity_cache,
    clear_relation_cache,
    resolve_entity_with_ai,
)
from artana_evidence_api.types.graph_contracts import (
    KernelEntityListResponse,
    KernelEntityResponse,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_caches():
    """Ensure caches are clean before and after each test."""
    clear_all_caches()
    yield
    clear_all_caches()


class _FakeKernelStore:
    def __init__(self) -> None:
        self.closed = False
        self.kernel: _FakeKernel | None = None

    async def close(self) -> None:
        self.closed = True


class _FakeKernel:
    def __init__(self, *, store, model_port, tool_port=None, middleware=None, policy=None) -> None:  # type: ignore[no-untyped-def]
        del tool_port, middleware, policy
        self.store = store
        self.model_port = model_port
        self.closed = False
        store.kernel = self

    async def close(self) -> None:
        self.closed = True


class _FakeGraphHarnessSkillContextBuilder:
    def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.kwargs = kwargs


class _FakeGraphHarnessSkillAutonomousAgent:
    run_result: object = SimpleNamespace(
        action=RelationTypeAction.REGISTER_NEW,
        canonical_type="FAKE",
        reasoning="synthetic resolution",
    )
    run_exc: Exception | None = None

    def __init__(self, kernel, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.kernel = kernel
        self.kwargs = kwargs

    async def run(self, **kwargs):  # type: ignore[no-untyped-def]
        self.kwargs.update(kwargs)
        if self.__class__.run_exc is not None:
            raise self.__class__.run_exc
        return self.__class__.run_result


# ---------------------------------------------------------------------------
# Decision schema tests
# ---------------------------------------------------------------------------


class TestRelationTypeDecision:
    def test_map_to_existing(self):
        d = RelationTypeDecision(
            action=RelationTypeAction.MAP_TO_EXISTING,
            canonical_type="INHIBITS",
            reasoning="REPRESSS is a typo of REPRESSES which maps to INHIBITS.",
        )
        assert d.action == RelationTypeAction.MAP_TO_EXISTING
        assert d.canonical_type == "INHIBITS"

    def test_typo_correction(self):
        d = RelationTypeDecision(
            action=RelationTypeAction.TYPO_CORRECTION,
            canonical_type="REPRESSES",
            reasoning="REPRESSS has 3 S's, likely typo of REPRESSES.",
        )
        assert d.action == RelationTypeAction.TYPO_CORRECTION
        assert d.canonical_type == "REPRESSES"

    def test_register_new(self):
        d = RelationTypeDecision(
            action=RelationTypeAction.REGISTER_NEW,
            canonical_type="PROTECTS_AGAINST",
            reasoning="Genuinely new concept not covered by existing types.",
        )
        assert d.action == RelationTypeAction.REGISTER_NEW

    def test_canonical_type_min_length(self):
        with pytest.raises(Exception):
            RelationTypeDecision(
                action=RelationTypeAction.MAP_TO_EXISTING,
                canonical_type="",
                reasoning="Empty type.",
            )


class TestEntityDecision:
    def test_match_existing(self):
        d = EntityDecision(
            action=EntityAction.MATCH_EXISTING,
            matched_entity_id="11111111-1111-1111-1111-111111111111",
            matched_entity_label="SNCA",
            reasoning="alpha-synuclein is the protein encoded by SNCA.",
        )
        assert d.action == EntityAction.MATCH_EXISTING
        assert d.matched_entity_id == "11111111-1111-1111-1111-111111111111"

    def test_create_new(self):
        d = EntityDecision(
            action=EntityAction.CREATE_NEW,
            entity_type="PROTEIN",
            reasoning="Not found in the graph.",
        )
        assert d.action == EntityAction.CREATE_NEW
        assert d.entity_type == "PROTEIN"
        assert d.matched_entity_id is None


# ---------------------------------------------------------------------------
# Cache key tests
# ---------------------------------------------------------------------------


class TestCacheKeys:
    def test_relation_cache_key_normalizes(self):
        assert _relation_cache_key("  represss  ") == "*:REPRESSS"
        assert _relation_cache_key("protects against") == "*:PROTECTS_AGAINST"
        assert _relation_cache_key("INHIBITS") == "*:INHIBITS"
        assert _relation_cache_key("INHIBITS", "space-1") == "space-1:INHIBITS"

    def test_entity_cache_key_includes_space(self):
        key = _entity_cache_key("alpha-synuclein", "space-1")
        assert key == "space-1:alpha-synuclein"
        # Case-insensitive
        assert _entity_cache_key("BRCA1", "s") == _entity_cache_key("brca1", "s")

    def test_clear_relation_cache(self):
        _relation_cache["TEST"] = RelationTypeDecision(
            action=RelationTypeAction.MAP_TO_EXISTING,
            canonical_type="TEST",
            reasoning="test",
        )
        assert len(_relation_cache) == 1
        clear_relation_cache()
        assert len(_relation_cache) == 0

    def test_clear_entity_cache(self):
        _entity_cache["s:test"] = EntityDecision(
            action=EntityAction.CREATE_NEW,
            entity_type="GENE",
            reasoning="test",
        )
        assert len(_entity_cache) == 1
        clear_entity_cache()
        assert len(_entity_cache) == 0

    def test_clear_all_caches(self):
        _relation_cache["R"] = RelationTypeDecision(
            action=RelationTypeAction.REGISTER_NEW,
            canonical_type="R",
            reasoning="test",
        )
        _entity_cache["s:e"] = EntityDecision(
            action=EntityAction.CREATE_NEW,
            entity_type="GENE",
            reasoning="test",
        )
        clear_all_caches()
        assert len(_relation_cache) == 0
        assert len(_entity_cache) == 0


# ---------------------------------------------------------------------------
# Relation cache hit tests (no LLM call)
# ---------------------------------------------------------------------------


class TestRelationCacheHit:
    @pytest.mark.asyncio
    async def test_cached_decision_returned_without_agent_call(self):
        from artana_evidence_api.relation_type_resolver import resolve_relation_type

        # Pre-populate cache
        _relation_cache[_relation_cache_key("REPRESSS")] = RelationTypeDecision(
            action=RelationTypeAction.TYPO_CORRECTION,
            canonical_type="REPRESSES",
            reasoning="Cached typo correction.",
        )

        # Should return from cache without calling any agent
        result = await resolve_relation_type(
            "REPRESSS",
            known_types=["INHIBITS", "ACTIVATES"],
        )
        assert result.action == RelationTypeAction.TYPO_CORRECTION
        assert result.canonical_type == "REPRESSES"

    @pytest.mark.asyncio
    async def test_known_type_returns_map_to_existing_without_agent(self):
        from artana_evidence_api.relation_type_resolver import resolve_relation_type

        result = await resolve_relation_type(
            "INHIBITS",
            known_types=["INHIBITS", "ACTIVATES", "CAUSES"],
        )
        assert result.action == RelationTypeAction.MAP_TO_EXISTING
        assert result.canonical_type == "INHIBITS"
        # Should be cached now
        assert _relation_cache_key("INHIBITS") in _relation_cache


# ---------------------------------------------------------------------------
# Relation batch tests
# ---------------------------------------------------------------------------


class TestRelationBatch:
    @pytest.mark.asyncio
    async def test_batch_deduplicates_and_uses_cache(self):
        from artana_evidence_api.relation_type_resolver import (
            resolve_relation_types_batch,
        )

        # Pre-populate one
        _relation_cache[_relation_cache_key("REPRESSS")] = RelationTypeDecision(
            action=RelationTypeAction.TYPO_CORRECTION,
            canonical_type="REPRESSES",
            reasoning="Cached.",
        )

        # Only UNKNOWN_TYPE should need resolution; mock the agent call
        mock_decision = RelationTypeDecision(
            action=RelationTypeAction.REGISTER_NEW,
            canonical_type="UNKNOWN_TYPE",
            reasoning="Genuinely new.",
        )

        with patch(
            "artana_evidence_api.relation_type_resolver._run_kernel_agent",
            new_callable=AsyncMock,
            return_value=mock_decision,
        ) as mock_agent:
            results = await resolve_relation_types_batch(
                ["REPRESSS", "UNKNOWN_TYPE", "represss"],  # duplicate
                known_types=["INHIBITS"],
        )

        # Should have called agent only once (for UNKNOWN_TYPE)
        assert mock_agent.call_count == 1
        assert results[_relation_cache_key("REPRESSS")].canonical_type == "REPRESSES"
        assert results[_relation_cache_key("UNKNOWN_TYPE")].canonical_type == "UNKNOWN_TYPE"
        assert (
            results[_relation_cache_key("UNKNOWN_TYPE")].action
            == RelationTypeAction.REGISTER_NEW
        )


# ---------------------------------------------------------------------------
# Relation agent fallback on error
# ---------------------------------------------------------------------------


class TestRelationAgentFallback:
    @pytest.mark.asyncio
    async def test_agent_failure_falls_back_to_register_new(self):
        from artana_evidence_api.relation_type_resolver import resolve_relation_type

        with patch(
            "artana_evidence_api.relation_type_resolver._run_kernel_agent",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Agent unavailable"),
        ):
            result = await resolve_relation_type(
                "BRAND_NEW_TYPE",
                known_types=["INHIBITS"],
            )

        assert result.action == RelationTypeAction.REGISTER_NEW
        assert result.canonical_type == "BRAND_NEW_TYPE"
        assert "failed" in result.reasoning.lower()
        # Should be cached even on failure
        assert _relation_cache_key("BRAND_NEW_TYPE") in _relation_cache


@pytest.mark.asyncio
async def test_run_kernel_agent_uses_fresh_store_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_stores: list[_FakeKernelStore] = []

    def _create_store() -> _FakeKernelStore:
        store = _FakeKernelStore()
        created_stores.append(store)
        return store

    _FakeGraphHarnessSkillAutonomousAgent.run_result = RelationTypeDecision(
        action=RelationTypeAction.REGISTER_NEW,
        canonical_type="fresh_store_test",
        reasoning="synthetic resolution",
    )
    _FakeGraphHarnessSkillAutonomousAgent.run_exc = None

    monkeypatch.setattr(runtime_support, "create_artana_postgres_store", _create_store)
    monkeypatch.setattr(
        runtime_support,
        "get_model_registry",
        lambda: SimpleNamespace(
            get_default_model=lambda _capability: SimpleNamespace(
                model_id="openai:gpt-5.4-mini",
                timeout_seconds=60.0,
            ),
        ),
    )
    monkeypatch.setattr(
        runtime_support,
        "normalize_litellm_model_id",
        lambda model_id: model_id,
    )
    monkeypatch.setattr("artana.kernel.ArtanaKernel", _FakeKernel)
    monkeypatch.setattr(
        "artana_evidence_api.composition.build_graph_harness_kernel_middleware",
        lambda: (),
    )
    monkeypatch.setattr(
        "artana_evidence_api.policy.build_graph_harness_policy",
        lambda: object(),
    )
    monkeypatch.setattr(
        "artana_evidence_api.tool_registry.build_graph_harness_tool_registry",
        lambda: object(),
    )
    monkeypatch.setattr(
        "artana_evidence_api.runtime_skill_registry.load_graph_harness_skill_registry",
        lambda: object(),
    )
    monkeypatch.setattr(
        "artana_evidence_api.runtime_skill_agent.GraphHarnessSkillContextBuilder",
        _FakeGraphHarnessSkillContextBuilder,
    )
    monkeypatch.setattr(
        "artana_evidence_api.runtime_skill_agent.GraphHarnessSkillAutonomousAgent",
        _FakeGraphHarnessSkillAutonomousAgent,
    )

    first = await _run_kernel_agent(
        system_prompt="system",
        prompt="resolve relation",
        output_schema=RelationTypeDecision,
        run_id_prefix="relation-test",
        tenant_id="tenant-1",
    )
    second = await _run_kernel_agent(
        system_prompt="system",
        prompt="resolve relation",
        output_schema=RelationTypeDecision,
        run_id_prefix="relation-test",
        tenant_id="tenant-1",
    )

    assert isinstance(first, RelationTypeDecision)
    assert isinstance(second, RelationTypeDecision)
    assert len(created_stores) == 2
    assert created_stores[0] is not created_stores[1]
    assert all(store.closed for store in created_stores)
    for store in created_stores:
        assert store.kernel is not None
        assert store.kernel.closed


@pytest.mark.asyncio
async def test_run_kernel_agent_closes_store_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_stores: list[_FakeKernelStore] = []

    def _create_store() -> _FakeKernelStore:
        store = _FakeKernelStore()
        created_stores.append(store)
        return store

    _FakeGraphHarnessSkillAutonomousAgent.run_exc = RuntimeError("synthetic outage")

    monkeypatch.setattr(runtime_support, "create_artana_postgres_store", _create_store)
    monkeypatch.setattr(
        runtime_support,
        "get_model_registry",
        lambda: SimpleNamespace(
            get_default_model=lambda _capability: SimpleNamespace(
                model_id="openai:gpt-5.4-mini",
                timeout_seconds=60.0,
            ),
        ),
    )
    monkeypatch.setattr(
        runtime_support,
        "normalize_litellm_model_id",
        lambda model_id: model_id,
    )
    monkeypatch.setattr("artana.kernel.ArtanaKernel", _FakeKernel)
    monkeypatch.setattr(
        "artana_evidence_api.composition.build_graph_harness_kernel_middleware",
        lambda: (),
    )
    monkeypatch.setattr(
        "artana_evidence_api.policy.build_graph_harness_policy",
        lambda: object(),
    )
    monkeypatch.setattr(
        "artana_evidence_api.tool_registry.build_graph_harness_tool_registry",
        lambda: object(),
    )
    monkeypatch.setattr(
        "artana_evidence_api.runtime_skill_registry.load_graph_harness_skill_registry",
        lambda: object(),
    )
    monkeypatch.setattr(
        "artana_evidence_api.runtime_skill_agent.GraphHarnessSkillContextBuilder",
        _FakeGraphHarnessSkillContextBuilder,
    )
    monkeypatch.setattr(
        "artana_evidence_api.runtime_skill_agent.GraphHarnessSkillAutonomousAgent",
        _FakeGraphHarnessSkillAutonomousAgent,
    )

    with pytest.raises(RuntimeError, match="synthetic outage"):
        await _run_kernel_agent(
            system_prompt="system",
            prompt="resolve relation",
            output_schema=RelationTypeDecision,
            run_id_prefix="relation-test",
            tenant_id="tenant-1",
        )

    _FakeGraphHarnessSkillAutonomousAgent.run_exc = None
    assert len(created_stores) == 1
    assert created_stores[0].closed is True
    assert created_stores[0].kernel is not None
    assert created_stores[0].kernel.closed is True


# ---------------------------------------------------------------------------
# Entity: resolve_entity_with_ai tests
# ---------------------------------------------------------------------------


class _FakeGateway:
    """Minimal gateway mock for entity resolution tests.

    When ``always_return_all=True``, all entities are returned regardless
    of the query — simulating a graph API that returns broad search results
    (e.g. semantic/vector search that returns candidates even without
    substring overlap).
    """

    def __init__(
        self,
        entities: list[KernelEntityResponse] | None = None,
        *,
        always_return_all: bool = False,
    ):
        self._entities = entities or []
        self._always_return_all = always_return_all

    def list_entities(
        self,
        *,
        space_id,
        q=None,
        entity_type=None,
        ids=None,
        offset=0,
        limit=50,
    ):
        if self._always_return_all:
            matching = self._entities
        else:
            matching = self._entities
            if q:
                nq = q.strip().casefold()
                matching = [
                    e
                    for e in self._entities
                    if nq in (e.display_label or "").casefold()
                    or any(nq in a.casefold() for a in e.aliases)
                ]
        return KernelEntityListResponse(
            entities=matching,
            total=len(matching),
            offset=0,
            limit=limit,
        )


def _make_entity(
    entity_id: str,
    label: str,
    entity_type: str = "GENE",
    aliases: list[str] | None = None,
) -> KernelEntityResponse:
    now = datetime.now(UTC)
    return KernelEntityResponse(
        id=UUID(entity_id),
        research_space_id=uuid4(),
        entity_type=entity_type,
        display_label=label,
        aliases=aliases or [],
        metadata={},
        created_at=now,
        updated_at=now,
    )


class TestResolveEntityWithAi:
    @pytest.mark.asyncio
    async def test_exact_match_skips_agent(self):
        """Exact label match should return immediately without calling the agent."""
        entity_id = "11111111-1111-1111-1111-111111111111"
        gateway = _FakeGateway(
            entities=[_make_entity(entity_id, "BRCA1", aliases=["brca1"])],
        )

        result = await resolve_entity_with_ai(
            space_id=uuid4(),
            label="BRCA1",
            graph_api_gateway=gateway,
        )

        assert result is not None
        assert result["id"] == entity_id
        assert result["display_label"] == "BRCA1"

    @pytest.mark.asyncio
    async def test_alias_match_skips_agent(self):
        """Exact alias match should return immediately without calling the agent."""
        entity_id = "22222222-2222-2222-2222-222222222222"
        gateway = _FakeGateway(
            entities=[
                _make_entity(entity_id, "TP53", aliases=["p53", "tumor protein p53"]),
            ],
        )

        result = await resolve_entity_with_ai(
            space_id=uuid4(),
            label="p53",
            graph_api_gateway=gateway,
        )

        assert result is not None
        assert result["id"] == entity_id

    @pytest.mark.asyncio
    async def test_no_candidates_returns_none_without_agent(self):
        """When graph search returns nothing, return None (create new)."""
        gateway = _FakeGateway(entities=[])

        result = await resolve_entity_with_ai(
            space_id=uuid4(),
            label="some-unknown-entity",
            graph_api_gateway=gateway,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_ambiguous_match_calls_agent(self):
        """When candidates exist but no exact match, agent should be called."""
        entity_id = "33333333-3333-3333-3333-333333333333"
        gateway = _FakeGateway(
            entities=[
                _make_entity(entity_id, "SNCA", entity_type="GENE"),
            ],
            always_return_all=True,  # Graph API returns broad semantic results
        )

        agent_decision = EntityDecision(
            action=EntityAction.MATCH_EXISTING,
            matched_entity_id=entity_id,
            matched_entity_label="SNCA",
            reasoning="alpha-synuclein is the protein encoded by the SNCA gene.",
        )

        with patch(
            "artana_evidence_api.relation_type_resolver._run_kernel_agent",
            new_callable=AsyncMock,
            return_value=agent_decision,
        ) as mock_agent:
            result = await resolve_entity_with_ai(
                space_id=uuid4(),
                label="alpha-synuclein",
                graph_api_gateway=gateway,
            )

        mock_agent.assert_called_once()
        assert result is not None
        assert result["id"] == entity_id
        assert result["display_label"] == "SNCA"

    @pytest.mark.asyncio
    async def test_agent_decides_create_new(self):
        """Agent can decide the label is a genuinely new entity."""
        gateway = _FakeGateway(
            entities=[
                _make_entity(
                    "44444444-4444-4444-4444-444444444444",
                    "BRCA2",
                    entity_type="GENE",
                ),
            ],
            always_return_all=True,
        )

        agent_decision = EntityDecision(
            action=EntityAction.CREATE_NEW,
            entity_type="PROTEIN",
            reasoning="PALB2 is a different gene, not related to BRCA2.",
        )

        with patch(
            "artana_evidence_api.relation_type_resolver._run_kernel_agent",
            new_callable=AsyncMock,
            return_value=agent_decision,
        ):
            result = await resolve_entity_with_ai(
                space_id=uuid4(),
                label="PALB2",
                graph_api_gateway=gateway,
            )

        assert result is None  # None means "create new"

    @pytest.mark.asyncio
    async def test_agent_failure_returns_none(self):
        """On agent failure, fall back to create_new (return None)."""
        gateway = _FakeGateway(
            entities=[
                _make_entity(
                    "55555555-5555-5555-5555-555555555555",
                    "TP53",
                ),
            ],
            always_return_all=True,
        )

        with patch(
            "artana_evidence_api.relation_type_resolver._run_kernel_agent",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Agent crashed"),
        ):
            result = await resolve_entity_with_ai(
                space_id=uuid4(),
                label="tumor suppressor p53",
                graph_api_gateway=gateway,
            )

        assert result is None  # Safe fallback

    @pytest.mark.asyncio
    async def test_cache_prevents_duplicate_agent_calls(self):
        """Second call with same label+space should use cache."""
        entity_id = "66666666-6666-6666-6666-666666666666"
        space_id = uuid4()
        gateway = _FakeGateway(
            entities=[_make_entity(entity_id, "EGFR", entity_type="GENE")],
            always_return_all=True,
        )

        agent_decision = EntityDecision(
            action=EntityAction.MATCH_EXISTING,
            matched_entity_id=entity_id,
            matched_entity_label="EGFR",
            reasoning="ErbB1 is an alias for EGFR.",
        )

        with patch(
            "artana_evidence_api.relation_type_resolver._run_kernel_agent",
            new_callable=AsyncMock,
            return_value=agent_decision,
        ) as mock_agent:
            result1 = await resolve_entity_with_ai(
                space_id=space_id,
                label="ErbB1",
                graph_api_gateway=gateway,
            )
            result2 = await resolve_entity_with_ai(
                space_id=space_id,
                label="ErbB1",
                graph_api_gateway=gateway,
            )

        # Agent called only once, second call uses cache
        assert mock_agent.call_count == 1
        assert result1 == result2
        assert result1["id"] == entity_id


# ---------------------------------------------------------------------------
# document_extraction: ai_resolved_entities integration
# ---------------------------------------------------------------------------


class TestDocumentExtractionAiResolved:
    """Tests that build_document_extraction_drafts uses ai_resolved_entities."""

    def test_ai_resolved_entities_used_over_deterministic(self):
        """When ai_resolved_entities contains a match, it should be used
        instead of calling _resolve_entity_label deterministically."""
        from artana_evidence_api.document_extraction import (
            ExtractedRelationCandidate,
            build_document_extraction_drafts,
            build_document_review_context,
        )
        from artana_evidence_api.document_store import HarnessDocumentRecord

        now = datetime.now(UTC)
        space_id = uuid4()
        subject_entity_id = str(uuid4())

        document = HarnessDocumentRecord(
            id=str(uuid4()),
            space_id=str(space_id),
            created_by=str(uuid4()),
            title="Test doc",
            source_type="text",
            filename=None,
            media_type="text/plain",
            sha256="abc",
            byte_size=10,
            page_count=None,
            text_content="alpha-synuclein causes mitochondrial dysfunction.",
            text_excerpt="alpha-synuclein causes mitochondrial dysfunction.",
            raw_storage_key=None,
            enriched_storage_key=None,
            ingestion_run_id=str(uuid4()),
            last_enrichment_run_id=None,
            last_extraction_run_id=None,
            enrichment_status="completed",
            extraction_status="not_started",
            metadata={},
            created_at=now,
            updated_at=now,
        )
        candidates = [
            ExtractedRelationCandidate(
                subject_label="alpha-synuclein",
                relation_type="CAUSES",
                object_label="mitochondrial dysfunction",
                sentence="alpha-synuclein causes mitochondrial dysfunction.",
            ),
        ]

        # AI resolved: alpha-synuclein → existing SNCA entity
        ai_resolved = {
            "alpha-synuclein": {
                "id": subject_entity_id,
                "display_label": "SNCA",
            },
        }

        # Empty graph — without AI resolution, entities would be unresolved
        gateway = _EmptyGraphApiGateway()

        drafts_without_ai, _ = build_document_extraction_drafts(
            space_id=space_id,
            document=document,
            candidates=candidates,
            graph_api_gateway=gateway,
            review_context=build_document_review_context(),
        )

        drafts_with_ai, _ = build_document_extraction_drafts(
            space_id=space_id,
            document=document,
            candidates=candidates,
            graph_api_gateway=gateway,
            review_context=build_document_review_context(),
            ai_resolved_entities=ai_resolved,
        )

        # Without AI: subject is unresolved
        assert (
            drafts_without_ai[0].payload["proposed_subject"].startswith("unresolved:")
        )

        # With AI: subject is resolved to the SNCA entity
        assert drafts_with_ai[0].payload["proposed_subject"] == subject_entity_id
        assert drafts_with_ai[0].metadata["subject_resolved"] is True


# Reuse the _EmptyGraphApiGateway from the existing test file
class _EmptyGraphApiGateway:
    def __init__(self) -> None:
        self.query = self

    def list_entities(
        self,
        *,
        space_id,
        q=None,
        entity_type=None,
        ids=None,
        offset=0,
        limit=50,
    ):
        return KernelEntityListResponse(entities=[], total=0, offset=0, limit=50)
