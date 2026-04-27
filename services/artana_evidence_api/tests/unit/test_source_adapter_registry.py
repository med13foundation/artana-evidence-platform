"""Tests for the typed direct-search source adapter registry."""

from __future__ import annotations

import pytest
from artana_evidence_api.evidence_selection_extraction_policy import (
    extraction_policy_for_source,
)
from artana_evidence_api.evidence_selection_source_playbooks import (
    source_query_playbook,
)
from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
    EvidenceSelectionSourceSearchError,
)
from artana_evidence_api.source_adapters import (
    SourceAdapterRegistryError,
    require_source_adapter,
    source_adapter,
    source_adapter_keys,
    source_adapters,
)
from artana_evidence_api.source_policies import source_record_policy
from artana_evidence_api.source_registry import (
    direct_search_source_keys,
    get_source_definition,
)
from artana_evidence_api.types.common import JSONObject


def test_source_adapter_registry_matches_direct_search_sources() -> None:
    adapters = source_adapters()
    adapter_keys = [adapter.source_key for adapter in adapters]

    assert tuple(adapter_keys) == direct_search_source_keys()
    assert source_adapter_keys() == direct_search_source_keys()
    assert len(adapter_keys) == len(set(adapter_keys))
    assert source_adapter("clinical-trials") is source_adapter("clinical_trials")
    assert source_adapter("hgnc") is None


@pytest.mark.parametrize("source_key", direct_search_source_keys())
def test_source_adapter_composes_source_owned_contracts(source_key: str) -> None:
    adapter = require_source_adapter(source_key)

    assert adapter.definition() == get_source_definition(source_key)
    assert adapter.query_playbook() == source_query_playbook(source_key)
    assert adapter.record_policy() == source_record_policy(source_key)
    assert adapter.extraction_policy() == extraction_policy_for_source(source_key)
    assert adapter.source_family == adapter.definition().source_family


@pytest.mark.parametrize("source_key", direct_search_source_keys())
def test_source_adapter_validates_live_search_payloads(source_key: str) -> None:
    adapter = require_source_adapter(source_key)

    adapter.validate_live_search(
        EvidenceSelectionLiveSourceSearch(
            source_key=source_key,
            query_payload=_valid_query_payload(source_key),
            max_records=2,
        ),
    )


def test_source_adapter_rejects_source_key_alias_for_validation() -> None:
    adapter = require_source_adapter("clinical_trials")

    with pytest.raises(EvidenceSelectionSourceSearchError, match="canonical"):
        adapter.validate_live_search(
            EvidenceSelectionLiveSourceSearch(
                source_key="clinical-trials",
                query_payload={"query": "MED13 congenital heart disease"},
                max_records=2,
            ),
        )


def test_source_adapter_rejects_mismatched_live_search_source() -> None:
    adapter = require_source_adapter("pubmed")

    with pytest.raises(EvidenceSelectionSourceSearchError, match="cannot validate"):
        adapter.validate_live_search(
            EvidenceSelectionLiveSourceSearch(
                source_key="clinvar",
                query_payload={"gene_symbol": "MED13"},
                max_records=2,
            ),
        )


def test_source_adapter_rejects_invalid_live_search_payload() -> None:
    adapter = require_source_adapter("clinvar")

    with pytest.raises(ValueError, match="gene_symbol"):
        adapter.validate_live_search(
            EvidenceSelectionLiveSourceSearch(
                source_key="clinvar",
                query_payload={"query": "MED13"},
                max_records=2,
            ),
        )


def test_require_source_adapter_rejects_non_direct_search_source() -> None:
    with pytest.raises(SourceAdapterRegistryError, match="No source adapter"):
        require_source_adapter("hgnc")


def test_source_adapter_builds_candidate_context_from_record_policy() -> None:
    adapter = require_source_adapter("clinvar")

    context = adapter.build_candidate_context(
        {
            "accession": "VCV000012345",
            "variation_id": 12345,
            "gene_symbol": "BRCA1",
            "title": "NM_007294.4(BRCA1):c.5266dupC",
            "clinical_significance": {"description": "Pathogenic"},
            "conditions": ["Breast cancer"],
        },
    )

    assert context["source_key"] == "clinvar"
    assert context["source_family"] == "variant"
    assert context["provider_external_id"] == "VCV000012345"
    assert context["variant_aware_recommended"] is True
    assert context["normalized_record"] == {
        "accession": "VCV000012345",
        "variation_id": 12345,
        "gene_symbol": "BRCA1",
        "title": "NM_007294.4(BRCA1):c.5266dupC",
        "clinical_significance": {"description": "Pathogenic"},
        "conditions": ["Breast cancer"],
    }
    assert context["extraction_policy"] == {
        "proposal_type": "variant_evidence_candidate",
        "review_type": "variant_source_record_review",
        "evidence_role": "variant interpretation candidate",
        "limitations": [
            "ClinVar significance depends on submitter evidence and review status.",
            "Variant-level records do not prove disease causality by themselves.",
        ],
        "normalized_fields": [
            "accession",
            "variation_id",
            "gene_symbol",
            "clinical_significance",
            "review_status",
            "condition",
            "title",
        ],
    }


def test_source_adapter_emits_candidate_context_provider_id_when_missing() -> None:
    adapter = require_source_adapter("pubmed")

    context = adapter.build_candidate_context({"title": "MED13 review"})

    assert context["provider_external_id"] is None
    assert context["variant_aware_recommended"] is False
    assert context["normalized_record"] == {"title": "MED13 review"}


def _valid_query_payload(source_key: str) -> JSONObject:
    pubmed_parameters: JSONObject = {"search_term": "MED13"}
    payloads: dict[str, JSONObject] = {
        "pubmed": {"parameters": pubmed_parameters},
        "marrvel": {"gene_symbol": "MED13"},
        "clinvar": {"gene_symbol": "MED13"},
        "clinical_trials": {"query": "MED13 congenital heart disease"},
        "uniprot": {"uniprot_id": "Q9UHV7"},
        "alphafold": {"uniprot_id": "Q9UHV7"},
        "drugbank": {"drugbank_id": "DB08820"},
        "mgi": {"query": "Med13"},
        "zfin": {"query": "med13"},
    }
    return payloads[source_key]
