"""ClinicalTrials.gov source plugin parity and execution tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
from artana_evidence_api.clinicaltrials_gateway import ClinicalTrialsGatewayFetchResult
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
from artana_evidence_api.source_plugins.clinical_trials import (
    ClinicalTrialsSourcePlugin,
)
from artana_evidence_api.source_policies import adapter_source_record_policy
from artana_evidence_api.source_registry import get_source_definition


def test_clinical_trials_plugin_matches_legacy_metadata() -> None:
    plugin = ClinicalTrialsSourcePlugin()
    definition = get_source_definition("clinical_trials")

    assert definition is not None
    assert plugin.source_definition() == definition
    assert plugin.source_key == definition.source_key
    assert plugin.source_family == definition.source_family
    assert plugin.display_name == definition.display_name
    assert plugin.request_schema_ref == definition.request_schema_ref
    assert plugin.result_schema_ref == definition.result_schema_ref


def test_clinical_trials_plugin_matches_legacy_query_playbook() -> None:
    plugin = ClinicalTrialsSourcePlugin()
    legacy_playbook = adapter_source_query_playbook("clinical_trials")
    intent = PlannedSourceIntent(
        source_key="clinical_trials",
        disease="cystic fibrosis",
        drug_name="ivacaftor",
        evidence_role="trial context",
        reason="Search trials.",
    )

    assert legacy_playbook is not None
    assert plugin.build_query_payload(intent) == legacy_playbook.build_payload(intent)
    assert plugin.supported_objective_intents == legacy_playbook.supported_objective_intents
    assert plugin.result_interpretation_hints == legacy_playbook.result_interpretation_hints
    assert plugin.non_goals == legacy_playbook.non_goals
    assert plugin.handoff_eligible is legacy_playbook.handoff_eligible


def test_clinical_trials_plugin_matches_legacy_record_policy() -> None:
    plugin = ClinicalTrialsSourcePlugin()
    legacy_policy = adapter_source_record_policy("clinical_trials")
    record = {
        "nct_id": "NCT01234567",
        "brief_title": "MED13 trial",
        "overall_status": "RECRUITING",
        "phases": ["PHASE1"],
        "conditions": ["Congenital heart disease"],
        "interventions": [{"name": "Observation"}],
        "study_type": "OBSERVATIONAL",
    }

    assert legacy_policy is not None
    assert plugin.handoff_target_kind == legacy_policy.handoff_target_kind
    assert plugin.direct_search_supported is legacy_policy.direct_search_supported
    assert plugin.provider_external_id(record) == legacy_policy.provider_external_id(record)
    assert plugin.recommends_variant_aware(record) is legacy_policy.recommends_variant_aware(record)
    assert plugin.normalize_record(record) == legacy_policy.normalize_record(record)


def test_clinical_trials_plugin_matches_legacy_extraction_policy() -> None:
    plugin = ClinicalTrialsSourcePlugin()
    legacy_policy = adapter_extraction_policy_for_source("clinical_trials")
    record = {
        "nct_id": "NCT01234567",
        "brief_title": "MED13 trial",
        "overall_status": "RECRUITING",
        "conditions": ["Congenital heart disease"],
    }

    assert plugin.review_policy.source_key == legacy_policy.source_key
    assert plugin.review_policy.proposal_type == legacy_policy.proposal_type
    assert plugin.review_policy.review_type == legacy_policy.review_type
    assert plugin.review_policy.evidence_role == legacy_policy.evidence_role
    assert plugin.review_policy.limitations == legacy_policy.limitations
    assert plugin.review_policy.normalized_fields == legacy_policy.normalized_fields
    assert plugin.normalized_extraction_payload(record) == (
        adapter_normalized_extraction_payload(
            source_key="clinical_trials",
            record=record,
        )
    )
    assert plugin.proposal_summary("Relevant trial.") == adapter_proposal_summary(
        source_key="clinical_trials",
        selection_reason="Relevant trial.",
    )
    assert plugin.review_item_summary("Relevant trial.") == adapter_review_item_summary(
        source_key="clinical_trials",
        selection_reason="Relevant trial.",
    )


def test_clinical_trials_plugin_builds_candidate_context() -> None:
    plugin = ClinicalTrialsSourcePlugin()

    context = plugin.build_candidate_context(
        {
            "nct_id": "NCT01234567",
            "brief_title": "MED13 trial",
            "overall_status": "RECRUITING",
        },
    ).to_json()

    assert context["source_key"] == "clinical_trials"
    assert context["source_family"] == "clinical"
    assert context["provider_external_id"] == "NCT01234567"
    assert context["variant_aware_recommended"] is False
    assert context["normalized_record"] == {
        "nct_id": "NCT01234567",
        "title": "MED13 trial",
        "status": "RECRUITING",
    }
    assert context["extraction_policy"]["proposal_type"] == "clinical_evidence_candidate"


@pytest.mark.asyncio
async def test_source_search_runner_dispatches_clinical_trials_plugin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = ClinicalTrialsSourcePlugin(gateway_factory=lambda: _FakeClinicalGateway())

    monkeypatch.setattr(
        "artana_evidence_api.evidence_selection_source_search.source_plugin_for_execution",
        lambda source_key, **_: plugin if source_key == "clinical_trials" else None,
    )

    result = await EvidenceSelectionSourceSearchRunner().run_search(
        space_id=uuid4(),
        created_by=uuid4(),
        source_search=EvidenceSelectionLiveSourceSearch(
            source_key="clinical_trials",
            query_payload={"query": "MED13 congenital heart disease"},
            max_records=1,
        ),
        store=InMemoryDirectSourceSearchStore(),
    )

    assert result.source_key == "clinical_trials"
    assert result.query == "MED13 congenital heart disease"
    assert result.max_results == 1
    assert result.record_count == 1
    assert result.records == [{"nct_id": "NCT01234567", "brief_title": "MED13 trial"}]


class _FakeClinicalGateway:
    async def fetch_records_async(
        self,
        *,
        query: str,
        max_results: int = 20,
    ) -> ClinicalTrialsGatewayFetchResult:
        assert query == "MED13 congenital heart disease"
        assert max_results == 1
        return ClinicalTrialsGatewayFetchResult(
            records=[
                {
                    "nct_id": "NCT01234567",
                    "brief_title": "MED13 trial",
                },
            ],
            fetched_records=1,
        )
