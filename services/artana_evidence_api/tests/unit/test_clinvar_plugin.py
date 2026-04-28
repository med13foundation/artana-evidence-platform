"""ClinVar source plugin parity and execution tests."""

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
)
from artana_evidence_api.source_enrichment_bridges import ClinVarQueryConfig
from artana_evidence_api.source_plugins.clinvar import ClinVarSourcePlugin
from artana_evidence_api.source_plugins.contracts import (
    EvidenceSelectionSourceSearchError,
    SourceSearchExecutionContext,
)
from artana_evidence_api.source_policies import adapter_source_record_policy
from artana_evidence_api.source_registry import get_source_definition
from artana_evidence_api.types.common import JSONObject
from pydantic import ValidationError


def test_clinvar_plugin_matches_legacy_metadata() -> None:
    plugin = ClinVarSourcePlugin()
    definition = get_source_definition("clinvar")

    assert definition is not None
    assert plugin.source_definition() == definition
    assert plugin.source_key == definition.source_key
    assert plugin.source_family == definition.source_family
    assert plugin.display_name == definition.display_name
    assert plugin.request_schema_ref == definition.request_schema_ref
    assert plugin.result_schema_ref == definition.result_schema_ref


def test_clinvar_plugin_matches_legacy_query_playbook() -> None:
    plugin = ClinVarSourcePlugin()
    legacy_playbook = adapter_source_query_playbook("clinvar")
    intent = PlannedSourceIntent(
        source_key="clinvar",
        gene_symbol=" brca1 ",
        evidence_role="variant assertion",
        reason="Search ClinVar.",
    )

    assert legacy_playbook is not None
    assert plugin.build_query_payload(intent) == legacy_playbook.build_payload(intent)
    assert (
        plugin.supported_objective_intents
        == legacy_playbook.supported_objective_intents
    )
    assert (
        plugin.result_interpretation_hints
        == legacy_playbook.result_interpretation_hints
    )
    assert plugin.non_goals == legacy_playbook.non_goals
    assert plugin.handoff_eligible is legacy_playbook.handoff_eligible


def test_clinvar_plugin_matches_legacy_record_policy() -> None:
    plugin = ClinVarSourcePlugin()
    legacy_policy = adapter_source_record_policy("clinvar")
    record = _clinvar_record()

    assert legacy_policy is not None
    assert plugin.handoff_target_kind == legacy_policy.handoff_target_kind
    assert plugin.direct_search_supported is legacy_policy.direct_search_supported
    assert plugin.provider_external_id(record) == legacy_policy.provider_external_id(
        record
    )
    assert plugin.recommends_variant_aware(
        record
    ) is legacy_policy.recommends_variant_aware(record)
    assert plugin.normalize_record(record) == legacy_policy.normalize_record(record)


def test_clinvar_normalized_record_preserves_legacy_key_surface() -> None:
    plugin = ClinVarSourcePlugin()
    legacy_policy = adapter_source_record_policy("clinvar")

    assert legacy_policy is not None
    assert plugin.normalize_record(_clinvar_record()) == {
        "accession": "VCV000012345",
        "variation_id": 12345,
        "gene_symbol": "BRCA1",
        "title": "NM_007294.4(BRCA1):c.5266dupC",
        "clinical_significance": "Pathogenic",
        "conditions": ["Breast-ovarian cancer, familial 1"],
        "hgvs": "NM_007294.4:c.5266dupC",
    }
    assert plugin.normalize_record(_clinvar_record()) == legacy_policy.normalize_record(
        _clinvar_record(),
    )


@pytest.mark.parametrize(
    "record",
    [
        {"variant_aware_recommended": True},
        {"variant_aware_recommended": True, "accession": "ABC000012345"},
        {"hgvs": "NM_007294.4:c.5266dupC"},
        {"variant_aware_recommended": False, "hgvs": "NM_007294.4:c.5266dupC"},
        {"hgvs_notation": "NM_007294.4:c.5266dupC"},
        {"hgvs_c": "c.5266dupC"},
        {"hgvs_p": "p.Gln1756Profs"},
        {"accession": "vcv000012345.1"},
        {"accession": "VCV000012345.1"},
        {"accession": "RCV000012345"},
        {"accession": "SCV000012345"},
        {"title": "NM_007294.4(BRCA1):c.5266dupC"},
        {"title": "NP_009225.1(BRCA1):p.Gln1756Profs"},
        {"title": "NC_000017.11:g.43082434dup"},
        {"title": "NC_012920.1:m.3243A>G"},
    ],
)
def test_clinvar_variant_aware_true_fixtures_match_legacy(record: JSONObject) -> None:
    plugin = ClinVarSourcePlugin()
    legacy_policy = adapter_source_record_policy("clinvar")

    assert legacy_policy is not None
    assert plugin.recommends_variant_aware(record) is True
    assert plugin.recommends_variant_aware(
        record
    ) is legacy_policy.recommends_variant_aware(
        record,
    )


@pytest.mark.parametrize(
    "record",
    [
        {},
        {"variant_aware_recommended": False},
        {"accession": "ABC000012345"},
        {"accession": "VCV-nope"},
        {"title": "BRCA1 clinical significance summary"},
        {"title": "BRCA1 colon separated text"},
    ],
)
def test_clinvar_variant_aware_false_fixtures_match_legacy(record: JSONObject) -> None:
    plugin = ClinVarSourcePlugin()
    legacy_policy = adapter_source_record_policy("clinvar")

    assert legacy_policy is not None
    assert plugin.recommends_variant_aware(record) is False
    assert plugin.recommends_variant_aware(
        record
    ) is legacy_policy.recommends_variant_aware(
        record,
    )


def test_clinvar_provider_external_id_preserves_legacy_string_only_behavior() -> None:
    plugin = ClinVarSourcePlugin()
    legacy_policy = adapter_source_record_policy("clinvar")
    records: tuple[JSONObject, ...] = (
        {"accession": " VCV000012345 "},
        {"clinvar_id": " 12345 "},
        {"variation_id": " 67890 "},
        {"variation_id": 67890},
    )

    assert legacy_policy is not None
    for record in records:
        assert plugin.provider_external_id(
            record
        ) == legacy_policy.provider_external_id(
            record,
        )


def test_clinvar_plugin_matches_legacy_extraction_policy() -> None:
    plugin = ClinVarSourcePlugin()
    legacy_policy = adapter_extraction_policy_for_source("clinvar")
    record = _clinvar_record()

    assert plugin.review_policy.source_key == legacy_policy.source_key
    assert plugin.review_policy.proposal_type == legacy_policy.proposal_type
    assert plugin.review_policy.review_type == legacy_policy.review_type
    assert plugin.review_policy.evidence_role == legacy_policy.evidence_role
    assert plugin.review_policy.limitations == legacy_policy.limitations
    assert plugin.review_policy.normalized_fields == legacy_policy.normalized_fields
    assert plugin.normalized_extraction_payload(record) == (
        adapter_normalized_extraction_payload(
            source_key="clinvar",
            record=record,
        )
    )
    assert plugin.proposal_summary("Relevant variant.") == adapter_proposal_summary(
        source_key="clinvar",
        selection_reason="Relevant variant.",
    )
    assert plugin.review_item_summary(
        "Relevant variant."
    ) == adapter_review_item_summary(
        source_key="clinvar",
        selection_reason="Relevant variant.",
    )


def test_clinvar_plugin_builds_candidate_context() -> None:
    plugin = ClinVarSourcePlugin()

    context = plugin.build_candidate_context(_clinvar_record()).to_json()

    assert context["source_key"] == "clinvar"
    assert context["source_family"] == "variant"
    assert context["provider_external_id"] == "VCV000012345"
    assert context["variant_aware_recommended"] is True
    assert context["normalized_record"] == {
        "accession": "VCV000012345",
        "variation_id": 12345,
        "gene_symbol": "BRCA1",
        "title": "NM_007294.4(BRCA1):c.5266dupC",
        "clinical_significance": "Pathogenic",
        "conditions": ["Breast-ovarian cancer, familial 1"],
        "hgvs": "NM_007294.4:c.5266dupC",
    }
    assert context["extraction_policy"]["proposal_type"] == (
        "variant_evidence_candidate"
    )


def test_clinvar_plugin_validates_live_search_source_key() -> None:
    plugin = ClinVarSourcePlugin()

    with pytest.raises(
        EvidenceSelectionSourceSearchError,
        match="ClinVar plugin requires canonical source_key 'clinvar'",
    ):
        plugin.validate_live_search(
            EvidenceSelectionLiveSourceSearch(
                source_key="pubmed",
                query_payload={"gene_symbol": "BRCA1"},
            ),
        )


def test_clinvar_plugin_validates_live_search_payload() -> None:
    plugin = ClinVarSourcePlugin()

    plugin.validate_live_search(
        EvidenceSelectionLiveSourceSearch(
            source_key="clinvar",
            query_payload={"gene_symbol": " brca1 "},
            max_records=5,
        ),
    )


def test_clinvar_plugin_preserves_pydantic_validation_error_contract() -> None:
    plugin = ClinVarSourcePlugin()

    with pytest.raises(ValidationError):
        plugin.validate_live_search(
            EvidenceSelectionLiveSourceSearch(
                source_key="clinvar",
                query_payload={},
            ),
        )


@pytest.mark.asyncio
async def test_clinvar_plugin_reports_unavailable_gateway() -> None:
    plugin = ClinVarSourcePlugin(gateway_factory=lambda: None)

    with pytest.raises(
        EvidenceSelectionSourceSearchError,
        match="ClinVar gateway is unavailable.",
    ):
        await plugin.run_direct_search(
            context=SourceSearchExecutionContext(
                space_id=uuid4(),
                created_by=uuid4(),
                store=InMemoryDirectSourceSearchStore(),
            ),
            search=EvidenceSelectionLiveSourceSearch(
                source_key="clinvar",
                query_payload={"gene_symbol": "BRCA1"},
            ),
        )


@pytest.mark.asyncio
async def test_clinvar_plugin_runs_direct_search() -> None:
    gateway = _FakeClinVarGateway()
    plugin = ClinVarSourcePlugin(gateway_factory=lambda: gateway)
    store = InMemoryDirectSourceSearchStore()
    space_id = uuid4()

    result = await plugin.run_direct_search(
        context=SourceSearchExecutionContext(
            space_id=space_id,
            created_by=uuid4(),
            store=store,
        ),
        search=EvidenceSelectionLiveSourceSearch(
            source_key="clinvar",
            query_payload={
                "gene_symbol": " brca1 ",
                "clinical_significance": [" Pathogenic "],
            },
            max_records=1,
        ),
    )

    assert result.source_key == "clinvar"
    assert result.space_id == space_id
    assert result.query == "BRCA1"
    assert result.gene_symbol == "BRCA1"
    assert result.clinical_significance == ["Pathogenic"]
    assert result.max_results == 1
    assert result.record_count == 1
    assert result.records == [_clinvar_record()]
    assert result.source_capture.source_key == "clinvar"
    assert result.source_capture.external_id == "VCV000012345"
    assert gateway.configs == [
        ClinVarQueryConfig(
            query="BRCA1 ClinVar",
            gene_symbol="BRCA1",
            clinical_significance=("Pathogenic",),
            max_results=1,
        ),
    ]


def _clinvar_record() -> JSONObject:
    return {
        "clinvar_id": "123",
        "accession": "VCV000012345",
        "variation_id": 12345,
        "title": "NM_007294.4(BRCA1):c.5266dupC",
        "gene_symbol": "BRCA1",
        "clinical_significance": "Pathogenic",
        "conditions": ["Breast-ovarian cancer, familial 1"],
        "review_status": "criteria provided, multiple submitters",
        "variation_type": "duplication",
        "hgvs": "NM_007294.4:c.5266dupC",
        "source": "clinvar",
    }


class _FakeClinVarGateway:
    def __init__(self) -> None:
        self.configs: list[ClinVarQueryConfig] = []

    async def fetch_records(self, config: ClinVarQueryConfig) -> list[JSONObject]:
        self.configs.append(config)
        return [_clinvar_record()]
