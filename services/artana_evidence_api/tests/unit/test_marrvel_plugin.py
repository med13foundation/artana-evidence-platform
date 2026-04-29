"""MARRVEL source plugin parity and execution tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from artana_evidence_api.direct_source_search import InMemoryDirectSourceSearchStore
from artana_evidence_api.evidence_selection_extraction_policy import (
    adapter_extraction_policy_for_source,
    adapter_normalized_extraction_payload,
    adapter_proposal_summary,
    adapter_review_item_summary,
)
from artana_evidence_api.evidence_selection_source_planning import PlannedSourceIntent
from artana_evidence_api.evidence_selection_source_playbooks import (
    adapter_source_query_playbook,
)
from artana_evidence_api.marrvel_discovery import MarrvelDiscoveryResult
from artana_evidence_api.source_plugins.contracts import (
    EvidenceSelectionSourceSearchError,
    SourcePluginPlanningError,
    SourceSearchExecutionContext,
)
from artana_evidence_api.source_plugins.marrvel import MarrvelSourcePlugin
from artana_evidence_api.source_policies import adapter_source_record_policy
from artana_evidence_api.source_registry import get_source_definition


def test_marrvel_plugin_matches_legacy_metadata() -> None:
    plugin = MarrvelSourcePlugin()
    definition = get_source_definition("marrvel")

    assert definition is not None
    assert plugin.source_definition() == definition
    assert plugin.source_key == definition.source_key
    assert plugin.source_family == definition.source_family
    assert plugin.display_name == definition.display_name
    assert plugin.request_schema_ref == definition.request_schema_ref
    assert plugin.result_schema_ref == definition.result_schema_ref
    assert plugin.metadata.default_research_plan_enabled is True


def test_marrvel_plugin_matches_legacy_query_playbook_defaults() -> None:
    plugin = MarrvelSourcePlugin()
    legacy_playbook = adapter_source_query_playbook("marrvel")
    intent = PlannedSourceIntent(
        source_key="marrvel",
        gene_symbol=" MED13 ",
        evidence_role="variant panel evidence",
        reason="Search MARRVEL.",
    )

    assert legacy_playbook is not None
    assert plugin.build_query_payload(intent) == legacy_playbook.build_payload(intent)
    assert plugin.supported_objective_intents == legacy_playbook.supported_objective_intents
    assert plugin.result_interpretation_hints == legacy_playbook.result_interpretation_hints
    assert plugin.non_goals == legacy_playbook.non_goals
    assert plugin.handoff_eligible is legacy_playbook.handoff_eligible


def test_marrvel_plugin_preserves_request_looseness_and_panel_normalization() -> None:
    plugin = MarrvelSourcePlugin()
    intent = PlannedSourceIntent(
        source_key="marrvel",
        gene_symbol="MED13",
        variant_hgvs=" NC_000017.11:g.6012345A>G ",
        taxon_id=9606,
        panels=["ClinVar", "clinvar", "GNOMAD_VARIANT"],
        evidence_role="variant panel evidence",
        reason="Search variant panels.",
    )

    assert plugin.build_query_payload(intent) == {
        "gene_symbol": "MED13",
        "variant_hgvs": "NC_000017.11:g.6012345A>G",
        "panels": ["clinvar", "gnomad_variant"],
    }


def test_marrvel_plugin_rejects_conflicting_variant_inputs() -> None:
    plugin = MarrvelSourcePlugin()
    intent = PlannedSourceIntent(
        source_key="marrvel",
        variant_hgvs="NC_000017.11:g.6012345A>G",
        protein_variant="p.Arg1Trp",
        evidence_role="variant panel evidence",
        reason="Bad request.",
    )

    with pytest.raises(SourcePluginPlanningError, match="either variant_hgvs or protein_variant"):
        plugin.build_query_payload(intent)


def test_marrvel_plugin_rejects_unsupported_planning_panel() -> None:
    plugin = MarrvelSourcePlugin()
    intent = PlannedSourceIntent(
        source_key="marrvel",
        gene_symbol="MED13",
        panels=["not-a-panel"],
        evidence_role="variant panel evidence",
        reason="Bad panel.",
    )

    with pytest.raises(SourcePluginPlanningError, match="Unsupported MARRVEL panel"):
        plugin.build_query_payload(intent)


def test_marrvel_plugin_matches_legacy_record_policy() -> None:
    plugin = MarrvelSourcePlugin()
    legacy_policy = adapter_source_record_policy("marrvel")
    record = _marrvel_panel_record()

    assert legacy_policy is not None
    assert plugin.handoff_target_kind == legacy_policy.handoff_target_kind
    assert plugin.direct_search_supported is legacy_policy.direct_search_supported
    assert plugin.provider_external_id(record) == legacy_policy.provider_external_id(record)
    assert plugin.recommends_variant_aware(record) is legacy_policy.recommends_variant_aware(record)
    assert plugin.normalize_record(record) == legacy_policy.normalize_record(record)


def test_marrvel_plugin_matches_legacy_extraction_policy() -> None:
    plugin = MarrvelSourcePlugin()
    legacy_policy = adapter_extraction_policy_for_source("marrvel")
    record = _marrvel_panel_record()

    assert plugin.review_policy.source_key == legacy_policy.source_key
    assert plugin.review_policy.proposal_type == legacy_policy.proposal_type
    assert plugin.review_policy.review_type == legacy_policy.review_type
    assert plugin.review_policy.evidence_role == legacy_policy.evidence_role
    assert plugin.review_policy.limitations == legacy_policy.limitations
    assert plugin.review_policy.normalized_fields == legacy_policy.normalized_fields
    assert plugin.normalized_extraction_payload(record) == (
        adapter_normalized_extraction_payload(source_key="marrvel", record=record)
    )
    assert plugin.proposal_summary("Relevant panel.") == adapter_proposal_summary(
        source_key="marrvel",
        selection_reason="Relevant panel.",
    )
    assert plugin.review_item_summary("Relevant panel.") == adapter_review_item_summary(
        source_key="marrvel",
        selection_reason="Relevant panel.",
    )


def test_marrvel_plugin_builds_variant_aware_candidate_context() -> None:
    plugin = MarrvelSourcePlugin()

    context = plugin.build_candidate_context(_marrvel_panel_record()).to_json()

    assert context["source_key"] == "marrvel"
    assert context["source_family"] == "variant"
    assert context["provider_external_id"] == "search-1:clinvar:0"
    assert context["variant_aware_recommended"] is True
    assert context["normalized_record"] == {
        "marrvel_record_id": "search-1:clinvar:0",
        "panel_name": "clinvar",
        "panel_family": "variant",
        "gene_symbol": "MED13",
        "resolved_gene_symbol": "MED13",
        "hgvs": "NC_000017.11:g.6012345A>G",
        "query_mode": "variant_hgvs",
        "query_value": "NC_000017.11:g.6012345A>G",
    }
    assert context["extraction_policy"]["proposal_type"] == "variant_evidence_candidate"


def test_marrvel_plugin_validates_live_search_source_key() -> None:
    plugin = MarrvelSourcePlugin()

    with pytest.raises(EvidenceSelectionSourceSearchError, match="canonical source_key"):
        plugin.validate_live_search(
            _LiveSearch(
                source_key="MARRVEL",
                query_payload={"gene_symbol": "MED13"},
            ),
        )


def test_marrvel_plugin_rejects_live_search_without_query_input() -> None:
    plugin = MarrvelSourcePlugin()

    with pytest.raises(
        EvidenceSelectionSourceSearchError,
        match="gene_symbol, variant_hgvs, or protein_variant",
    ):
        plugin.validate_live_search(
            _LiveSearch(source_key="marrvel", query_payload={"taxon_id": 9606}),
        )


@pytest.mark.asyncio
async def test_marrvel_plugin_runs_direct_search_and_preserves_panel_shape() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    service = _FakeMarrvelDiscoveryService(
        result=MarrvelDiscoveryResult(
            id=search_id,
            space_id=space_id,
            owner_id=user_id,
            query_mode="variant_hgvs",
            query_value="NC_000017.11:g.6012345A>G",
            gene_symbol="MED13",
            resolved_gene_symbol="MED13",
            resolved_variant="NM_005121.3:c.1A>G",
            taxon_id=9606,
            status="completed",
            gene_found=True,
            gene_info={"symbol": "MED13"},
            omim_count=0,
            variant_count=2,
            panel_counts={"clinvar": 1, "gnomad_variant": 1},
            panels={
                "clinvar": [
                    {
                        "title": "ClinVar panel hit",
                        "variant": "NC_000017.11:g.6012345A>G",
                    },
                ],
                "gnomad_variant": {"allele_count": 3},
            },
            available_panels=["clinvar", "gnomad_variant"],
            created_at=datetime.now(UTC),
        ),
    )
    plugin = MarrvelSourcePlugin(discovery_service_factory=lambda: service)

    result = await plugin.run_direct_search(
        context=SourceSearchExecutionContext(
            space_id=space_id,
            created_by=user_id,
            store=InMemoryDirectSourceSearchStore(),
        ),
        search=_LiveSearch(
            source_key="marrvel",
            query_payload={
                "gene_symbol": "MED13",
                "variant_hgvs": "NC_000017.11:g.6012345A>G",
                "panels": ["clinvar", "gnomad_variant"],
            },
        ),
    )

    assert service.requests == [
        {
            "owner_id": user_id,
            "space_id": space_id,
            "gene_symbol": "MED13",
            "variant_hgvs": "NC_000017.11:g.6012345A>G",
            "protein_variant": None,
            "taxon_id": 9606,
            "panels": ["clinvar", "gnomad_variant"],
        },
    ]
    assert service.close_count == 1
    assert result.source_key == "marrvel"
    assert result.query == "NC_000017.11:g.6012345A>G"
    assert result.record_count == 2
    assert result.source_capture.external_id is None
    assert result.records[0]["marrvel_record_id"] == f"{search_id}:clinvar:0"
    assert result.records[0]["panel_family"] == "variant"
    assert result.records[0]["variant_aware_recommended"] is True
    assert result.records[0]["hgvs_notation"] == "NC_000017.11:g.6012345A>G"
    assert result.records[1]["marrvel_record_id"] == f"{search_id}:gnomad_variant:0"
    assert result.records[1]["panel_payload"] == {"allele_count": 3}
    assert result.records[1]["hgvs_notation"] == "NM_005121.3:c.1A>G"


@pytest.mark.asyncio
async def test_marrvel_plugin_reports_unavailable_discovery_service() -> None:
    plugin = MarrvelSourcePlugin(discovery_service_factory=lambda: None)

    with pytest.raises(
        EvidenceSelectionSourceSearchError,
        match="MARRVEL discovery service is unavailable",
    ):
        await plugin.run_direct_search(
            context=SourceSearchExecutionContext(
                space_id=uuid4(),
                created_by=uuid4(),
                store=InMemoryDirectSourceSearchStore(),
            ),
            search=_LiveSearch(
                source_key="marrvel",
                query_payload={"gene_symbol": "MED13"},
            ),
        )


@pytest.mark.asyncio
async def test_marrvel_plugin_closes_discovery_service_when_search_fails() -> None:
    service = _FailingMarrvelDiscoveryService()
    plugin = MarrvelSourcePlugin(discovery_service_factory=lambda: service)

    with pytest.raises(RuntimeError, match="boom"):
        await plugin.run_direct_search(
            context=SourceSearchExecutionContext(
                space_id=uuid4(),
                created_by=uuid4(),
                store=InMemoryDirectSourceSearchStore(),
            ),
            search=_LiveSearch(
                source_key="marrvel",
                query_payload={"gene_symbol": "MED13"},
            ),
        )

    assert service.close_count == 1


@pytest.mark.asyncio
async def test_marrvel_plugin_preserves_hgvs_precedence() -> None:
    result = await _run_marrvel_panel_search(
        panel_payload={
            "hgvs_notation": "preferred",
            "hgvs": "secondary",
            "variant": "tertiary",
            "cdna_change": "cdna",
            "protein_change": "protein",
        },
        resolved_variant="resolved",
        query_mode="variant_hgvs",
        query_value="query",
    )

    assert result.records[0]["hgvs_notation"] == "preferred"


@pytest.mark.asyncio
async def test_marrvel_plugin_does_not_use_gene_query_as_hgvs_fallback() -> None:
    result = await _run_marrvel_panel_search(
        panel_payload={"title": "Metadata-only panel"},
        resolved_variant=None,
        query_mode="gene",
        query_value="MED13",
    )

    assert "hgvs_notation" not in result.records[0]


def _marrvel_panel_record() -> dict[str, object]:
    return {
        "marrvel_record_id": "search-1:clinvar:0",
        "panel_name": "clinvar",
        "panel_family": "variant",
        "gene_symbol": "MED13",
        "resolved_gene_symbol": "MED13",
        "hgvs_notation": "NC_000017.11:g.6012345A>G",
        "query_mode": "variant_hgvs",
        "query_value": "NC_000017.11:g.6012345A>G",
        "variant_aware_recommended": True,
    }


@dataclass(frozen=True, slots=True)
class _LiveSearch:
    source_key: str
    query_payload: dict[str, object]
    max_records: int | None = None
    timeout_seconds: float | None = None


class _FakeMarrvelDiscoveryService:
    def __init__(self, *, result: MarrvelDiscoveryResult) -> None:
        self.result = result
        self.requests: list[dict[str, object]] = []
        self.close_count = 0

    async def search(
        self,
        *,
        owner_id: UUID,
        space_id: UUID,
        gene_symbol: str | None = None,
        variant_hgvs: str | None = None,
        protein_variant: str | None = None,
        taxon_id: int = 9606,
        panels: tuple[str, ...] | list[str] | None = None,
    ) -> MarrvelDiscoveryResult:
        self.requests.append(
            {
                "owner_id": owner_id,
                "space_id": space_id,
                "gene_symbol": gene_symbol,
                "variant_hgvs": variant_hgvs,
                "protein_variant": protein_variant,
                "taxon_id": taxon_id,
                "panels": list(panels or []),
            },
        )
        return self.result

    def close(self) -> None:
        self.close_count += 1


class _FailingMarrvelDiscoveryService:
    def __init__(self) -> None:
        self.close_count = 0

    async def search(
        self,
        *,
        owner_id: UUID,
        space_id: UUID,
        gene_symbol: str | None = None,
        variant_hgvs: str | None = None,
        protein_variant: str | None = None,
        taxon_id: int = 9606,
        panels: tuple[str, ...] | list[str] | None = None,
    ) -> MarrvelDiscoveryResult:
        del owner_id, space_id, gene_symbol, variant_hgvs
        del protein_variant, taxon_id, panels
        raise RuntimeError("boom")

    def close(self) -> None:
        self.close_count += 1


async def _run_marrvel_panel_search(
    *,
    panel_payload: dict[str, object],
    resolved_variant: str | None,
    query_mode: str,
    query_value: str,
) -> object:
    space_id = uuid4()
    user_id = uuid4()
    service = _FakeMarrvelDiscoveryService(
        result=MarrvelDiscoveryResult(
            id=uuid4(),
            space_id=space_id,
            owner_id=user_id,
            query_mode=query_mode,  # type: ignore[arg-type]
            query_value=query_value,
            gene_symbol="MED13" if query_mode == "gene" else None,
            resolved_gene_symbol="MED13",
            resolved_variant=resolved_variant,
            taxon_id=9606,
            status="completed",
            gene_found=True,
            gene_info={"symbol": "MED13"},
            omim_count=0,
            variant_count=1,
            panel_counts={"clinvar": 1},
            panels={"clinvar": [panel_payload]},
            available_panels=["clinvar"],
            created_at=datetime.now(UTC),
        ),
    )
    plugin = MarrvelSourcePlugin(discovery_service_factory=lambda: service)
    return await plugin.run_direct_search(
        context=SourceSearchExecutionContext(
            space_id=space_id,
            created_by=user_id,
            store=InMemoryDirectSourceSearchStore(),
        ),
        search=_LiveSearch(
            source_key="marrvel",
            query_payload={"gene_symbol": "MED13"},
        ),
    )
