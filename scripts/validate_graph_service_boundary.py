#!/usr/bin/env python3
"""Validate that graph internals stay behind the standalone service boundary."""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
TESTS_ROOT = REPO_ROOT / "tests"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
GRAPH_SERVICE_ROOT = REPO_ROOT / "services" / "artana_evidence_db"
GRAPH_SERVICE_DOCKERFILE = GRAPH_SERVICE_ROOT / "Dockerfile"
_SRC_GRAPH_PACKAGE = "src" + ".graph"

FORBIDDEN_IMPORT_PREFIXES = (
    "src.application.services.kernel",
    "src.infrastructure.repositories.kernel",
    "src.models.database.kernel",
)
FORBIDDEN_SERVICE_IMPORT_PREFIX = "services.artana_evidence_db"
FORBIDDEN_GRAPH_SERVICE_AI_IMPORT_PREFIXES = (
    "artana",
    "openai",
    "src.infrastructure.embeddings",
    "src.infrastructure.llm",
    "src.application.services.kernel.hybrid_graph_errors",
    "src.application.services.kernel.kernel_entity_similarity_service",
    "src.application.services.kernel.kernel_relation_suggestion_service",
)
FORBIDDEN_GRAPH_SERVICE_SHARED_IMPORT_PREFIXES = (
    "src.infrastructure.platform_graph",
    "src.application.services.kernel",
    "src.database.graph_schema",
    "src.domain.entities.kernel",
    "src.domain.entities.kernel.spaces",
    "src.domain.repositories.kernel",
    "src.domain.services.domain_context_resolver",
    "src.domain.entities.research_space_membership",
    "src.domain.entities.user",
    "src.domain.ports",
    "src.domain.value_objects.relation_types",
    "src.infrastructure.graph_governance",
    "src.infrastructure.ingestion.normalization.transform_runtime",
    "src.infrastructure.security.phi_encryption",
    "src.application.services._source_workflow_monitor_paper_links",
    "src.infrastructure.repositories.kernel",
    "src.database.url_resolver",
    "src.application.services.claim_first_metrics",
    "src.domain.ports.space_access_port",
    "src.domain.ports.space_registry_port",
    "src.infrastructure.security.jwt_provider",
    "src.application.services.kernel._kernel_claim_projection_readiness_support",
    "src.application.services.kernel._kernel_reasoning_path_support",
    "src.application.services.kernel.kernel_entity_errors",
    "src.models.database",
    "src.models.database.kernel.operation_runs",
    "src.models.database.source_document",
    _SRC_GRAPH_PACKAGE + ".",
    "src.type_definitions.graph_api_schemas",
    "src.type_definitions.dictionary",
    "src.type_definitions.common",
    "src.type_definitions.graph_service_contracts",
)
FORBIDDEN_GRAPH_TEST_AND_SCRIPT_IMPORT_PREFIXES = (
    "src.application.services.kernel",
    "src.domain.entities.kernel",
    "src.domain.repositories.kernel",
    "src.infrastructure.repositories.kernel",
    "src.infrastructure.graph_governance",
    "src.type_definitions.graph_api_schemas",
    "src.type_definitions.graph_service_contracts",
    _SRC_GRAPH_PACKAGE + ".",
)
FORBIDDEN_GRAPH_SERVICE_DOCKERFILE_SNIPPETS = (
    "COPY services ./services",
    "COPY src ./src",
    "COPY pyproject.toml",
    "COPY artana.toml",
    "pip install .",
    "pip install -e .",
)

ALLOWED_PREFIXES = (
    "services/artana_evidence_db/",
    "src/application/services/kernel/",
    "src/database/graph_schema.py",
    "src/infrastructure/graph_governance/",
    "src/infrastructure/queries/graph_security_queries.py",
    "src/infrastructure/repositories/graph_observability_repository.py",
    "src/infrastructure/repositories/kernel/",
    "src/models/database/kernel/",
)

LEGACY_ALLOWLIST = frozenset()


@dataclass(frozen=True)
class BoundaryViolation:
    file_path: str
    line_number: int
    imported_module: str


def _is_type_checking_guard(test_node: ast.expr) -> bool:
    return (isinstance(test_node, ast.Name) and test_node.id == "TYPE_CHECKING") or (
        isinstance(test_node, ast.Attribute)
        and isinstance(test_node.value, ast.Name)
        and test_node.value.id == "typing"
        and test_node.attr == "TYPE_CHECKING"
    )


def _build_parent_lookup(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parent_by_child: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_by_child[child] = parent
    return parent_by_child


def _is_type_checking_import(
    *,
    node: ast.AST,
    parent_by_child: dict[ast.AST, ast.AST],
) -> bool:
    current = parent_by_child.get(node)
    while current is not None:
        if isinstance(current, ast.If) and _is_type_checking_guard(current.test):
            return True
        current = parent_by_child.get(current)
    return False


def _extract_import_modules(node: ast.AST) -> list[str]:
    if isinstance(node, ast.ImportFrom):
        if node.module is None:
            return []
        return [node.module]
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    return []


def _extract_dynamic_import_module(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call) or not node.args:
        return None

    func = node.func
    if isinstance(func, ast.Name):
        is_import_module = func.id == "import_module"
    elif isinstance(func, ast.Attribute):
        is_import_module = (
            isinstance(func.value, ast.Name)
            and func.value.id == "importlib"
            and func.attr == "import_module"
        )
    else:
        is_import_module = False

    if not is_import_module:
        return None

    module_arg = node.args[0]
    if isinstance(module_arg, ast.Constant) and isinstance(module_arg.value, str):
        return module_arg.value
    return None


def _module_matches_forbidden_prefixes(
    module_name: str,
    forbidden_import_prefixes: tuple[str, ...],
) -> bool:
    for prefix in forbidden_import_prefixes:
        if module_name == prefix or module_name.startswith(f"{prefix}."):
            return True
    return False


def _is_allowed_file(relative_path: str) -> bool:
    return relative_path in LEGACY_ALLOWLIST or relative_path.startswith(
        ALLOWED_PREFIXES,
    )


def _scan_tree_for_violations(
    *,
    root: Path,
    is_allowed_file: Callable[[str], bool],
    forbidden_import_prefixes: tuple[str, ...],
) -> list[BoundaryViolation]:
    violations: list[BoundaryViolation] = []
    for file_path in root.rglob("*.py"):
        relative_path = str(file_path.relative_to(REPO_ROOT))
        if is_allowed_file(relative_path):
            continue

        try:
            tree = ast.parse(
                file_path.read_text(encoding="utf-8"),
                filename=str(file_path),
            )
        except SyntaxError:
            continue

        parent_by_child = _build_parent_lookup(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Import | ast.ImportFrom):
                continue
            if _is_type_checking_import(node=node, parent_by_child=parent_by_child):
                continue
            violations.extend(
                BoundaryViolation(
                    file_path=relative_path,
                    line_number=getattr(node, "lineno", 0),
                    imported_module=module_name,
                )
                for module_name in _extract_import_modules(node)
                if _module_matches_forbidden_prefixes(
                    module_name,
                    forbidden_import_prefixes,
                )
            )
    return violations


def _find_violations() -> list[BoundaryViolation]:
    violations = _scan_tree_for_violations(
        root=SRC_ROOT,
        is_allowed_file=_is_allowed_file,
        forbidden_import_prefixes=FORBIDDEN_IMPORT_PREFIXES,
    )
    violations.extend(
        _scan_tree_for_violations(
            root=SRC_ROOT,
            is_allowed_file=lambda _: False,
            forbidden_import_prefixes=(FORBIDDEN_SERVICE_IMPORT_PREFIX,),
        ),
    )
    violations.extend(
        _scan_tree_for_violations(
            root=GRAPH_SERVICE_ROOT,
            is_allowed_file=lambda _: False,
            forbidden_import_prefixes=FORBIDDEN_GRAPH_SERVICE_AI_IMPORT_PREFIXES,
        ),
    )
    violations.extend(
        _scan_tree_for_violations(
            root=GRAPH_SERVICE_ROOT,
            is_allowed_file=lambda _: False,
            forbidden_import_prefixes=FORBIDDEN_GRAPH_SERVICE_SHARED_IMPORT_PREFIXES,
        ),
    )
    violations.extend(
        _scan_tree_for_dynamic_import_violations(
            root=GRAPH_SERVICE_ROOT,
            is_allowed_file=lambda _: False,
            forbidden_import_prefixes=FORBIDDEN_GRAPH_SERVICE_SHARED_IMPORT_PREFIXES,
        ),
    )
    violations.extend(
        _scan_tree_for_dynamic_import_violations(
            root=GRAPH_SERVICE_ROOT,
            is_allowed_file=lambda _: False,
            forbidden_import_prefixes=FORBIDDEN_GRAPH_SERVICE_AI_IMPORT_PREFIXES,
        ),
    )
    violations.extend(
        _scan_tree_for_violations(
            root=TESTS_ROOT,
            is_allowed_file=lambda _: False,
            forbidden_import_prefixes=FORBIDDEN_GRAPH_TEST_AND_SCRIPT_IMPORT_PREFIXES,
        ),
    )
    violations.extend(
        _scan_tree_for_violations(
            root=SCRIPTS_ROOT,
            is_allowed_file=lambda relative_path: relative_path
            == "scripts/validate_graph_service_boundary.py",
            forbidden_import_prefixes=FORBIDDEN_GRAPH_TEST_AND_SCRIPT_IMPORT_PREFIXES,
        ),
    )
    violations.extend(_find_dockerfile_violations())
    return sorted(
        violations,
        key=lambda violation: (
            violation.file_path,
            violation.line_number,
            violation.imported_module,
        ),
    )


def _find_dockerfile_violations() -> list[BoundaryViolation]:
    if not GRAPH_SERVICE_DOCKERFILE.exists():
        return []

    violations: list[BoundaryViolation] = []
    for line_number, line in enumerate(
        GRAPH_SERVICE_DOCKERFILE.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        for snippet in FORBIDDEN_GRAPH_SERVICE_DOCKERFILE_SNIPPETS:
            if snippet in line:
                violations.extend(
                    [
                        BoundaryViolation(
                            file_path=str(
                                GRAPH_SERVICE_DOCKERFILE.relative_to(REPO_ROOT),
                            ),
                            line_number=line_number,
                            imported_module=snippet,
                        ),
                    ],
                )
    return violations


def _scan_tree_for_dynamic_import_violations(
    *,
    root: Path,
    is_allowed_file: Callable[[str], bool],
    forbidden_import_prefixes: tuple[str, ...],
) -> list[BoundaryViolation]:
    violations: list[BoundaryViolation] = []
    for file_path in root.rglob("*.py"):
        relative_path = str(file_path.relative_to(REPO_ROOT))
        if is_allowed_file(relative_path):
            continue

        try:
            tree = ast.parse(
                file_path.read_text(encoding="utf-8"),
                filename=str(file_path),
            )
        except SyntaxError:
            continue

        parent_by_child = _build_parent_lookup(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _is_type_checking_import(node=node, parent_by_child=parent_by_child):
                continue

            imported_module = _extract_dynamic_import_module(node)
            if imported_module is None:
                continue
            if not _module_matches_forbidden_prefixes(
                imported_module,
                forbidden_import_prefixes,
            ):
                continue

            violations.append(
                BoundaryViolation(
                    file_path=relative_path,
                    line_number=getattr(node, "lineno", 0),
                    imported_module=imported_module,
                ),
            )
    return violations


def main() -> int:
    violations = _find_violations()
    if not violations:
        print("graph_boundary: ok")
        return 0

    print("graph_boundary: error")
    print("Direct graph-internal imports are only allowed in the standalone service.")
    print("The standalone graph service also cannot import Artana/OpenAI/LLM")
    print("runtime modules after the harness extraction boundary.")
    print("Graph-service container packaging must stay on service-local")
    print("requirements instead of installing the shared root package.")
    for violation in violations:
        print(
            f"{violation.file_path}:{violation.line_number}: error: "
            f"graph_boundary: imports {violation.imported_module}",
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
