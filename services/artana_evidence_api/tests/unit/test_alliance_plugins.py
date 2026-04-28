"""MGI and ZFIN Alliance-family plugin parity tests."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

import pytest
from artana_evidence_api.alliance_gene_gateways import AllianceGeneGatewayFetchResult
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
from artana_evidence_api.source_plugins.contracts import SourceSearchExecutionContext
from artana_evidence_api.source_plugins.mgi import MGISourcePlugin
from artana_evidence_api.source_plugins.zfin import ZFINSourcePlugin
from artana_evidence_api.source_policies import adapter_source_record_policy
from artana_evidence_api.source_registry import get_source_definition
from artana_evidence_api.types.common import JSONObject

AlliancePlugin = MGISourcePlugin | ZFINSourcePlugin


def _mgi_record() -> JSONObject:
    return {
        "mgi_id": "MGI:1919711",
        "gene_symbol": "Med13",
        "gene_name": "mediator complex subunit 13",
        "species": "Mus musculus",
        "phenotype_statements": ["abnormal heart morphology"],
        "disease_associations": [{"name": "heart disease", "do_id": "DOID:114"}],
    }


def _zfin_record() -> JSONObject:
    return {
        "zfin_id": "ZDB-GENE-040426-1432",
        "gene_symbol": "med13",
        "gene_name": "mediator complex subunit 13",
        "species": "Danio rerio",
        "phenotype_statements": ["abnormal cardiac ventricle morphology"],
        "expression_terms": ["heart"],
    }


@pytest.mark.parametrize(
    ("source_key", "plugin"),
    [("mgi", MGISourcePlugin()), ("zfin", ZFINSourcePlugin())],
)
def test_alliance_plugins_match_legacy_metadata(
    source_key: str,
    plugin: AlliancePlugin,
) -> None:
    definition = get_source_definition(source_key)

    assert definition is not None
    assert plugin.source_definition() == definition
    assert plugin.source_key == definition.source_key
    assert plugin.source_family == definition.source_family
    assert plugin.display_name == definition.display_name
    assert plugin.request_schema_ref == definition.request_schema_ref
    assert plugin.result_schema_ref == definition.result_schema_ref


@pytest.mark.parametrize(
    ("source_key", "plugin", "intent"),
    [
        (
            "mgi",
            MGISourcePlugin(),
            PlannedSourceIntent(
                source_key="mgi",
                gene_symbol="Med13",
                phenotype="cardiac phenotype",
                evidence_role="mouse model",
                reason="Search mouse model evidence.",
            ),
        ),
        (
            "zfin",
            ZFINSourcePlugin(),
            PlannedSourceIntent(
                source_key="zfin",
                gene_symbol="med13",
                disease="heart development",
                evidence_role="zebrafish model",
                reason="Search zebrafish model evidence.",
            ),
        ),
    ],
)
def test_alliance_plugins_match_legacy_query_playbooks(
    source_key: str,
    plugin: AlliancePlugin,
    intent: PlannedSourceIntent,
) -> None:
    legacy_playbook = adapter_source_query_playbook(source_key)

    assert legacy_playbook is not None
    assert plugin.build_query_payload(intent) == legacy_playbook.build_payload(intent)
    assert plugin.supported_objective_intents == legacy_playbook.supported_objective_intents
    assert plugin.result_interpretation_hints == legacy_playbook.result_interpretation_hints
    assert plugin.non_goals == legacy_playbook.non_goals
    assert plugin.handoff_eligible is legacy_playbook.handoff_eligible


@pytest.mark.parametrize(
    ("source_key", "plugin", "record"),
    [("mgi", MGISourcePlugin(), _mgi_record()), ("zfin", ZFINSourcePlugin(), _zfin_record())],
)
def test_alliance_plugins_match_legacy_record_policies(
    source_key: str,
    plugin: AlliancePlugin,
    record: JSONObject,
) -> None:
    legacy_policy = adapter_source_record_policy(source_key)

    assert legacy_policy is not None
    assert plugin.handoff_target_kind == legacy_policy.handoff_target_kind
    assert plugin.direct_search_supported is legacy_policy.direct_search_supported
    assert plugin.provider_external_id(record) == legacy_policy.provider_external_id(record)
    assert plugin.recommends_variant_aware(record) is legacy_policy.recommends_variant_aware(record)
    assert plugin.normalize_record(record) == legacy_policy.normalize_record(record)


@pytest.mark.parametrize(
    ("source_key", "plugin", "record"),
    [("mgi", MGISourcePlugin(), _mgi_record()), ("zfin", ZFINSourcePlugin(), _zfin_record())],
)
def test_alliance_plugins_match_legacy_extraction_policies(
    source_key: str,
    plugin: AlliancePlugin,
    record: JSONObject,
) -> None:
    legacy_policy = adapter_extraction_policy_for_source(source_key)

    assert plugin.review_policy.source_key == legacy_policy.source_key
    assert plugin.review_policy.proposal_type == legacy_policy.proposal_type
    assert plugin.review_policy.review_type == legacy_policy.review_type
    assert plugin.review_policy.evidence_role == legacy_policy.evidence_role
    assert plugin.review_policy.limitations == legacy_policy.limitations
    assert plugin.review_policy.normalized_fields == legacy_policy.normalized_fields
    assert plugin.normalized_extraction_payload(record) == (
        adapter_normalized_extraction_payload(source_key=source_key, record=record)
    )
    assert plugin.proposal_summary("Relevant model.") == adapter_proposal_summary(
        source_key=source_key,
        selection_reason="Relevant model.",
    )
    assert plugin.review_item_summary("Relevant model.") == adapter_review_item_summary(
        source_key=source_key,
        selection_reason="Relevant model.",
    )


@pytest.mark.parametrize(
    ("plugin", "record", "provider_id", "proposal_type"),
    [
        (
            MGISourcePlugin(),
            _mgi_record(),
            "MGI:1919711",
            "model_organism_evidence_candidate",
        ),
        (
            ZFINSourcePlugin(),
            _zfin_record(),
            "ZDB-GENE-040426-1432",
            "model_organism_evidence_candidate",
        ),
    ],
)
def test_alliance_plugins_build_candidate_context(
    plugin: AlliancePlugin,
    record: JSONObject,
    provider_id: str,
    proposal_type: str,
) -> None:
    context = plugin.build_candidate_context(record).to_json()

    assert context["source_key"] == plugin.source_key
    assert context["source_family"] == "model_organism"
    assert context["provider_external_id"] == provider_id
    assert context["variant_aware_recommended"] is False
    assert context["normalized_record"] == plugin.normalize_record(record)
    assert context["extraction_policy"]["proposal_type"] == proposal_type


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("plugin", "source_key", "record"),
    [("mgi", "mgi", _mgi_record()), ("zfin", "zfin", _zfin_record())],
)
async def test_alliance_plugins_delegate_direct_search_execution(
    plugin: str,
    source_key: str,
    record: JSONObject,
) -> None:
    source_plugin: AlliancePlugin
    if plugin == "mgi":
        source_plugin = MGISourcePlugin(
            gateway_factory=lambda: _FakeAllianceGateway(records=[record]),
        )
    else:
        source_plugin = ZFINSourcePlugin(
            gateway_factory=lambda: _FakeAllianceGateway(records=[record]),
        )

    result = await source_plugin.run_direct_search(
        context=SourceSearchExecutionContext(
            space_id=uuid4(),
            created_by=uuid4(),
            store=InMemoryDirectSourceSearchStore(),
        ),
        search=EvidenceSelectionLiveSourceSearch(
            source_key=source_key,
            query_payload={"query": "MED13"},
            max_records=1,
        ),
    )

    assert result.source_key == source_key
    assert result.query == "MED13"
    assert result.max_results == 1
    assert result.record_count == 1
    assert result.records == [record]


class _FakeAllianceGateway:
    def __init__(self, *, records: Sequence[JSONObject]) -> None:
        self._records = list(records)

    async def fetch_records_async(
        self,
        *,
        query: str,
        max_results: int = 20,
    ) -> AllianceGeneGatewayFetchResult:
        assert query == "MED13"
        assert max_results == 1
        return AllianceGeneGatewayFetchResult(
            records=[dict(record) for record in self._records],
            fetched_records=len(self._records),
        )
