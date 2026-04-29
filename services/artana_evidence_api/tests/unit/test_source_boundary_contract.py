"""Contract tests for source-boundary policy helpers."""

from __future__ import annotations

import ast
from pathlib import Path

from artana_evidence_api.source_adapters import require_source_adapter, source_adapters
from artana_evidence_api.source_registry import (
    direct_search_source_keys,
    get_source_definition,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_EVIDENCE_API_ROOT = _REPO_ROOT / "services" / "artana_evidence_api"
_SOURCE_ADAPTER_FILE = _EVIDENCE_API_ROOT / "source_adapters.py"
_ADAPTER_ONLY_MODULES = frozenset(
    (
        "artana_evidence_api.evidence_selection_extraction_policy",
        "artana_evidence_api.evidence_selection_source_playbooks",
        "artana_evidence_api.source_policies",
    ),
)
_PRIVATE_HELPER_MODULES = _ADAPTER_ONLY_MODULES | frozenset(
    ("artana_evidence_api.evidence_selection_source_search",),
)
_ADAPTER_ONLY_IMPORTS = {
    "artana_evidence_api.evidence_selection_source_search": {
        "adapter_validate_live_source_search",
    },
}
_FORBIDDEN_SOURCE_DOCUMENT_IMPORTS = {
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
    adapter_keys = {adapter.source_key for adapter in source_adapters()}

    assert adapter_keys == set(direct_search_source_keys())
    for adapter in source_adapters():
        definition = get_source_definition(adapter.source_key)
        assert definition is not None
        assert adapter.source_family == definition.source_family
        assert adapter.request_schema_ref == definition.request_schema_ref
        assert adapter.result_schema_ref == definition.result_schema_ref
        assert adapter.handoff_target_kind == "source_document"


def test_simple_source_boundary_policy_matches_registry() -> None:
    adapter = require_source_adapter("clinical_trials")
    definition = get_source_definition("clinical_trials")

    assert definition is not None
    assert adapter.source_key == definition.source_key
    assert adapter.source_family == definition.source_family
    assert adapter.direct_search_supported is definition.direct_search_enabled
    assert adapter.request_schema_ref == definition.request_schema_ref
    assert adapter.result_schema_ref == definition.result_schema_ref
    assert adapter.handoff_target_kind == "source_document"
    assert adapter.provider_external_id({"nct_id": "NCT01234567"}) == "NCT01234567"
    assert adapter.recommends_variant_aware({"nct_id": "NCT01234567"}) is False
    assert adapter.normalize_record(
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
    adapter = require_source_adapter("clinvar")
    definition = get_source_definition("clinvar")

    assert definition is not None
    assert adapter.source_key == definition.source_key
    assert adapter.source_family == definition.source_family
    assert adapter.direct_search_supported is definition.direct_search_enabled
    assert adapter.request_schema_ref == definition.request_schema_ref
    assert adapter.result_schema_ref == definition.result_schema_ref
    assert adapter.handoff_target_kind == "source_document"
    assert adapter.provider_external_id(
        {"accession": "VCV000012345", "variation_id": 12345},
    ) == "VCV000012345"
    assert adapter.recommends_variant_aware({"accession": "VCV000012345"}) is True
    assert adapter.recommends_variant_aware({"hgvs": 12345}) is False
    assert adapter.recommends_variant_aware({"title": "BRCA1 gene overview"}) is False
    assert adapter.normalize_record({"conditions": {}}) == {}
    assert adapter.normalize_record(
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
        if "tests" in path.parts or path == _SOURCE_ADAPTER_FILE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        relative_path = path.relative_to(_REPO_ROOT)
        module_aliases = _source_helper_module_aliases(
            tree=tree,
            relative_path=relative_path,
            violations=violations,
        )
        violations.extend(
            _private_source_helper_attribute_violations(
                tree=tree,
                relative_path=relative_path,
                module_aliases=module_aliases,
            ),
        )

    assert violations == []


def _source_helper_module_aliases(
    *,
    tree: ast.AST,
    relative_path: Path,
    violations: list[str],
) -> dict[str, str]:
    module_aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            _record_source_helper_from_import_violation(
                node=node,
                relative_path=relative_path,
                violations=violations,
            )
        elif isinstance(node, ast.Import):
            module_aliases.update(
                _record_source_helper_module_import_violation(
                    node=node,
                    relative_path=relative_path,
                    violations=violations,
                ),
            )
    return module_aliases


def _record_source_helper_from_import_violation(
    *,
    node: ast.ImportFrom,
    relative_path: Path,
    violations: list[str],
) -> None:
    if node.module in _ADAPTER_ONLY_MODULES:
        violations.append(
            f"{relative_path} imports source-owned helpers from {node.module}",
        )
    private_imports = sorted(
        alias.name
        for alias in node.names
        if node.module in _PRIVATE_HELPER_MODULES
        and (
            alias.name.startswith("_")
            or alias.name in _ADAPTER_ONLY_IMPORTS.get(node.module, set())
        )
    )
    if private_imports:
        violations.append(
            f"{relative_path} imports {', '.join(private_imports)} from {node.module}",
        )
    forbidden_names = _FORBIDDEN_SOURCE_DOCUMENT_IMPORTS.get(node.module)
    if forbidden_names is None:
        return
    imported = {alias.name for alias in node.names}
    bypassed = sorted(imported & forbidden_names)
    if bypassed:
        violations.append(
            f"{relative_path} imports {', '.join(bypassed)} from {node.module}",
        )


def _record_source_helper_module_import_violation(
    *,
    node: ast.Import,
    relative_path: Path,
    violations: list[str],
) -> dict[str, str]:
    module_aliases: dict[str, str] = {}
    for alias in node.names:
        if alias.name not in _PRIVATE_HELPER_MODULES:
            continue
        module_aliases[alias.asname or alias.name] = alias.name
        if alias.name in _ADAPTER_ONLY_MODULES:
            violations.append(
                f"{relative_path} imports source-owned module {alias.name}",
            )
    return module_aliases


def _private_source_helper_attribute_violations(
    *,
    tree: ast.AST,
    relative_path: Path,
    module_aliases: dict[str, str],
) -> list[str]:
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if not isinstance(node.value, ast.Name):
            continue
        module_name = module_aliases.get(node.value.id)
        if module_name is None:
            continue
        if (
            not node.attr.startswith("_")
            and node.attr not in _ADAPTER_ONLY_IMPORTS.get(module_name, set())
        ):
            continue
        violations.append(
            f"{relative_path} accesses private source helper "
            f"{module_name}.{node.attr}",
        )
    return violations
