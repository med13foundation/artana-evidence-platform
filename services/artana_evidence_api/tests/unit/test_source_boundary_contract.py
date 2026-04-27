"""Contract tests for source-boundary policy helpers."""

from __future__ import annotations

import ast
from pathlib import Path

from artana_evidence_api.source_policies import (
    source_record_policies,
    source_record_policy,
)
from artana_evidence_api.source_registry import (
    direct_search_source_keys,
    get_source_definition,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_EVIDENCE_API_ROOT = _REPO_ROOT / "services" / "artana_evidence_api"
_SOURCE_ADAPTER_INTERNAL_MODULES = frozenset(
    {
        "evidence_selection_extraction_policy.py",
        "evidence_selection_source_playbooks.py",
        "evidence_selection_source_search.py",
        "source_adapters.py",
        "source_policies.py",
    },
)
_FORBIDDEN_SOURCE_HELPER_IMPORTS = {
    "artana_evidence_api.evidence_selection_extraction_policy": {
        "extraction_policy_for_source",
    },
    "artana_evidence_api.evidence_selection_source_playbooks": {
        "source_query_playbook",
    },
    "artana_evidence_api.evidence_selection_source_search": {
        "validate_live_source_search",
    },
    "artana_evidence_api.source_policies": {
        "source_record_policy",
    },
    "artana_evidence_api.source_document_bridges": {
        "SourceDocument",
        "SourceDocumentRepositoryProtocol",
        "build_source_document",
        "build_source_document_repository",
        "create_observation_bridge_entity_recognition_service",
        "source_document_extraction_status_value",
        "source_document_id",
        "source_document_metadata",
        "source_document_model_copy",
    },
}


def test_every_direct_search_source_has_record_policy() -> None:
    policy_keys = {policy.source_key for policy in source_record_policies()}

    assert policy_keys == set(direct_search_source_keys())
    for policy in source_record_policies():
        definition = get_source_definition(policy.source_key)
        assert definition is not None
        assert policy.source_family == definition.source_family
        assert policy.request_schema_ref == definition.request_schema_ref
        assert policy.result_schema_ref == definition.result_schema_ref
        assert policy.handoff_target_kind == "source_document"


def test_simple_source_boundary_policy_matches_registry() -> None:
    policy = source_record_policy("clinical_trials")
    definition = get_source_definition("clinical_trials")

    assert policy is not None
    assert definition is not None
    assert policy.source_key == definition.source_key
    assert policy.source_family == definition.source_family
    assert policy.direct_search_supported is definition.direct_search_enabled
    assert policy.request_schema_ref == definition.request_schema_ref
    assert policy.result_schema_ref == definition.result_schema_ref
    assert policy.handoff_target_kind == "source_document"
    assert policy.provider_external_id({"nct_id": "NCT01234567"}) == "NCT01234567"
    assert policy.recommends_variant_aware({"nct_id": "NCT01234567"}) is False
    assert policy.normalize_record(
        {
            "nct_id": "NCT01234567",
            "brief_title": "MED13 trial",
            "overall_status": "RECRUITING",
            "phases": ["PHASE1"],
            "conditions": ["Congenital heart disease"],
            "interventions": [{"name": "Observation"}],
            "study_type": "OBSERVATIONAL",
        },
    ) == {
        "nct_id": "NCT01234567",
        "title": "MED13 trial",
        "status": "RECRUITING",
        "phase": ["PHASE1"],
        "conditions": ["Congenital heart disease"],
        "interventions": ["Observation"],
        "study_type": "OBSERVATIONAL",
    }


def test_variant_aware_source_boundary_policy_matches_registry() -> None:
    policy = source_record_policy("clinvar")
    definition = get_source_definition("clinvar")

    assert policy is not None
    assert definition is not None
    assert policy.source_key == definition.source_key
    assert policy.source_family == definition.source_family
    assert policy.direct_search_supported is definition.direct_search_enabled
    assert policy.request_schema_ref == definition.request_schema_ref
    assert policy.result_schema_ref == definition.result_schema_ref
    assert policy.handoff_target_kind == "source_document"
    assert policy.provider_external_id(
        {"accession": "VCV000012345", "variation_id": 12345},
    ) == "VCV000012345"
    assert policy.recommends_variant_aware({"accession": "VCV000012345"}) is True
    assert policy.recommends_variant_aware({"hgvs": 12345}) is False
    assert policy.recommends_variant_aware({"title": "BRCA1 gene overview"}) is False
    assert policy.normalize_record({"conditions": {}}) == {}
    assert policy.normalize_record(
        {
            "accession": "VCV000012345",
            "variation_id": 12345,
            "gene_symbol": "BRCA1",
            "title": "NM_007294.4(BRCA1):c.5266dupC",
            "clinical_significance": {"description": "Pathogenic"},
            "conditions": ["Breast cancer"],
            "hgvs": "NM_007294.4:c.5266dupC",
        },
    ) == {
        "accession": "VCV000012345",
        "variation_id": 12345,
        "gene_symbol": "BRCA1",
        "title": "NM_007294.4(BRCA1):c.5266dupC",
        "clinical_significance": {"description": "Pathogenic"},
        "conditions": ["Breast cancer"],
        "hgvs": "NM_007294.4:c.5266dupC",
    }


def test_production_callers_use_source_adapters_for_source_owned_behavior() -> None:
    violations: list[str] = []
    for path in sorted(_EVIDENCE_API_ROOT.rglob("*.py")):
        if "tests" in path.parts or path.name in _SOURCE_ADAPTER_INTERNAL_MODULES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue
            forbidden_names = _FORBIDDEN_SOURCE_HELPER_IMPORTS.get(node.module)
            if forbidden_names is None:
                continue
            imported = {alias.name for alias in node.names}
            bypassed = sorted(imported & forbidden_names)
            if bypassed:
                relative_path = path.relative_to(_REPO_ROOT)
                violations.append(
                    f"{relative_path} imports {', '.join(bypassed)} from {node.module}",
                )

    assert violations == []
