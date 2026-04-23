#!/usr/bin/env python3
"""Validate artana-evidence-api packaging and service-boundary invariants."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REMOVED_MONOREPO_SRC_ROOT = REPO_ROOT / "src"
HARNESS_ROOT = REPO_ROOT / "services" / "artana_evidence_api"
HARNESS_DOCKERFILE = HARNESS_ROOT / "Dockerfile"
HARNESS_TEST_PATHS = (
    HARNESS_ROOT / "tests" / "unit",
    HARNESS_ROOT / "tests" / "integration",
    REPO_ROOT / "tests" / "e2e" / "artana_evidence_api",
    HARNESS_ROOT / "tests" / "support.py",
)
HARNESS_SCRIPT_PATHS = (
    REPO_ROOT / "scripts" / "export_artana_evidence_api_openapi.py",
)
_SRC_GRAPH_PACKAGE = "src" + ".graph"
_RAW_MUTATION_TRANSPORT_IMPORT_ALLOWED_FILES = {
    HARNESS_ROOT / "graph_client.py",
    HARNESS_ROOT / "graph_transport.py",
    HARNESS_ROOT / "graph_integration" / "context.py",
    HARNESS_ROOT / "graph_integration" / "submission.py",
    HARNESS_ROOT / "space_lifecycle_sync.py",
}
_RAW_MUTATION_TRANSPORT_IMPLEMENTATION_FILE = HARNESS_ROOT / "graph_transport.py"
_IDENTITY_MODEL_IMPORT_PREFIXES = (
    "artana_evidence_api.models.api_key",
    "artana_evidence_api.models.research_space",
    "artana_evidence_api.models.user",
)
_IDENTITY_MODEL_IMPORT_ALLOWED_FILES = {
    HARNESS_ROOT / "api_keys.py",
    HARNESS_ROOT / "app.py",
    HARNESS_ROOT / "dependencies.py",
    HARNESS_ROOT / "identity" / "local_gateway.py",
    HARNESS_ROOT / "models" / "__init__.py",
    HARNESS_ROOT / "research_space_store.py",
    HARNESS_ROOT / "space_sync_types.py",
    HARNESS_ROOT / "sqlalchemy_stores.py",
}

FORBIDDEN_IMPORT_PREFIXES = (
    "artana_evidence_db.",
    "src.infrastructure.platform_graph.artana_evidence_api",
    "src.infrastructure.platform_graph.graph_service",
    "src.domain.entities.user",
    "src.routes.auth",
    "src.database.session",
    "src.models.database",
    "src.domain.agents.contracts.base",
    "src.domain.agents.contracts.graph_connection",
    "src.domain.agents.contracts.graph_search",
    "src.domain.agents.models",
    "src.infrastructure.llm.adapters._artana_step_helpers",
    "src.infrastructure.llm.adapters._openai_json_schema_model_port",
    "src.infrastructure.llm.config",
    "src.infrastructure.llm.state.shared_postgres_store",
    "src.type_definitions.common",
    "src.type_definitions.graph_service_contracts",
    "src.infrastructure.graph_service",
    _SRC_GRAPH_PACKAGE + ".",
    "src.infrastructure.llm.prompts.graph_search",
    "src.infrastructure.llm.prompts.graph_connection",
    "src.infrastructure.dependency_injection.dependencies",
)
FORBIDDEN_TEST_AND_SCRIPT_IMPORT_PREFIXES = (
    "src.infrastructure.platform_graph.artana_evidence_api",
    "src.infrastructure.platform_graph.graph_service",
    "src.domain.entities.user",
    "src.routes.auth",
    "src.database.session",
    "src.models.database",
    "src.domain.agents.contracts.base",
    "src.domain.agents.contracts.graph_connection",
    "src.domain.agents.contracts.graph_search",
    "src.domain.agents.models",
    "src.infrastructure.llm.adapters._artana_step_helpers",
    "src.infrastructure.llm.adapters._openai_json_schema_model_port",
    "src.infrastructure.llm.config",
    "src.infrastructure.llm.state.shared_postgres_store",
    "src.type_definitions.common",
    "src.type_definitions.graph_service_contracts",
    "src.infrastructure.graph_service",
    _SRC_GRAPH_PACKAGE + ".",
    "src.infrastructure.llm.prompts.graph_search",
    "src.infrastructure.llm.prompts.graph_connection",
    "src.infrastructure.dependency_injection.dependencies",
)
FORBIDDEN_DOCKERFILE_SNIPPETS = (
    "COPY services ./services",
    "COPY src ./src",
    "COPY artana.toml ./artana.toml",
    'pip install ".[dev]"',
    "COPY pyproject.toml ./pyproject.toml",
)
FORBIDDEN_GRAPH_OFFICIAL_MUTATION_PATHS = (
    "/v1/dictionary/domain-contexts",
    "/v1/dictionary/entity-types",
    "/v1/dictionary/relation-types",
    "/v1/dictionary/relation-constraints",
    "/v1/dictionary/relation-synonyms",
    "/v1/dictionary/variables",
    "/v1/dictionary/value-sets",
)
_HARNESS_PRODUCTION_EXCLUDED_DIRS = frozenset(
    {
        "__pycache__",
        "alembic",
        "tests",
    },
)
_ROUTER_IMPORT_ALLOWED_FILES = {
    HARNESS_ROOT / "app.py",
}


@dataclass(frozen=True)
class BoundaryViolation:
    file_path: str
    line_number: int
    imported_module: str


def _is_harness_production_file(file_path: Path) -> bool:
    relative_parts = file_path.relative_to(HARNESS_ROOT).parts
    return not any(part in _HARNESS_PRODUCTION_EXCLUDED_DIRS for part in relative_parts)


def _read_imports(file_path: Path) -> list[BoundaryViolation]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    violations: list[BoundaryViolation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            module_names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module_names = [node.module] if node.module is not None else []
        else:
            continue
        violations.extend(
            [
                BoundaryViolation(
                    file_path=str(file_path.relative_to(REPO_ROOT)),
                    line_number=getattr(node, "lineno", 0),
                    imported_module=module_name,
                )
                for module_name in module_names
                if module_name.startswith(FORBIDDEN_IMPORT_PREFIXES)
            ],
        )
    return violations


def _path_literal(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr) and node.values:
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                parts.append("{}")
        return "".join(parts)
    return None


def _imports_raw_mutation_transport(node: ast.AST) -> bool:
    if isinstance(node, ast.ImportFrom):
        return any(alias.name == "GraphRawMutationTransport" for alias in node.names)
    if isinstance(node, ast.Import):
        return any(
            alias.name.endswith(".GraphRawMutationTransport") for alias in node.names
        )
    return False


def _raw_mutation_import_violations(file_path: Path) -> list[BoundaryViolation]:
    if not _is_harness_production_file(file_path):
        return []
    if file_path in _RAW_MUTATION_TRANSPORT_IMPORT_ALLOWED_FILES:
        return []
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    violations: list[BoundaryViolation] = []
    for node in ast.walk(tree):
        if _imports_raw_mutation_transport(node):
            violations.append(
                BoundaryViolation(
                    file_path=str(file_path.relative_to(REPO_ROOT)),
                    line_number=getattr(node, "lineno", 0),
                    imported_module="GraphRawMutationTransport import outside allowlist",
                ),
            )
    return violations


def _identity_model_import_violations(file_path: Path) -> list[BoundaryViolation]:
    if not _is_harness_production_file(file_path):
        return []
    if file_path in _IDENTITY_MODEL_IMPORT_ALLOWED_FILES:
        return []
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    violations: list[BoundaryViolation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            module_names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module_names = [node.module] if node.module is not None else []
        else:
            continue
        violations.extend(
            [
                BoundaryViolation(
                    file_path=str(file_path.relative_to(REPO_ROOT)),
                    line_number=getattr(node, "lineno", 0),
                    imported_module=(
                        "identity model import outside identity boundary: "
                        f"{module_name}"
                    ),
                )
                for module_name in module_names
                if module_name.startswith(_IDENTITY_MODEL_IMPORT_PREFIXES)
            ],
        )
    return violations


def _runtime_router_import_violations(file_path: Path) -> list[BoundaryViolation]:
    if not _is_harness_production_file(file_path):
        return []
    if file_path in _ROUTER_IMPORT_ALLOWED_FILES:
        return []
    if "routers" in file_path.relative_to(HARNESS_ROOT).parts:
        return []
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    violations: list[BoundaryViolation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            module_names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module_names = [node.module] if node.module is not None else []
        else:
            continue
        violations.extend(
            [
                BoundaryViolation(
                    file_path=str(file_path.relative_to(REPO_ROOT)),
                    line_number=getattr(node, "lineno", 0),
                    imported_module=(
                        "production runtime import from router module: "
                        f"{module_name}"
                    ),
                )
                for module_name in module_names
                if module_name == "artana_evidence_api.routers"
                or module_name.startswith("artana_evidence_api.routers.")
            ],
        )
    return violations


def _call_method_and_path(node: ast.Call) -> tuple[str | None, str | None]:
    if isinstance(node.func, ast.Attribute) and node.func.attr in {
        "post",
        "put",
        "patch",
        "delete",
    }:
        return node.func.attr.upper(), _path_literal(
            node.args[0] if node.args else None
        )

    if not (
        isinstance(node.func, ast.Attribute)
        and node.func.attr in {"_request", "_request_model", "request"}
    ):
        return None, None
    method_node = node.args[0] if node.args else None
    path_node = node.args[1] if len(node.args) > 1 else None
    method = (
        method_node.value.upper()
        if isinstance(method_node, ast.Constant) and isinstance(method_node.value, str)
        else None
    )
    return method, _path_literal(path_node)


def _read_forbidden_graph_mutation_calls(file_path: Path) -> list[BoundaryViolation]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    violations: list[BoundaryViolation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        method, path = _call_method_and_path(node)
        if method not in {"POST", "PUT", "PATCH", "DELETE"} or path is None:
            continue
        if path.startswith(FORBIDDEN_GRAPH_OFFICIAL_MUTATION_PATHS):
            violations.append(
                BoundaryViolation(
                    file_path=str(file_path.relative_to(REPO_ROOT)),
                    line_number=getattr(node, "lineno", 0),
                    imported_module=f"official dictionary mutation call {method} {path}",
                ),
            )
            continue
        if (
            file_path != _RAW_MUTATION_TRANSPORT_IMPLEMENTATION_FILE
            and _is_direct_raw_graph_mutation(method=method, path=path)
        ):
            violations.append(
                BoundaryViolation(
                    file_path=str(file_path.relative_to(REPO_ROOT)),
                    line_number=getattr(node, "lineno", 0),
                    imported_module=f"direct graph mutation wrapper {method} {path}",
                ),
            )
    return violations


def _is_direct_raw_graph_mutation(*, method: str, path: str) -> bool:
    if not path.startswith("/v1/spaces/"):
        return False
    return (
        (method == "POST" and path.endswith("/entities"))
        or (method == "PUT" and "/entities/" in path)
        or (method == "POST" and path.endswith("/entities/batch"))
        or (method == "POST" and path.endswith("/claims"))
        or (method == "POST" and path.endswith("/relations"))
    )


def _dockerfile_violations() -> list[BoundaryViolation]:
    violations: list[BoundaryViolation] = []
    for line_number, line in enumerate(
        HARNESS_DOCKERFILE.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        violations.extend(
            [
                BoundaryViolation(
                    file_path=str(HARNESS_DOCKERFILE.relative_to(REPO_ROOT)),
                    line_number=line_number,
                    imported_module=snippet,
                )
                for snippet in FORBIDDEN_DOCKERFILE_SNIPPETS
                if snippet in line
            ],
        )
    return violations


def _find_violations() -> list[BoundaryViolation]:
    violations: list[BoundaryViolation] = []
    if REMOVED_MONOREPO_SRC_ROOT.exists():
        violations.append(
            BoundaryViolation(
                file_path="src",
                line_number=0,
                imported_module="removed monorepo src directory is present",
            ),
        )
    for file_path in HARNESS_ROOT.rglob("*.py"):
        violations.extend(_read_imports(file_path))
        if _is_harness_production_file(file_path):
            violations.extend(_identity_model_import_violations(file_path))
            violations.extend(_runtime_router_import_violations(file_path))
            violations.extend(_raw_mutation_import_violations(file_path))
            violations.extend(_read_forbidden_graph_mutation_calls(file_path))
    for path in HARNESS_TEST_PATHS:
        violations.extend(
            _read_imports_with_prefixes(
                path,
                FORBIDDEN_TEST_AND_SCRIPT_IMPORT_PREFIXES,
            ),
        )
    for path in HARNESS_SCRIPT_PATHS:
        violations.extend(
            _read_imports_with_prefixes(
                path,
                FORBIDDEN_TEST_AND_SCRIPT_IMPORT_PREFIXES,
            ),
        )
    violations.extend(_dockerfile_violations())
    return sorted(
        violations,
        key=lambda violation: (
            violation.file_path,
            violation.line_number,
            violation.imported_module,
        ),
    )


def _read_imports_with_prefixes(
    root: Path,
    forbidden_prefixes: tuple[str, ...],
    *,
    excluded_files: set[Path] | None = None,
) -> list[BoundaryViolation]:
    violations: list[BoundaryViolation] = []
    excluded = excluded_files or set()
    file_paths = [root] if root.is_file() else list(root.rglob("*.py"))
    for file_path in file_paths:
        if file_path in excluded:
            continue
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                module_names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                module_names = [node.module] if node.module is not None else []
            else:
                continue
            violations.extend(
                [
                    BoundaryViolation(
                        file_path=str(file_path.relative_to(REPO_ROOT)),
                        line_number=getattr(node, "lineno", 0),
                        imported_module=module_name,
                    )
                    for module_name in module_names
                    if module_name.startswith(forbidden_prefixes)
                ],
            )
    return violations


def main() -> int:
    violations = _find_violations()
    if not violations:
        print("artana_evidence_api_boundary: ok")
        return 0

    print("artana_evidence_api_boundary: error")
    print("Artana Evidence API packaging must stay scoped to the standalone service.")
    for violation in violations:
        print(
            f"{violation.file_path}:{violation.line_number}: error: "
            f"artana_evidence_api_boundary: imports {violation.imported_module}",
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
