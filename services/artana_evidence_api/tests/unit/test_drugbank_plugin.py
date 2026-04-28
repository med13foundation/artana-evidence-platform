"""DrugBank source plugin parity and execution tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
from artana_evidence_api.direct_source_search import InMemoryDirectSourceSearchStore
from artana_evidence_api.drugbank_gateway import DrugBankGatewayFetchResult
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
)
from artana_evidence_api.source_plugins.contracts import (
    EvidenceSelectionSourceSearchError,
    SourceSearchExecutionContext,
)
from artana_evidence_api.source_plugins.drugbank import DrugBankSourcePlugin
from artana_evidence_api.source_policies import adapter_source_record_policy
from artana_evidence_api.source_registry import get_source_definition
from artana_evidence_api.types.common import JSONObject
from pydantic import ValidationError


def test_drugbank_plugin_matches_legacy_metadata() -> None:
    plugin = DrugBankSourcePlugin()
    definition = get_source_definition("drugbank")

    assert definition is not None
    assert plugin.source_definition() == definition
    assert plugin.source_key == definition.source_key
    assert plugin.source_family == definition.source_family
    assert plugin.display_name == definition.display_name
    assert plugin.request_schema_ref == definition.request_schema_ref
    assert plugin.result_schema_ref == definition.result_schema_ref
    assert plugin.metadata.requires_credentials is True
    assert plugin.metadata.credential_names == ("DRUGBANK_API_KEY",)


def test_drugbank_plugin_matches_legacy_query_playbook_for_drug_name() -> None:
    plugin = DrugBankSourcePlugin()
    legacy_playbook = adapter_source_query_playbook("drugbank")
    intent = PlannedSourceIntent(
        source_key="drugbank",
        drug_name="imatinib",
        evidence_role="drug target context",
        reason="Fetch drug targets.",
    )

    assert legacy_playbook is not None
    assert plugin.build_query_payload(intent) == legacy_playbook.build_payload(intent)
    assert plugin.supported_objective_intents == legacy_playbook.supported_objective_intents
    assert plugin.result_interpretation_hints == legacy_playbook.result_interpretation_hints
    assert plugin.non_goals == legacy_playbook.non_goals
    assert plugin.handoff_eligible is legacy_playbook.handoff_eligible


def test_drugbank_plugin_matches_legacy_query_playbook_for_drugbank_id() -> None:
    plugin = DrugBankSourcePlugin()
    legacy_playbook = adapter_source_query_playbook("drugbank")
    intent = PlannedSourceIntent(
        source_key="drugbank",
        drug_name="imatinib",
        drugbank_id="DB00619",
        evidence_role="drug target context",
        reason="Fetch drug targets.",
    )

    assert legacy_playbook is not None
    assert plugin.build_query_payload(intent) == legacy_playbook.build_payload(intent)
    assert plugin.build_query_payload(intent) == {"drugbank_id": "DB00619"}


def test_drugbank_plugin_uses_query_as_drug_name_fallback() -> None:
    plugin = DrugBankSourcePlugin()
    legacy_playbook = adapter_source_query_playbook("drugbank")
    intent = PlannedSourceIntent(
        source_key="drugbank",
        query="  sotorasib  ",
        evidence_role="drug target context",
        reason="Fetch drug targets.",
    )

    assert legacy_playbook is not None
    assert plugin.build_query_payload(intent) == legacy_playbook.build_payload(intent)
    assert plugin.build_query_payload(intent) == {"drug_name": "sotorasib"}


def test_drugbank_plugin_matches_legacy_record_policy() -> None:
    plugin = DrugBankSourcePlugin()
    legacy_policy = adapter_source_record_policy("drugbank")
    record = _drugbank_record()

    assert legacy_policy is not None
    assert plugin.handoff_target_kind == legacy_policy.handoff_target_kind
    assert plugin.direct_search_supported is legacy_policy.direct_search_supported
    assert plugin.provider_external_id(record) == legacy_policy.provider_external_id(record)
    assert plugin.recommends_variant_aware(record) is legacy_policy.recommends_variant_aware(record)
    assert plugin.normalize_record(record) == legacy_policy.normalize_record(record)


def test_drugbank_plugin_matches_legacy_extraction_policy() -> None:
    plugin = DrugBankSourcePlugin()
    legacy_policy = adapter_extraction_policy_for_source("drugbank")
    record = _drugbank_record()

    assert plugin.review_policy.source_key == legacy_policy.source_key
    assert plugin.review_policy.proposal_type == legacy_policy.proposal_type
    assert plugin.review_policy.review_type == legacy_policy.review_type
    assert plugin.review_policy.evidence_role == legacy_policy.evidence_role
    assert plugin.review_policy.limitations == legacy_policy.limitations
    assert plugin.review_policy.normalized_fields == legacy_policy.normalized_fields
    assert plugin.normalized_extraction_payload(record) == (
        adapter_normalized_extraction_payload(
            source_key="drugbank",
            record=record,
        )
    )
    assert plugin.proposal_summary("Relevant drug target.") == adapter_proposal_summary(
        source_key="drugbank",
        selection_reason="Relevant drug target.",
    )
    assert plugin.review_item_summary("Relevant drug target.") == adapter_review_item_summary(
        source_key="drugbank",
        selection_reason="Relevant drug target.",
    )


def test_drugbank_plugin_builds_candidate_context() -> None:
    plugin = DrugBankSourcePlugin()

    context = plugin.build_candidate_context(_drugbank_record()).to_json()

    assert context["source_key"] == "drugbank"
    assert context["source_family"] == "drug"
    assert context["provider_external_id"] == "DB00619"
    assert context["variant_aware_recommended"] is False
    assert context["normalized_record"] == {
        "drugbank_id": "DB00619",
        "drug_name": "Imatinib",
        "target_name": "ABL1",
        "targets": ["ABL1", "KIT"],
        "mechanism": "Inhibits BCR-ABL.",
        "categories": ["Antineoplastic Agents"],
    }
    assert context["extraction_policy"]["proposal_type"] == (
        "drug_target_context_candidate"
    )


def test_drugbank_plugin_validates_source_key_mismatch() -> None:
    plugin = DrugBankSourcePlugin()

    with pytest.raises(
        EvidenceSelectionSourceSearchError,
        match="DrugBank plugin requires canonical source_key 'drugbank'",
    ):
        plugin.validate_live_search(
            EvidenceSelectionLiveSourceSearch(
                source_key="alphafold",
                query_payload={"drug_name": "imatinib"},
            ),
        )


def test_drugbank_plugin_rejects_invalid_live_search_payload() -> None:
    plugin = DrugBankSourcePlugin()

    with pytest.raises(ValidationError, match="Provide one of drug_name or drugbank_id"):
        plugin.validate_live_search(
            EvidenceSelectionLiveSourceSearch(
                source_key="drugbank",
                query_payload={},
            ),
        )


@pytest.mark.asyncio
async def test_drugbank_plugin_runs_existing_direct_search_path() -> None:
    plugin = DrugBankSourcePlugin(
        gateway_factory=lambda: _FakeDrugBankGateway(
            expected_drugbank_id="DB00619",
            expected_max_results=1,
        ),
    )

    context = plugin_context()

    result = await plugin.run_direct_search(
        context=context,
        search=EvidenceSelectionLiveSourceSearch(
            source_key="drugbank",
            query_payload={"drugbank_id": "DB00619"},
            max_records=1,
        ),
    )

    assert result.source_key == "drugbank"
    assert result.query == "DB00619"
    assert result.drugbank_id == "DB00619"
    assert result.drug_name is None
    assert result.max_results == 1
    assert result.record_count == 1
    assert result.records == [_drugbank_record()]
    assert result.source_capture.source_key == "drugbank"
    assert result.source_capture.external_id == "DB00619"
    assert context.store.get(
        space_id=result.space_id,
        source_key="drugbank",
        search_id=result.id,
    ) == result


@pytest.mark.asyncio
async def test_drugbank_plugin_runs_drug_name_direct_search_path() -> None:
    plugin = DrugBankSourcePlugin(
        gateway_factory=lambda: _FakeDrugBankGateway(
            expected_drug_name="imatinib",
            expected_max_results=3,
        ),
    )

    result = await plugin.run_direct_search(
        context=plugin_context(),
        search=EvidenceSelectionLiveSourceSearch(
            source_key="drugbank",
            query_payload={"drug_name": " imatinib "},
            max_records=3,
        ),
    )

    assert result.source_key == "drugbank"
    assert result.query == "imatinib"
    assert result.drug_name == "imatinib"
    assert result.drugbank_id is None
    assert result.max_results == 3
    assert result.record_count == 1


@pytest.mark.asyncio
async def test_drugbank_plugin_preserves_payload_max_results_over_max_records() -> None:
    plugin = DrugBankSourcePlugin(
        gateway_factory=lambda: _FakeDrugBankGateway(
            expected_drug_name="imatinib",
            expected_max_results=5,
        ),
    )

    result = await plugin.run_direct_search(
        context=plugin_context(),
        search=EvidenceSelectionLiveSourceSearch(
            source_key="drugbank",
            query_payload={"drug_name": "imatinib", "max_results": 5},
            max_records=2,
        ),
    )

    assert result.max_results == 5


@pytest.mark.asyncio
async def test_drugbank_plugin_default_gateway_factory_is_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = DrugBankSourcePlugin()

    monkeypatch.setattr(
        "artana_evidence_api.source_plugins.drugbank.build_drugbank_gateway",
        lambda: _FakeDrugBankGateway(
            expected_drug_name="imatinib",
            expected_max_results=1,
        ),
    )

    result = await plugin.run_direct_search(
        context=plugin_context(),
        search=EvidenceSelectionLiveSourceSearch(
            source_key="drugbank",
            query_payload={"drug_name": "imatinib"},
            max_records=1,
        ),
    )

    assert result.query == "imatinib"


@pytest.mark.asyncio
async def test_drugbank_plugin_run_direct_search_validates_source_key_mismatch() -> None:
    plugin = DrugBankSourcePlugin(gateway_factory=lambda: _UnexpectedDrugBankGateway())

    with pytest.raises(
        EvidenceSelectionSourceSearchError,
        match="DrugBank plugin requires canonical source_key 'drugbank'",
    ):
        await plugin.run_direct_search(
            context=plugin_context(),
            search=EvidenceSelectionLiveSourceSearch(
                source_key="alphafold",
                query_payload={"drug_name": "imatinib"},
            ),
        )


@pytest.mark.asyncio
async def test_drugbank_plugin_reports_unavailable_injected_gateway() -> None:
    plugin = DrugBankSourcePlugin(gateway_factory=lambda: None)

    with pytest.raises(
        EvidenceSelectionSourceSearchError,
        match="DrugBank gateway is unavailable.",
    ):
        await plugin.run_direct_search(
            context=plugin_context(),
            search=EvidenceSelectionLiveSourceSearch(
                source_key="drugbank",
                query_payload={"drug_name": "imatinib"},
            ),
        )


def plugin_context() -> SourceSearchExecutionContext:
    return SourceSearchExecutionContext(
        space_id=uuid4(),
        created_by=uuid4(),
        store=InMemoryDirectSourceSearchStore(),
    )


def _drugbank_record() -> JSONObject:
    return {
        "drugbank_id": "DB00619",
        "name": "Imatinib",
        "target_name": "ABL1",
        "targets": ["ABL1", "KIT"],
        "mechanism_of_action": "Inhibits BCR-ABL.",
        "categories": ["Antineoplastic Agents"],
    }


class _FakeDrugBankGateway:
    def __init__(
        self,
        *,
        expected_drug_name: str | None = None,
        expected_drugbank_id: str | None = None,
        expected_max_results: int,
    ) -> None:
        self._expected_drug_name = expected_drug_name
        self._expected_drugbank_id = expected_drugbank_id
        self._expected_max_results = expected_max_results

    def fetch_records(
        self,
        *,
        drug_name: str | None = None,
        drugbank_id: str | None = None,
        max_results: int = 100,
    ) -> DrugBankGatewayFetchResult:
        assert drug_name == self._expected_drug_name
        assert drugbank_id == self._expected_drugbank_id
        assert max_results == self._expected_max_results
        return DrugBankGatewayFetchResult(
            records=[_drugbank_record()],
            fetched_records=1,
        )


class _UnexpectedDrugBankGateway:
    def fetch_records(
        self,
        *,
        drug_name: str | None = None,
        drugbank_id: str | None = None,
        max_results: int = 100,
    ) -> DrugBankGatewayFetchResult:
        del drug_name, drugbank_id, max_results
        raise AssertionError("DrugBank gateway should not be called.")
