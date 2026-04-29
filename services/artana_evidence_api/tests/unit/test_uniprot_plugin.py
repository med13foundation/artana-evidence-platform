"""UniProt source plugin parity and execution tests."""

from __future__ import annotations

from uuid import uuid4

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
from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
    EvidenceSelectionSourceSearchRunner,
)
from artana_evidence_api.source_plugins.contracts import (
    EvidenceSelectionSourceSearchError,
    SourceSearchExecutionContext,
)
from artana_evidence_api.source_plugins.uniprot import UniProtSourcePlugin
from artana_evidence_api.source_policies import adapter_source_record_policy
from artana_evidence_api.source_registry import get_source_definition
from artana_evidence_api.uniprot_gateway import UniProtGatewayFetchResult


def test_uniprot_plugin_matches_legacy_metadata() -> None:
    plugin = UniProtSourcePlugin()
    definition = get_source_definition("uniprot")

    assert definition is not None
    assert plugin.source_definition() == definition
    assert plugin.source_key == definition.source_key
    assert plugin.source_family == definition.source_family
    assert plugin.display_name == definition.display_name
    assert plugin.request_schema_ref == definition.request_schema_ref
    assert plugin.result_schema_ref == definition.result_schema_ref


def test_uniprot_plugin_matches_legacy_query_playbook_for_query() -> None:
    plugin = UniProtSourcePlugin()
    legacy_playbook = adapter_source_query_playbook("uniprot")
    intent = PlannedSourceIntent(
        source_key="uniprot",
        gene_symbol="MED13",
        organism="Homo sapiens",
        evidence_role="protein identity",
        reason="Ground protein identity.",
    )

    assert legacy_playbook is not None
    assert plugin.build_query_payload(intent) == legacy_playbook.build_payload(intent)
    assert plugin.supported_objective_intents == legacy_playbook.supported_objective_intents
    assert plugin.result_interpretation_hints == legacy_playbook.result_interpretation_hints
    assert plugin.non_goals == legacy_playbook.non_goals
    assert plugin.handoff_eligible is legacy_playbook.handoff_eligible


def test_uniprot_plugin_matches_legacy_query_playbook_for_accession() -> None:
    plugin = UniProtSourcePlugin()
    legacy_playbook = adapter_source_query_playbook("uniprot")
    intent = PlannedSourceIntent(
        source_key="uniprot",
        uniprot_id="Q9UHV7",
        evidence_role="protein identity",
        reason="Fetch exact accession.",
    )

    assert legacy_playbook is not None
    assert plugin.build_query_payload(intent) == legacy_playbook.build_payload(intent)


def test_uniprot_plugin_matches_legacy_record_policy() -> None:
    plugin = UniProtSourcePlugin()
    legacy_policy = adapter_source_record_policy("uniprot")
    record = _uniprot_record()

    assert legacy_policy is not None
    assert plugin.handoff_target_kind == legacy_policy.handoff_target_kind
    assert plugin.direct_search_supported is legacy_policy.direct_search_supported
    assert plugin.provider_external_id(record) == legacy_policy.provider_external_id(record)
    assert plugin.recommends_variant_aware(record) is legacy_policy.recommends_variant_aware(record)
    assert plugin.normalize_record(record) == legacy_policy.normalize_record(record)


def test_uniprot_plugin_matches_legacy_extraction_policy() -> None:
    plugin = UniProtSourcePlugin()
    legacy_policy = adapter_extraction_policy_for_source("uniprot")
    record = _uniprot_record()

    assert plugin.review_policy.source_key == legacy_policy.source_key
    assert plugin.review_policy.proposal_type == legacy_policy.proposal_type
    assert plugin.review_policy.review_type == legacy_policy.review_type
    assert plugin.review_policy.evidence_role == legacy_policy.evidence_role
    assert plugin.review_policy.limitations == legacy_policy.limitations
    assert plugin.review_policy.normalized_fields == legacy_policy.normalized_fields
    assert plugin.normalized_extraction_payload(record) == (
        adapter_normalized_extraction_payload(
            source_key="uniprot",
            record=record,
        )
    )
    assert plugin.proposal_summary("Relevant protein annotation.") == (
        adapter_proposal_summary(
            source_key="uniprot",
            selection_reason="Relevant protein annotation.",
        )
    )
    assert plugin.review_item_summary("Relevant protein annotation.") == (
        adapter_review_item_summary(
            source_key="uniprot",
            selection_reason="Relevant protein annotation.",
        )
    )


def test_uniprot_plugin_builds_candidate_context() -> None:
    plugin = UniProtSourcePlugin()

    context = plugin.build_candidate_context(_uniprot_record()).to_json()

    assert context["source_key"] == "uniprot"
    assert context["source_family"] == "protein"
    assert context["provider_external_id"] == "Q9UHV7"
    assert context["variant_aware_recommended"] is False
    assert context["normalized_record"] == {
        "uniprot_id": "Q9UHV7",
        "gene_symbol": "MED13",
        "protein_name": "Mediator complex subunit 13",
        "organism": "Homo sapiens",
        "function": "Component of the mediator complex.",
        "sequence_length": 2174,
    }
    assert context["extraction_policy"]["proposal_type"] == (
        "protein_annotation_candidate"
    )


@pytest.mark.asyncio
async def test_source_search_runner_dispatches_uniprot_plugin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = UniProtSourcePlugin(gateway_factory=lambda: _FakeUniProtGateway())

    monkeypatch.setattr(
        "artana_evidence_api.evidence_selection_source_search.source_plugin_for_execution",
        lambda source_key, **_: plugin if source_key == "uniprot" else None,
    )

    result = await EvidenceSelectionSourceSearchRunner().run_search(
        space_id=uuid4(),
        created_by=uuid4(),
        source_search=EvidenceSelectionLiveSourceSearch(
            source_key="uniprot",
            query_payload={"query": "MED13"},
            max_records=1,
        ),
        store=InMemoryDirectSourceSearchStore(),
    )

    assert result.source_key == "uniprot"
    assert result.query == "MED13"
    assert result.uniprot_id is None
    assert result.max_results == 1
    assert result.record_count == 1
    assert result.records == [_uniprot_record()]


@pytest.mark.asyncio
async def test_uniprot_plugin_rejects_unavailable_gateway() -> None:
    plugin = UniProtSourcePlugin(gateway_factory=lambda: None)

    with pytest.raises(
        EvidenceSelectionSourceSearchError,
        match="UniProt gateway is unavailable",
    ):
        await plugin.run_direct_search(
            context=SourceSearchExecutionContext(
                space_id=uuid4(),
                created_by=uuid4(),
                store=InMemoryDirectSourceSearchStore(),
            ),
            search=EvidenceSelectionLiveSourceSearch(
                source_key="uniprot",
                query_payload={"query": "MED13"},
                max_records=1,
            ),
        )


def _uniprot_record() -> dict[str, object]:
    return {
        "uniprot_id": "Q9UHV7",
        "primary_accession": "Q9UHV7",
        "accession": "Q9UHV7",
        "gene_name": "MED13",
        "protein_name": "Mediator complex subunit 13",
        "organism": "Homo sapiens",
        "function": "Component of the mediator complex.",
        "sequence_length": 2174,
        "source": "uniprot",
    }


class _FakeUniProtGateway:
    def fetch_records(
        self,
        *,
        query: str | None = None,
        uniprot_id: str | None = None,
        max_results: int = 100,
    ) -> UniProtGatewayFetchResult:
        assert query == "MED13"
        assert uniprot_id is None
        assert max_results == 1
        return UniProtGatewayFetchResult(
            records=[_uniprot_record()],
            fetched_records=1,
        )

