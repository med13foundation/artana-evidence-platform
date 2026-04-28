"""AlphaFold source plugin parity and execution tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
from artana_evidence_api.alphafold_gateway import AlphaFoldGatewayFetchResult
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
from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
    EvidenceSelectionSourceSearchRunner,
)
from artana_evidence_api.source_plugins.alphafold import AlphaFoldSourcePlugin
from artana_evidence_api.source_policies import adapter_source_record_policy
from artana_evidence_api.source_registry import get_source_definition


def test_alphafold_plugin_matches_legacy_metadata() -> None:
    plugin = AlphaFoldSourcePlugin()
    definition = get_source_definition("alphafold")

    assert definition is not None
    assert plugin.source_definition() == definition
    assert plugin.source_key == definition.source_key
    assert plugin.source_family == definition.source_family
    assert plugin.display_name == definition.display_name
    assert plugin.request_schema_ref == definition.request_schema_ref
    assert plugin.result_schema_ref == definition.result_schema_ref


def test_alphafold_plugin_matches_legacy_query_playbook() -> None:
    plugin = AlphaFoldSourcePlugin()
    legacy_playbook = adapter_source_query_playbook("alphafold")
    intent = PlannedSourceIntent(
        source_key="alphafold",
        uniprot_id="P38398",
        evidence_role="structure",
        reason="Fetch structure.",
    )

    assert legacy_playbook is not None
    assert plugin.build_query_payload(intent) == legacy_playbook.build_payload(intent)
    assert plugin.supported_objective_intents == legacy_playbook.supported_objective_intents
    assert plugin.result_interpretation_hints == legacy_playbook.result_interpretation_hints
    assert plugin.non_goals == legacy_playbook.non_goals
    assert plugin.handoff_eligible is legacy_playbook.handoff_eligible


def test_alphafold_plugin_matches_legacy_record_policy() -> None:
    plugin = AlphaFoldSourcePlugin()
    legacy_policy = adapter_source_record_policy("alphafold")
    record = _alphafold_record()

    assert legacy_policy is not None
    assert plugin.handoff_target_kind == legacy_policy.handoff_target_kind
    assert plugin.direct_search_supported is legacy_policy.direct_search_supported
    assert plugin.provider_external_id(record) == legacy_policy.provider_external_id(record)
    assert plugin.recommends_variant_aware(record) is legacy_policy.recommends_variant_aware(record)
    assert plugin.normalize_record(record) == legacy_policy.normalize_record(record)


def test_alphafold_plugin_matches_legacy_extraction_policy() -> None:
    plugin = AlphaFoldSourcePlugin()
    legacy_policy = adapter_extraction_policy_for_source("alphafold")
    record = _alphafold_record()

    assert plugin.review_policy.source_key == legacy_policy.source_key
    assert plugin.review_policy.proposal_type == legacy_policy.proposal_type
    assert plugin.review_policy.review_type == legacy_policy.review_type
    assert plugin.review_policy.evidence_role == legacy_policy.evidence_role
    assert plugin.review_policy.limitations == legacy_policy.limitations
    assert plugin.review_policy.normalized_fields == legacy_policy.normalized_fields
    assert plugin.normalized_extraction_payload(record) == (
        adapter_normalized_extraction_payload(
            source_key="alphafold",
            record=record,
        )
    )
    assert plugin.proposal_summary("Relevant structure.") == adapter_proposal_summary(
        source_key="alphafold",
        selection_reason="Relevant structure.",
    )
    assert plugin.review_item_summary("Relevant structure.") == adapter_review_item_summary(
        source_key="alphafold",
        selection_reason="Relevant structure.",
    )


def test_alphafold_plugin_builds_candidate_context() -> None:
    plugin = AlphaFoldSourcePlugin()

    context = plugin.build_candidate_context(_alphafold_record()).to_json()

    assert context["source_key"] == "alphafold"
    assert context["source_family"] == "structure"
    assert context["provider_external_id"] == "P38398"
    assert context["variant_aware_recommended"] is False
    assert context["normalized_record"] == {
        "uniprot_id": "P38398",
        "protein_name": "BRCA1 protein",
        "gene_symbol": "BRCA1",
        "organism": "Homo sapiens",
        "confidence": 92.4,
        "model_url": "https://alphafold.example/P38398.cif",
        "pdb_url": "https://alphafold.example/P38398.pdb",
        "domains": [{"name": "BRCT"}],
    }
    assert context["extraction_policy"]["proposal_type"] == "structure_context_candidate"


@pytest.mark.asyncio
async def test_source_search_runner_dispatches_alphafold_plugin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = AlphaFoldSourcePlugin(gateway_factory=lambda: _FakeAlphaFoldGateway())

    monkeypatch.setattr(
        "artana_evidence_api.evidence_selection_source_search.source_plugin_for_execution",
        lambda source_key, **_: plugin if source_key == "alphafold" else None,
    )

    result = await EvidenceSelectionSourceSearchRunner().run_search(
        space_id=uuid4(),
        created_by=uuid4(),
        source_search=EvidenceSelectionLiveSourceSearch(
            source_key="alphafold",
            query_payload={"uniprot_id": "P38398"},
            max_records=1,
        ),
        store=InMemoryDirectSourceSearchStore(),
    )

    assert result.source_key == "alphafold"
    assert result.query == "P38398"
    assert result.max_results == 1
    assert result.record_count == 1
    assert result.records == [_alphafold_record()]


def _alphafold_record() -> dict[str, object]:
    return {
        "uniprot_id": "P38398",
        "protein_name": "BRCA1 protein",
        "gene_name": "BRCA1",
        "organism": "Homo sapiens",
        "predicted_structure_confidence": 92.4,
        "model_url": "https://alphafold.example/P38398.cif",
        "pdb_url": "https://alphafold.example/P38398.pdb",
        "domains": [{"name": "BRCT"}],
    }


class _FakeAlphaFoldGateway:
    def fetch_records(
        self,
        *,
        uniprot_id: str | None = None,
        max_results: int = 100,
    ) -> AlphaFoldGatewayFetchResult:
        assert uniprot_id == "P38398"
        assert max_results == 1
        return AlphaFoldGatewayFetchResult(
            records=[_alphafold_record()],
            fetched_records=1,
        )
