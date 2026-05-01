"""Architecture guardrails for source plugins."""

from __future__ import annotations

import ast
from pathlib import Path

from artana_evidence_api.source_plugins.registry import (
    authority_source_plugin_keys,
    document_ingestion_source_plugin_keys,
    source_plugin_keys,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_EVIDENCE_API_ROOT = _REPO_ROOT / "services" / "artana_evidence_api"
_SOURCE_PLUGINS_ROOT = _EVIDENCE_API_ROOT / "source_plugins"
_SOURCE_ORCHESTRATION_MODULES = (
    _EVIDENCE_API_ROOT / "evidence_selection_source_search.py",
    _EVIDENCE_API_ROOT / "evidence_selection_source_playbooks.py",
    _EVIDENCE_API_ROOT / "evidence_selection_extraction_policy.py",
    _EVIDENCE_API_ROOT / "source_adapters.py",
    _EVIDENCE_API_ROOT / "source_policies.py",
    _EVIDENCE_API_ROOT / "source_search_handoff.py",
)
_FORBIDDEN_PLUGIN_IMPORTS = (
    "artana_evidence_api.routers",
    "artana_evidence_api.models",
    "artana_evidence_api.database",
    "artana_evidence_api.bootstrap_proposal_review",
    "artana_evidence_api.document_extraction_review",
    "artana_evidence_api.document_ingestion_support",
    "artana_evidence_api.evidence_selection_review_staging",
    "artana_evidence_api.proposal_actions",
    "artana_evidence_api.proposal_store",
    "artana_evidence_api.review_item_store",
    "artana_evidence_api.source_document_repository",
    "artana_evidence_api.source_document_graph_writer",
    "artana_evidence_api.source_document_models",
    "artana_evidence_api.sqlalchemy_unit_of_work",
    "artana_evidence_db",
    "sqlalchemy",
)


def test_source_plugins_do_not_collapse_into_single_monolith() -> None:
    assert not (_EVIDENCE_API_ROOT / "source_plugins.py").exists()
    assert not (_SOURCE_PLUGINS_ROOT / "authority.py").exists()
    assert not (_SOURCE_PLUGINS_ROOT / "hgnc.py").exists()
    assert not (_SOURCE_PLUGINS_ROOT / "mondo.py").exists()
    assert not (_SOURCE_PLUGINS_ROOT / "ingestion.py").exists()
    assert not (_SOURCE_PLUGINS_ROOT / "pdf.py").exists()
    assert not (_SOURCE_PLUGINS_ROOT / "text.py").exists()
    assert (_SOURCE_PLUGINS_ROOT / "contracts.py").exists()
    assert (_SOURCE_PLUGINS_ROOT / "registry.py").exists()
    assert (_SOURCE_PLUGINS_ROOT / "pubmed.py").exists()
    assert (_SOURCE_PLUGINS_ROOT / "marrvel.py").exists()
    assert (_SOURCE_PLUGINS_ROOT / "clinvar.py").exists()
    assert (_SOURCE_PLUGINS_ROOT / "drugbank.py").exists()
    assert (_SOURCE_PLUGINS_ROOT / "alphafold.py").exists()
    assert (_SOURCE_PLUGINS_ROOT / "gnomad.py").exists()
    assert (_SOURCE_PLUGINS_ROOT / "uniprot.py").exists()
    assert (_SOURCE_PLUGINS_ROOT / "clinical_trials.py").exists()
    assert (_SOURCE_PLUGINS_ROOT / "mgi.py").exists()
    assert (_SOURCE_PLUGINS_ROOT / "zfin.py").exists()
    assert (_SOURCE_PLUGINS_ROOT / "authority" / "base.py").exists()
    assert (_SOURCE_PLUGINS_ROOT / "authority" / "mondo.py").exists()
    assert (_SOURCE_PLUGINS_ROOT / "authority" / "hgnc.py").exists()
    assert (_SOURCE_PLUGINS_ROOT / "ingestion" / "base.py").exists()
    assert (_SOURCE_PLUGINS_ROOT / "ingestion" / "pdf.py").exists()
    assert (_SOURCE_PLUGINS_ROOT / "ingestion" / "text.py").exists()


def test_source_plugin_modules_stay_small_and_focused() -> None:
    oversized_modules: list[str] = []
    limits_by_name = {
        "contracts.py": 450,
        "registry.py": 375,
    }
    for path in sorted(_SOURCE_PLUGINS_ROOT.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        max_lines = limits_by_name.get(path.name, 500)
        if line_count > max_lines:
            oversized_modules.append(f"{path.relative_to(_REPO_ROOT)}:{line_count}")

    assert oversized_modules == []


def test_source_plugin_package_init_has_no_plugin_import_side_effects() -> None:
    tree = ast.parse((_SOURCE_PLUGINS_ROOT / "__init__.py").read_text(encoding="utf-8"))

    imports = [node for node in ast.walk(tree) if isinstance(node, ast.Import | ast.ImportFrom)]

    assert imports == []


def test_source_plugin_registry_uses_explicit_listing_not_decorators() -> None:
    tree = ast.parse((_SOURCE_PLUGINS_ROOT / "registry.py").read_text(encoding="utf-8"))
    registration_decorators = [
        _decorator_name(decorator)
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            and node.decorator_list
        )
        for decorator in node.decorator_list
        if _decorator_name(decorator) not in {"lru_cache"}
    ]

    assert registration_decorators == []


def test_source_plugins_do_not_import_router_or_persistence_layers() -> None:
    violations: list[str] = []

    for path in sorted(_SOURCE_PLUGINS_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                _record_forbidden_plugin_import(
                    module_name=node.module,
                    path=path,
                    violations=violations,
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    _record_forbidden_plugin_import(
                        module_name=alias.name,
                        path=path,
                        violations=violations,
                    )

    assert violations == []


def test_orchestration_modules_do_not_define_per_source_dispatch_maps() -> None:
    migrated_keys = set(source_plugin_keys())
    migrated_keys.update(authority_source_plugin_keys())
    migrated_keys.update(document_ingestion_source_plugin_keys())
    source_map_entries: list[str] = []

    for path in _SOURCE_ORCHESTRATION_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                source_map_entries.extend(
                    f"{path.relative_to(_REPO_ROOT)}:{key.value}"
                    for key in node.keys
                    if (
                        isinstance(key, ast.Constant)
                        and isinstance(key.value, str)
                        and key.value in migrated_keys
                    )
                )
            elif isinstance(node, ast.Call) and _call_name(node.func) == "dict":
                source_map_entries.extend(
                    f"{path.relative_to(_REPO_ROOT)}:{keyword.arg}"
                    for keyword in node.keywords
                    if keyword.arg in migrated_keys
                )

    assert source_map_entries == []


def test_orchestration_modules_do_not_branch_on_source_keys() -> None:
    migrated_keys = set(source_plugin_keys())
    migrated_keys.update(authority_source_plugin_keys())
    migrated_keys.update(document_ingestion_source_plugin_keys())
    branches: list[str] = []

    for path in _SOURCE_ORCHESTRATION_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and _contains_source_key_literal(
                node.test,
                migrated_keys=migrated_keys,
            ):
                branches.append(f"{path.relative_to(_REPO_ROOT)}:if")
            elif isinstance(node, ast.Match):
                subject_name = _name_for_expr(node.subject)
                if "source_key" not in subject_name:
                    continue
                branches.extend(
                    f"{path.relative_to(_REPO_ROOT)}:match"
                    for case in node.cases
                    if _pattern_contains_source_key_literal(
                        case.pattern,
                        migrated_keys=migrated_keys,
                    )
                )

    assert branches == []


def test_production_code_uses_plugin_registry_not_concrete_plugins() -> None:
    allowed_imports = {
        "artana_evidence_api.source_plugins.contracts",
        "artana_evidence_api.source_plugins.registry",
    }
    violations: list[str] = []

    for path in sorted(_EVIDENCE_API_ROOT.rglob("*.py")):
        if _is_relative_to(path, _SOURCE_PLUGINS_ROOT):
            continue
        if "/tests/" in path.as_posix():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for module_name in _imported_modules(tree):
            if module_name in allowed_imports:
                continue
            if module_name.startswith("artana_evidence_api.source_plugins."):
                violations.append(
                    f"{path.relative_to(_REPO_ROOT)} imports {module_name}",
                )

    assert violations == []


def _record_forbidden_plugin_import(
    *,
    module_name: str,
    path: Path,
    violations: list[str],
) -> None:
    if not any(
        module_name == forbidden or module_name.startswith(f"{forbidden}.")
        for forbidden in _FORBIDDEN_PLUGIN_IMPORTS
    ):
        return
    violations.append(f"{path.relative_to(_REPO_ROOT)} imports {module_name}")


def _decorator_name(decorator: ast.expr) -> str:
    if isinstance(decorator, ast.Name):
        return decorator.id
    if isinstance(decorator, ast.Call):
        return _decorator_name(decorator.func)
    if isinstance(decorator, ast.Attribute):
        return decorator.attr
    return ""


def _call_name(expr: ast.expr) -> str:
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return expr.attr
    return ""


def _contains_source_key_literal(expr: ast.expr, *, migrated_keys: set[str]) -> bool:
    for node in ast.walk(expr):
        if isinstance(node, ast.Constant) and node.value in migrated_keys:
            return True
    return False


def _pattern_contains_source_key_literal(
    pattern: ast.pattern,
    *,
    migrated_keys: set[str],
) -> bool:
    for node in ast.walk(pattern):
        if (
            isinstance(node, ast.MatchValue)
            and isinstance(node.value, ast.Constant)
            and node.value.value in migrated_keys
        ):
            return True
    return False


def _name_for_expr(expr: ast.expr) -> str:
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return f"{_name_for_expr(expr.value)}.{expr.attr}"
    return ""


def _imported_modules(tree: ast.AST) -> tuple[str, ...]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
    return tuple(modules)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
