"""PubMed source plugin parity and execution tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
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
from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
)
from artana_evidence_api.pubmed_discovery import (
    AdvancedQueryParameters,
    DiscoveryProvider,
    DiscoverySearchJob,
    DiscoverySearchStatus,
    PubMedDiscoveryService,
    RunPubmedSearchRequest,
)
from artana_evidence_api.source_plugins.contracts import (
    EvidenceSelectionSourceSearchError,
    SourceSearchExecutionContext,
)
from artana_evidence_api.source_plugins.pubmed import PubMedSourcePlugin
from artana_evidence_api.source_policies import adapter_source_record_policy
from artana_evidence_api.source_registry import get_source_definition


def test_pubmed_plugin_matches_legacy_metadata() -> None:
    plugin = PubMedSourcePlugin()
    definition = get_source_definition("pubmed")

    assert definition is not None
    assert plugin.source_definition() == definition
    assert plugin.source_key == definition.source_key
    assert plugin.source_family == definition.source_family
    assert plugin.display_name == definition.display_name
    assert plugin.request_schema_ref == definition.request_schema_ref
    assert plugin.result_schema_ref == definition.result_schema_ref


def test_pubmed_plugin_matches_legacy_query_playbook() -> None:
    plugin = PubMedSourcePlugin()
    legacy_playbook = adapter_source_query_playbook("pubmed")
    intent = PlannedSourceIntent(
        source_key="pubmed",
        gene_symbol="MED13",
        disease="congenital heart disease",
        phenotype="developmental delay",
        evidence_role="literature",
        reason="Find literature.",
    )

    assert legacy_playbook is not None
    assert plugin.build_query_payload(intent) == legacy_playbook.build_payload(intent)
    assert plugin.supported_objective_intents == legacy_playbook.supported_objective_intents
    assert plugin.result_interpretation_hints == legacy_playbook.result_interpretation_hints
    assert plugin.non_goals == legacy_playbook.non_goals
    assert plugin.handoff_eligible is legacy_playbook.handoff_eligible


def test_pubmed_plugin_matches_legacy_record_policy() -> None:
    plugin = PubMedSourcePlugin()
    legacy_policy = adapter_source_record_policy("pubmed")
    record = _pubmed_record()

    assert legacy_policy is not None
    assert plugin.handoff_target_kind == legacy_policy.handoff_target_kind
    assert plugin.direct_search_supported is legacy_policy.direct_search_supported
    assert plugin.provider_external_id(record) == legacy_policy.provider_external_id(record)
    assert plugin.recommends_variant_aware(record) is legacy_policy.recommends_variant_aware(record)
    assert plugin.normalize_record(record) == legacy_policy.normalize_record(record)


def test_pubmed_plugin_matches_legacy_extraction_policy() -> None:
    plugin = PubMedSourcePlugin()
    legacy_policy = adapter_extraction_policy_for_source("pubmed")
    record = _pubmed_record()

    assert plugin.review_policy.source_key == legacy_policy.source_key
    assert plugin.review_policy.proposal_type == legacy_policy.proposal_type
    assert plugin.review_policy.review_type == legacy_policy.review_type
    assert plugin.review_policy.evidence_role == legacy_policy.evidence_role
    assert plugin.review_policy.limitations == legacy_policy.limitations
    assert plugin.review_policy.normalized_fields == legacy_policy.normalized_fields
    assert plugin.normalized_extraction_payload(record) == (
        adapter_normalized_extraction_payload(
            source_key="pubmed",
            record=record,
        )
    )
    assert plugin.proposal_summary("Relevant paper.") == adapter_proposal_summary(
        source_key="pubmed",
        selection_reason="Relevant paper.",
    )
    assert plugin.review_item_summary("Relevant paper.") == adapter_review_item_summary(
        source_key="pubmed",
        selection_reason="Relevant paper.",
    )


def test_pubmed_plugin_builds_candidate_context_with_pmid_identity() -> None:
    plugin = PubMedSourcePlugin()

    context = plugin.build_candidate_context(_pubmed_record()).to_json()

    assert context["source_key"] == "pubmed"
    assert context["source_family"] == "literature"
    assert context["provider_external_id"] == "12345"
    assert context["variant_aware_recommended"] is False
    assert context["normalized_record"] == {
        "pmid": "12345",
        "title": "MED13 and congenital heart disease",
        "abstract": "A focused abstract.",
        "journal": "Journal of MED13",
        "publication_year": "2025",
    }
    assert context["extraction_policy"]["proposal_type"] == (
        "literature_evidence_candidate"
    )


def test_pubmed_plugin_normalizes_pubdate_to_publication_date() -> None:
    plugin = PubMedSourcePlugin()

    normalized = plugin.normalize_record(
        {
            "pmid": "12345",
            "title": "MED13 and congenital heart disease",
            "journal": "Journal of MED13",
            "pubdate": "2025 Dec",
        },
    )

    assert normalized == {
        "pmid": "12345",
        "title": "MED13 and congenital heart disease",
        "journal": "Journal of MED13",
        "publication_date": "2025 Dec",
    }


def test_pubmed_plugin_prefers_publication_date_over_pubdate() -> None:
    plugin = PubMedSourcePlugin()

    normalized = plugin.normalize_record(
        {
            "pmid": "12345",
            "publication_date": "2025-12-01",
            "pubdate": "2025 Dec",
        },
    )

    assert normalized["publication_date"] == "2025-12-01"


def test_pubmed_plugin_validates_nested_parameters_and_max_records() -> None:
    plugin = PubMedSourcePlugin()

    plugin.validate_live_search(
        EvidenceSelectionLiveSourceSearch(
            source_key="pubmed",
            query_payload={"parameters": {"search_term": "MED13"}},
            max_records=3,
        ),
    )


@pytest.mark.asyncio
async def test_pubmed_plugin_runs_completed_job_as_durable_source_search() -> None:
    owner_id = uuid4()
    space_id = uuid4()
    job_id = uuid4()
    service = _FakePubMedDiscoveryService(
        result=_pubmed_job(
            job_id=job_id,
            owner_id=owner_id,
            space_id=space_id,
            status=DiscoverySearchStatus.COMPLETED,
            total_results=7,
            preview_records=[_pubmed_record()],
        ),
    )
    store = InMemoryDirectSourceSearchStore()
    plugin = PubMedSourcePlugin(
        discovery_service_factory=lambda: _service_context(service),
    )

    result = await plugin.run_direct_search(
        context=SourceSearchExecutionContext(
            space_id=space_id,
            created_by=owner_id,
            store=store,
        ),
        search=EvidenceSelectionLiveSourceSearch(
            source_key="pubmed",
            query_payload={"parameters": {"search_term": "MED13"}},
            max_records=1,
        ),
    )

    assert service.requests == [
        RunPubmedSearchRequest(
            session_id=space_id,
            parameters=AdvancedQueryParameters(
                search_term="MED13",
                max_results=1,
            ),
        ),
    ]
    assert result.source_key == "pubmed"
    assert result.id == job_id
    assert result.total_results == 7
    assert result.record_count == 1
    assert result.records == [_pubmed_record()]
    assert result.source_capture.source_key == "pubmed"
    assert result.source_capture.external_id == str(job_id)
    assert result.source_capture.search_id == str(job_id)
    assert result.source_capture.query_payload["max_results"] == 1


@pytest.mark.asyncio
async def test_pubmed_plugin_rejects_incomplete_jobs() -> None:
    owner_id = uuid4()
    space_id = uuid4()
    service = _FakePubMedDiscoveryService(
        result=_pubmed_job(
            job_id=uuid4(),
            owner_id=owner_id,
            space_id=space_id,
            status=DiscoverySearchStatus.RUNNING,
            total_results=0,
            preview_records=[],
        ),
    )
    plugin = PubMedSourcePlugin(
        discovery_service_factory=lambda: _service_context(service),
    )

    with pytest.raises(
        EvidenceSelectionSourceSearchError,
        match="PubMed search did not complete successfully",
    ):
        await plugin.run_direct_search(
            context=SourceSearchExecutionContext(
                space_id=space_id,
                created_by=owner_id,
                store=InMemoryDirectSourceSearchStore(),
            ),
            search=EvidenceSelectionLiveSourceSearch(
                source_key="pubmed",
                query_payload={"parameters": {"search_term": "MED13"}},
            ),
        )


def _pubmed_record() -> dict[str, object]:
    return {
        "pmid": "12345",
        "title": "MED13 and congenital heart disease",
        "abstract": "A focused abstract.",
        "journal": "Journal of MED13",
        "publication_year": "2025",
    }


def _pubmed_job(
    *,
    job_id: UUID,
    owner_id: UUID,
    space_id: UUID,
    status: DiscoverySearchStatus,
    total_results: int,
    preview_records: list[dict[str, object]],
) -> DiscoverySearchJob:
    timestamp = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)
    return DiscoverySearchJob(
        id=job_id,
        owner_id=owner_id,
        session_id=space_id,
        provider=DiscoveryProvider.PUBMED,
        status=status,
        query_preview="MED13",
        parameters=AdvancedQueryParameters(search_term="MED13", max_results=1),
        total_results=total_results,
        result_metadata={"preview_records": preview_records},
        storage_key="pubmed/jobs/example.json",
        created_at=timestamp,
        updated_at=timestamp,
        completed_at=timestamp if status == DiscoverySearchStatus.COMPLETED else None,
    )


class _FakePubMedDiscoveryService(PubMedDiscoveryService):
    def __init__(self, *, result: DiscoverySearchJob) -> None:
        self.result = result
        self.requests: list[RunPubmedSearchRequest] = []

    async def run_pubmed_search(
        self,
        owner_id: UUID,
        request: RunPubmedSearchRequest,
    ) -> DiscoverySearchJob:
        assert owner_id == self.result.owner_id
        self.requests.append(request)
        return self.result

    def get_search_job(
        self,
        owner_id: UUID,
        job_id: UUID,
    ) -> DiscoverySearchJob | None:
        if owner_id == self.result.owner_id and job_id == self.result.id:
            return self.result
        return None

    def close(self) -> None:
        return None


@contextmanager
def _service_context(
    service: _FakePubMedDiscoveryService,
) -> Iterator[_FakePubMedDiscoveryService]:
    yield service
