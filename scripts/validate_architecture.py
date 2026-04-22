#!/usr/bin/env python3
"""
Architectural Compliance Validator for Artana Resource Library.

Validates codebase against architectural standards defined in:
- docs/EngineeringArchitecture.md
- docs/type_examples.md
- docs/frontend/EngenieeringArchitectureNext.md
- AGENTS.md
- architecture_overrides.json (technical debt tracking)

This script checks for:
1. Type safety violations (Any, cast usage)
2. JSON type usage (dict[str, Any] -> JSONObject/JSONValue)
3. Update type usage (plain dict -> TypedDict classes)
4. Test fixture usage (plain dicts -> typed fixtures)
5. API response types (routes -> ApiResponse/PaginatedResponse)
6. Clean Architecture layer violations
7. Single Responsibility Principle violations
8. Monolithic code patterns
9. Import dependency violations
"""

import ast
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logger = logging.getLogger(__name__)
_SRC_GRAPH_PACKAGE = "src" + ".graph"

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.type_definitions.common import JSONValue

# Allowed exceptions for type checking
ALLOWED_ANY_USAGE = {
    "src/type_definitions/json_utils.py",  # Explicit override in pyproject.toml
    "src/application/packaging/licenses/manager.py",  # License compatibility checking
    "src/application/packaging/licenses/manifest.py",  # YAML parsing
    # Artana runtime interop - documented exceptions for generic type surfaces
    "src/infrastructure/llm/adapters/query_agent_adapter.py",
    "src/infrastructure/llm/adapters/query_agent_adapter_helpers.py",
}

# Clean Architecture layer definitions
LAYER_BOUNDARIES = {
    "domain": {
        "path": "src/domain",
        "forbidden_imports": [
            "src.infrastructure",
            "src.routes",
            "src.models",  # Domain owns business concepts; models are outer-layer schemas/ORM.
            "src.models.database",  # Domain should use entities, not DB models
            _SRC_GRAPH_PACKAGE,
        ],
        "allowed_imports": [
            "src.domain",
            "src.type_definitions",
            "typing",
            "collections.abc",
            "datetime",
            "uuid",
            "pydantic",
        ],
    },
    "application": {
        "path": "src/application",
        "forbidden_imports": [
            "src.routes",  # Application shouldn't know about routes
            _SRC_GRAPH_PACKAGE,
        ],
        "allowed_imports": [
            "src.domain",
            "src.application",
            "src.type_definitions",
            "src.infrastructure.repositories",  # Can use repository implementations
        ],
    },
    "infrastructure": {
        "path": "src/infrastructure",
        "forbidden_imports": [
            "src.routes",  # Infrastructure shouldn't know about routes
            _SRC_GRAPH_PACKAGE,
        ],
    },
}

# File size thresholds (lines of code)
# Note: Some complex infrastructure files (ingestors, transformers) may legitimately
# be larger due to their nature. However, files >1200 lines should be split.
MAX_FILE_SIZE = 1200  # Large files may violate SRP
WARNING_FILE_SIZE = 500  # Files approaching limit

# Complexity thresholds
MAX_FUNCTION_COMPLEXITY = 50  # Cyclomatic complexity
MAX_CLASS_METHODS = 30  # Methods per class

# Single Responsibility Principle thresholds
MAX_IMPORTS_PER_FILE = 21  # Too many imports = too many responsibilities
MAX_FUNCTION_PARAMETERS = 7  # Functions with many params often do too much
WARNING_IMPORTS_PER_FILE = (
    17  # Files approaching limit (orchestration services often need 15-17)
)

ARCHITECTURE_OVERRIDES_FILE = "architecture_overrides.json"
FASTAPI_ROUTE_DECORATORS = frozenset(
    {"get", "post", "put", "patch", "delete", "options", "head"},
)
ASYNC_ROUTE_NO_AWAIT_ALLOWLIST: frozenset[str] = frozenset()
ASYNC_HOT_PATH_BANNED_CALLS: dict[str, frozenset[str]] = {
    "src/middleware/audit_logging.py": frozenset(
        {"SessionLocal", "set_session_rls_context", "record_action"},
    ),
    "src/routes/research_spaces/workflow_monitor_stream_routes.py": frozenset(
        {
            "verify_space_membership",
            "resolve_space_source_ids",
            "get_source_workflow_monitor",
            "list_workflow_events",
        },
    ),
}
LLM_PROVIDER_BOUNDARY_ROOT = "src/infrastructure/llm/adapters/"
LLM_PROVIDER_BOUNDARY_ALLOWLIST: frozenset[str] = frozenset(
    {
        "src/infrastructure/llm/adapters/_artana_litellm_model_port.py",
        "src/infrastructure/llm/adapters/_graph_search_openai_model_port.py",
        "src/infrastructure/llm/adapters/_openai_json_schema_model_port.py",
        "src/infrastructure/llm/adapters/_openai_structured_output_helpers.py",
    },
)
FORBIDDEN_LLM_PROVIDER_MODULES: frozenset[str] = frozenset(
    {
        "httpx",
        "litellm",
        "openai",
    },
)
ALLOWED_LLM_PROVIDER_IMPORTS: dict[str, frozenset[str]] = {
    "src.infrastructure.llm.adapters._openai_json_schema_model_port": frozenset(
        {"has_configured_openai_api_key"},
    ),
}
FORBIDDEN_LLM_PROVIDER_SYMBOL_IMPORTS: dict[str, frozenset[str]] = {
    "artana.ports.model": frozenset({"LiteLLMAdapter"}),
    "src.infrastructure.llm.adapters._openai_json_schema_model_port": frozenset(
        {"OpenAIJSONSchemaModelPort"},
    ),
}


@dataclass
class Violation:
    """Represents an architectural violation."""

    file_path: str
    line_number: int
    violation_type: str
    message: str
    severity: str  # "error" or "warning"


@dataclass
class ValidationResult:
    """Results of architectural validation."""

    violations: list[Violation] = field(default_factory=list)
    files_checked: int = 0
    total_lines: int = 0

    @property
    def error_count(self) -> int:
        """Count of error-level violations."""
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        """Count of warning-level violations."""
        return sum(1 for v in self.violations if v.severity == "warning")

    def is_valid(self) -> bool:
        """Check if validation passed (no errors)."""
        return self.error_count == 0


@dataclass(frozen=True)
class FileSizeOverride:
    """Represents a documented file size exception."""

    path: str
    max_lines: int
    reason: str
    expires_on: str | None = None


@dataclass(frozen=True)
class ClassSizeOverride:
    """Represents a documented class size exception."""

    path: str
    class_name: str
    max_methods: int
    reason: str
    expires_on: str | None = None


@dataclass(frozen=True)
class ImportCountOverride:
    """Represents a documented import-count exception."""

    path: str
    max_imports: int
    reason: str
    expires_on: str | None = None


@dataclass
class ArchitectureOverrides:
    """Overrides for transitional technical debt."""

    file_size: dict[str, FileSizeOverride] = field(default_factory=dict)
    class_size: dict[tuple[str, str], ClassSizeOverride] = field(default_factory=dict)
    import_count: dict[str, ImportCountOverride] = field(default_factory=dict)

    @classmethod
    def load(cls, root_path: Path) -> "ArchitectureOverrides":
        """Load overrides from configuration file if present."""
        overrides_path = root_path / ARCHITECTURE_OVERRIDES_FILE
        if not overrides_path.exists():
            return cls()

        try:
            raw_data: JSONValue = json.loads(overrides_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:  # pragma: no cover - configuration error
            error_message = f"Invalid JSON in {ARCHITECTURE_OVERRIDES_FILE}: {exc.msg}"
            raise ValueError(error_message) from exc

        if not isinstance(raw_data, dict):
            message = f"{ARCHITECTURE_OVERRIDES_FILE} must contain a JSON object at the top level."
            raise TypeError(message)

        file_overrides = cls._parse_file_size_overrides(raw_data.get("file_size"))
        class_overrides = cls._parse_class_size_overrides(raw_data.get("class_size"))
        import_count_overrides = cls._parse_import_count_overrides(
            raw_data.get("import_count"),
        )

        return cls(file_overrides, class_overrides, import_count_overrides)

    @staticmethod
    def _parse_file_size_overrides(
        value: object | None,
    ) -> dict[str, FileSizeOverride]:
        overrides: dict[str, FileSizeOverride] = {}
        if not isinstance(value, list):
            return overrides

        for entry in value:
            if not isinstance(entry, dict):
                continue

            entry_dict: dict[str, object] = entry
            path_value = entry_dict.get("path")
            max_lines_value = entry_dict.get("max_lines")
            reason_value = entry_dict.get("reason")
            expires_value = entry_dict.get("expires_on")

            if (
                isinstance(path_value, str)
                and isinstance(max_lines_value, int)
                and isinstance(reason_value, str)
            ):
                expires = expires_value if isinstance(expires_value, str) else None
                overrides[path_value] = FileSizeOverride(
                    path=path_value,
                    max_lines=max_lines_value,
                    reason=reason_value,
                    expires_on=expires,
                )

        return overrides

    @staticmethod
    def _parse_class_size_overrides(
        value: object | None,
    ) -> dict[tuple[str, str], ClassSizeOverride]:
        overrides: dict[tuple[str, str], ClassSizeOverride] = {}
        if not isinstance(value, list):
            return overrides

        for entry in value:
            if not isinstance(entry, dict):
                continue

            entry_dict: dict[str, object] = entry
            path_value = entry_dict.get("path")
            class_name = entry_dict.get("class_name")
            max_methods_value = entry_dict.get("max_methods")
            reason_value = entry_dict.get("reason")
            expires_value = entry_dict.get("expires_on")

            if (
                isinstance(path_value, str)
                and isinstance(class_name, str)
                and isinstance(max_methods_value, int)
                and isinstance(reason_value, str)
            ):
                expires = expires_value if isinstance(expires_value, str) else None
                key = (path_value, class_name)
                overrides[key] = ClassSizeOverride(
                    path=path_value,
                    class_name=class_name,
                    max_methods=max_methods_value,
                    reason=reason_value,
                    expires_on=expires,
                )

        return overrides

    @staticmethod
    def _parse_import_count_overrides(
        value: object | None,
    ) -> dict[str, ImportCountOverride]:
        overrides: dict[str, ImportCountOverride] = {}
        if not isinstance(value, list):
            return overrides

        for entry in value:
            if not isinstance(entry, dict):
                continue

            entry_dict: dict[str, object] = entry
            path_value = entry_dict.get("path")
            max_imports_value = entry_dict.get("max_imports")
            reason_value = entry_dict.get("reason")
            expires_value = entry_dict.get("expires_on")

            if (
                isinstance(path_value, str)
                and isinstance(max_imports_value, int)
                and isinstance(reason_value, str)
            ):
                expires = expires_value if isinstance(expires_value, str) else None
                overrides[path_value] = ImportCountOverride(
                    path=path_value,
                    max_imports=max_imports_value,
                    reason=reason_value,
                    expires_on=expires,
                )

        return overrides


def _ast_to_string(node: ast.AST) -> str:
    """Convert AST node to string representation."""
    if hasattr(ast, "unparse"):
        try:
            return ast.unparse(node)
        except Exception:  # pragma: no cover - fallback
            logger.debug(
                "AST unparse failed; falling back to manual conversion",
                exc_info=True,
            )

    # Fallback for Python < 3.9 or when unparse fails
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.Subscript):
        value_str = _ast_to_string(node.value)
        if hasattr(node, "slice"):
            if isinstance(node.slice, ast.Index):  # Python < 3.9
                slice_str = _ast_to_string(node.slice.value)
            else:
                slice_str = _ast_to_string(node.slice)
        else:
            slice_str = ""
        return f"{value_str}[{slice_str}]"
    if isinstance(node, ast.Attribute):
        return f"{_ast_to_string(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        func_str = _ast_to_string(node.func)
        return f"{func_str}(...)"
    # For complex nodes, return a simplified representation
    return str(type(node).__name__)


class ArchitectureValidator:
    """Validates codebase against architectural standards."""

    def __init__(self, root_path: Path) -> None:
        """Initialize validator with root path."""
        self.root_path = root_path
        self.result = ValidationResult()
        self.overrides = ArchitectureOverrides.load(root_path)

    def validate(self) -> ValidationResult:
        """Run all validation checks."""
        python_files = self._find_python_files()
        self.result.files_checked = len(python_files)

        for file_path in python_files:
            self._validate_file(file_path)

        return self.result

    def _find_python_files(self) -> list[Path]:
        """Find all Python files in src directory."""
        python_files: list[Path] = []
        src_path = self.root_path / "src"

        if not src_path.exists():
            return python_files

        for py_file in src_path.rglob("*.py"):
            # Skip __pycache__ but include test files for fixture validation
            if "__pycache__" in str(py_file):
                continue
            python_files.append(py_file)

        return python_files

    def _validate_file(self, file_path: Path) -> None:
        """Validate a single Python file."""
        try:
            content = file_path.read_text(encoding="utf-8")
            self.result.total_lines += len(content.splitlines())

            tree = ast.parse(content, filename=str(file_path))
            relative_path = str(file_path.relative_to(self.root_path))

            # Check file size
            self._check_file_size(relative_path, content)

            # Check for type safety violations
            self._check_type_safety(tree, relative_path, content)

            # Check for type_examples.md pattern compliance
            self._check_json_type_usage(tree, relative_path, content)
            self._check_update_type_usage(tree, relative_path, content)

            # Check test files for typed fixture usage
            if "test_" in relative_path or "/tests/" in relative_path:
                self._check_test_fixture_usage(tree, relative_path, content)

            # Check route files for API response types
            if "/routes/" in relative_path:
                self._check_api_response_types(tree, relative_path, content)
                self._check_route_async_usage(tree, relative_path)

            # Check for layer violations
            self._check_layer_violations(tree, relative_path)
            self._check_llm_provider_boundary(tree, relative_path)

            # Check for complexity violations
            self._check_complexity(tree, relative_path)

            # Check for SRP violations (import count, parameter count)
            self._check_import_count(tree, relative_path)
            self._check_function_parameters(tree, relative_path)
            self._check_async_hot_path_sync_calls(tree, relative_path)

        except SyntaxError as e:
            self.result.violations.append(
                Violation(
                    file_path=str(file_path.relative_to(self.root_path)),
                    line_number=e.lineno or 0,
                    violation_type="syntax_error",
                    message=f"Syntax error: {e.msg}",
                    severity="error",
                ),
            )
        except Exception as e:
            self.result.violations.append(
                Violation(
                    file_path=str(file_path.relative_to(self.root_path)),
                    line_number=0,
                    violation_type="validation_error",
                    message=f"Error validating file: {e}",
                    severity="warning",
                ),
            )

    def _check_file_size(self, file_path: str, content: str) -> None:
        """Check if file violates size thresholds."""
        lines = len(content.splitlines())
        if self._allows_file_size_override(file_path, lines):
            return

        if lines > MAX_FILE_SIZE:
            self.result.violations.append(
                Violation(
                    file_path=file_path,
                    line_number=0,
                    violation_type="file_size",
                    message=(
                        f"File exceeds maximum size ({lines} > {MAX_FILE_SIZE} lines). "
                        "May violate Single Responsibility Principle."
                    ),
                    severity="error",
                ),
            )
        elif lines > WARNING_FILE_SIZE:
            self.result.violations.append(
                Violation(
                    file_path=file_path,
                    line_number=0,
                    violation_type="file_size",
                    message=(
                        f"File is large ({lines} > {WARNING_FILE_SIZE} lines). "
                        "Consider splitting into smaller modules."
                    ),
                    severity="warning",
                ),
            )

    def _check_type_safety(
        self,
        _tree: ast.AST,
        file_path: str,
        content: str,
    ) -> None:
        """Check for type safety violations (Any, cast)."""
        # Check for Any usage
        for node in ast.walk(_tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "typing"
                and any(alias.name == "Any" for alias in node.names)
                and file_path not in ALLOWED_ANY_USAGE
            ):
                self.result.violations.append(
                    Violation(
                        file_path=file_path,
                        line_number=node.lineno,
                        violation_type="any_usage",
                        message=(
                            "Use of 'Any' type violates type safety policy. "
                            "Use proper types from src/type_definitions/ instead."
                        ),
                        severity="error",
                    ),
                )

            # Check for cast usage
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "cast"
            ):
                self.result.violations.append(
                    Violation(
                        file_path=file_path,
                        line_number=node.lineno,
                        violation_type="cast_usage",
                        message=(
                            "Use of 'cast' violates type safety policy. "
                            "Use proper type guards or fix the underlying type issue."
                        ),
                        severity="error",
                    ),
                )

        # Check for Any in type annotations (string annotations)
        lines = content.splitlines()
        for i, line in enumerate(lines, start=1):
            # Check for Any in type annotations
            if "Any" in line and "from typing import" not in line:
                # Skip comments and strings
                if "#" in line or '"' in line or "'" in line:
                    continue
                # Check if it's a type annotation
                if (
                    (":" in line or "->" in line)
                    and file_path not in ALLOWED_ANY_USAGE
                    and ("Any" in line.split(":")[-1] or "Any" in line.split("->")[-1])
                ):
                    self.result.violations.append(
                        Violation(
                            file_path=file_path,
                            line_number=i,
                            violation_type="any_usage",
                            message=(
                                "Use of 'Any' in type annotation violates type safety policy."
                            ),
                            severity="error",
                        ),
                    )

    def _check_layer_violations(
        self,
        tree: ast.AST,
        file_path: str,
    ) -> None:
        """Check for Clean Architecture layer violations."""
        # Determine which layer this file belongs to
        layer = None
        for layer_name, config in LAYER_BOUNDARIES.items():
            if file_path.startswith(config["path"]):
                layer = layer_name
                break

        if not layer:
            return  # Not in a defined layer

        layer_config = LAYER_BOUNDARIES[layer]

        def _matches_forbidden_prefix(module_name: str, forbidden_prefix: str) -> bool:
            """Return True if module_name is (or is within) forbidden_prefix."""
            if module_name == forbidden_prefix:
                return True
            return module_name.startswith(f"{forbidden_prefix}.")

        # Normalise forbidden prefixes so we catch both absolute imports (src.*)
        # and occasional relative/short imports (infrastructure.*).
        forbidden_prefixes: list[str] = []
        for forbidden in layer_config.get("forbidden_imports", []):
            forbidden_prefixes.append(forbidden)
            if forbidden.startswith("src."):
                forbidden_prefixes.append(forbidden.removeprefix("src."))

        # Check imports (both `from x import y` and `import x`).
        for node in ast.walk(tree):
            imported_modules: list[tuple[str, int]] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.append((node.module, node.lineno))
            elif isinstance(node, ast.Import):
                imported_modules.extend(
                    (alias.name, node.lineno) for alias in node.names
                )
            else:
                continue

            for module_name, lineno in imported_modules:
                for forbidden in forbidden_prefixes:
                    if _matches_forbidden_prefix(module_name, forbidden):
                        self.result.violations.append(
                            Violation(
                                file_path=file_path,
                                line_number=lineno,
                                violation_type="layer_violation",
                                message=(
                                    f"Layer violation: {layer} layer imports from "
                                    f"{module_name} (forbidden prefix: {forbidden}). "
                                    "This violates Clean Architecture dependency inversion "
                                    "principle."
                                ),
                                severity="error",
                            ),
                        )

    def _check_complexity(
        self,
        tree: ast.AST,
        file_path: str,
    ) -> None:
        """Check for complexity violations (SRP)."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Simple complexity check: count decision points
                complexity = self._calculate_complexity(node)
                if complexity > MAX_FUNCTION_COMPLEXITY:
                    self.result.violations.append(
                        Violation(
                            file_path=file_path,
                            line_number=node.lineno,
                            violation_type="complexity",
                            message=(
                                f"Function '{node.name}' has high complexity "
                                f"({complexity} > {MAX_FUNCTION_COMPLEXITY}). "
                                "May violate Single Responsibility Principle."
                            ),
                            severity="warning",
                        ),
                    )

            if isinstance(node, ast.ClassDef):
                # Count methods in class
                methods = [
                    n
                    for n in node.body
                    if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
                ]
                if len(
                    methods,
                ) > MAX_CLASS_METHODS and not self._allows_class_size_override(
                    file_path,
                    node.name,
                    len(methods),
                ):
                    self.result.violations.append(
                        Violation(
                            file_path=file_path,
                            line_number=node.lineno,
                            violation_type="class_size",
                            message=(
                                f"Class '{node.name}' has many methods "
                                f"({len(methods)} > {MAX_CLASS_METHODS}). "
                                "May violate Single Responsibility Principle."
                            ),
                            severity="warning",
                        ),
                    )

    def _check_llm_provider_boundary(self, tree: ast.AST, file_path: str) -> None:
        """Ensure LLM adapters route provider traffic through Artana-managed ports."""
        if not file_path.startswith(LLM_PROVIDER_BOUNDARY_ROOT):
            return
        if file_path in LLM_PROVIDER_BOUNDARY_ALLOWLIST:
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_root = alias.name.split(".", 1)[0]
                    if module_root in FORBIDDEN_LLM_PROVIDER_MODULES:
                        self.result.violations.append(
                            Violation(
                                file_path=file_path,
                                line_number=node.lineno,
                                violation_type="llm_provider_boundary",
                                message=(
                                    f"LLM/agent adapter imports provider module '{alias.name}' directly. "
                                    "Use Artana-kernel-managed model ports instead of direct provider clients."
                                ),
                                severity="error",
                            ),
                        )
                continue

            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue

            module_name = node.module
            module_root = module_name.split(".", 1)[0]
            if module_root in FORBIDDEN_LLM_PROVIDER_MODULES:
                self.result.violations.append(
                    Violation(
                        file_path=file_path,
                        line_number=node.lineno,
                        violation_type="llm_provider_boundary",
                        message=(
                            f"LLM/agent adapter imports from provider module '{module_name}'. "
                            "Use Artana-kernel-managed model ports instead of direct provider clients."
                        ),
                        severity="error",
                    ),
                )
                continue

            allowed_imports = ALLOWED_LLM_PROVIDER_IMPORTS.get(module_name)
            if allowed_imports is not None:
                illegal_names = sorted(
                    alias.name
                    for alias in node.names
                    if alias.name not in allowed_imports and alias.name != "*"
                )
                if illegal_names:
                    self.result.violations.append(
                        Violation(
                            file_path=file_path,
                            line_number=node.lineno,
                            violation_type="llm_provider_boundary",
                            message=(
                                f"LLM/agent adapter imports provider-boundary symbols {illegal_names} "
                                f"from '{module_name}'. Only {sorted(allowed_imports)} may be imported "
                                "outside the dedicated provider-boundary modules."
                            ),
                            severity="error",
                        ),
                    )
                continue

            forbidden_symbols = FORBIDDEN_LLM_PROVIDER_SYMBOL_IMPORTS.get(module_name)
            if forbidden_symbols is None:
                continue
            imported_forbidden = sorted(
                alias.name
                for alias in node.names
                if alias.name in forbidden_symbols or alias.name == "*"
            )
            if imported_forbidden:
                self.result.violations.append(
                    Violation(
                        file_path=file_path,
                        line_number=node.lineno,
                        violation_type="llm_provider_boundary",
                        message=(
                            f"LLM/agent adapter imports direct provider symbol(s) {imported_forbidden} "
                            f"from '{module_name}'. Route provider traffic through Artana-kernel-managed "
                            "model ports instead."
                        ),
                        severity="error",
                    ),
                )

    def _calculate_complexity(self, node: ast.FunctionDef) -> int:
        """Calculate cyclomatic complexity of a function."""
        complexity = 1  # Base complexity

        for child in ast.walk(node):
            if isinstance(
                child,
                ast.If
                | ast.While
                | ast.For
                | ast.AsyncFor
                | ast.Try
                | ast.With
                | ast.AsyncWith,
            ):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1

        return complexity

    def _check_import_count(self, tree: ast.AST, file_path: str) -> None:
        """Check if file has too many imports (indicates multiple responsibilities)."""
        parent_by_child: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parent_by_child[child] = parent

        imports = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Import | ast.ImportFrom)
            and not self._is_type_checking_import(
                node=node,
                parent_by_child=parent_by_child,
            )
        ]
        import_count = len(imports)

        if self._allows_import_count_override(file_path, import_count):
            return

        if import_count > MAX_IMPORTS_PER_FILE:
            self.result.violations.append(
                Violation(
                    file_path=file_path,
                    line_number=0,
                    violation_type="import_count",
                    message=(
                        f"File has too many imports ({import_count} > {MAX_IMPORTS_PER_FILE}). "
                        "May indicate multiple responsibilities. "
                        "Consider splitting into smaller, focused modules."
                    ),
                    severity="error",
                ),
            )
        elif import_count > WARNING_IMPORTS_PER_FILE:
            self.result.violations.append(
                Violation(
                    file_path=file_path,
                    line_number=0,
                    violation_type="import_count",
                    message=(
                        f"File has many imports ({import_count} > {WARNING_IMPORTS_PER_FILE}). "
                        "Consider reviewing if the file has multiple responsibilities."
                    ),
                    severity="warning",
                ),
            )

    @staticmethod
    def _is_type_checking_import(
        *,
        node: ast.AST,
        parent_by_child: dict[ast.AST, ast.AST],
    ) -> bool:
        """Return True when an import is nested under an `if TYPE_CHECKING` block."""
        current = parent_by_child.get(node)
        while current is not None:
            if isinstance(
                current,
                ast.If,
            ) and ArchitectureValidator._is_type_checking_guard(current.test):
                return True
            current = parent_by_child.get(current)
        return False

    @staticmethod
    def _is_type_checking_guard(test: ast.AST) -> bool:
        """Return True when an if-test is `TYPE_CHECKING`."""
        if isinstance(test, ast.Name):
            return test.id == "TYPE_CHECKING"
        if isinstance(test, ast.Attribute):
            return (
                test.attr == "TYPE_CHECKING"
                and isinstance(test.value, ast.Name)
                and test.value.id == "typing"
            )
        return False

    def _check_function_parameters(self, tree: ast.AST, file_path: str) -> None:
        """Check if functions have too many parameters."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                # Count parameters (including self/cls for methods)
                # Note: Methods will have self/cls, so effective param count is len - 1
                param_count = len(node.args.args)

                # Check if it's a method (has self/cls as first param)
                is_method = (
                    param_count > 0
                    and isinstance(node.args.args[0].arg, str)
                    and node.args.args[0].arg in ("self", "cls")
                )

                # Effective parameter count (excluding self/cls for methods)
                effective_params = param_count - 1 if is_method else param_count

                if effective_params > MAX_FUNCTION_PARAMETERS:
                    self.result.violations.append(
                        Violation(
                            file_path=file_path,
                            line_number=node.lineno,
                            violation_type="parameter_count",
                            message=(
                                f"Function '{node.name}' has too many parameters "
                                f"({effective_params} > {MAX_FUNCTION_PARAMETERS}). "
                                "Consider using a parameter object or splitting responsibilities."
                            ),
                            severity="warning",
                        ),
                    )

    def _check_json_type_usage(
        self,
        _tree: ast.AST,
        file_path: str,
        content: str,
    ) -> None:
        """Check for dict[str, Any] usage and suggest JSONObject/JSONValue."""
        lines = content.splitlines()

        for i, line in enumerate(lines, start=1):
            # Skip comments and strings
            if "#" in line or '"' in line or "'" in line:
                # Check if it's a comment-only line
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                # Check if Any is inside a string
                if '"' in line or "'" in line:
                    continue

            # Check for dict[str, Any] or Dict[str, Any] patterns
            if (
                "dict[str, Any]" in line or "Dict[str, Any]" in line
            ) and file_path not in ALLOWED_ANY_USAGE:
                self.result.violations.append(
                    Violation(
                        file_path=file_path,
                        line_number=i,
                        violation_type="json_type_usage",
                        message=(
                            "Use of 'dict[str, Any]' violates type safety policy. "
                            "Use 'JSONObject' or 'JSONValue' from src.type_definitions.common instead. "
                            "See docs/type_examples.md for examples."
                        ),
                        severity="error",
                    ),
                )

            # Check for dict[str, Any] in type annotations
            if (
                (":" in line or "->" in line)
                and file_path not in ALLOWED_ANY_USAGE
                and ("dict[str, Any]" in line or "Dict[str, Any]" in line)
            ):
                self.result.violations.append(
                    Violation(
                        file_path=file_path,
                        line_number=i,
                        violation_type="json_type_usage",
                        message=(
                            "Use of 'dict[str, Any]' in type annotation violates type safety policy. "
                            "Use 'JSONObject' or 'JSONValue' from src.type_definitions.common instead."
                        ),
                        severity="error",
                    ),
                )

    def _check_update_type_usage(
        self,
        tree: ast.AST,
        file_path: str,
        content: str,  # noqa: ARG002 - content unused, kept for symmetry
    ) -> None:
        """Check that update operations use TypedDict classes like GeneUpdate."""
        # Known update TypedDict classes
        update_types = {
            "GeneUpdate",
            "VariantUpdate",
            "PhenotypeUpdate",
            "EvidenceUpdate",
            "PublicationUpdate",
        }

        # Check for function definitions with "update" in name
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                and "update" in node.name.lower()
            ):
                for arg in node.args.args:
                    if arg.annotation:
                        annotation_str = _ast_to_string(arg.annotation)
                        uses_plain_dict = (
                            "dict" in annotation_str.lower()
                            and not any(
                                update_type in annotation_str
                                for update_type in update_types
                            )
                            and "JSONObject" not in annotation_str
                        )
                        likely_update_param = (
                            "update" in annotation_str.lower()
                            or arg.arg.lower() in ("updates", "update", "data")
                        )
                        if uses_plain_dict and likely_update_param:
                            self.result.violations.append(
                                Violation(
                                    file_path=file_path,
                                    line_number=node.lineno,
                                    violation_type="update_type_usage",
                                    message=(
                                        f"Update operation '{node.name}' should use TypedDict classes "
                                        f"(GeneUpdate, VariantUpdate, etc.) instead of plain dict. "
                                        "See docs/type_examples.md for examples."
                                    ),
                                    severity="warning",
                                ),
                            )

    def _check_test_fixture_usage(
        self,
        tree: ast.AST,
        file_path: str,
        content: str,
    ) -> None:
        """Check that test files use typed fixtures from tests.test_types."""
        lines = content.splitlines()

        # Check if file imports from test_types
        has_test_types_import = any(
            isinstance(node, ast.ImportFrom)
            and node.module
            and "test_types" in node.module
            for node in ast.walk(tree)
        )

        # Check for plain dict usage in test data creation
        for i, line in enumerate(lines, start=1):
            # Look for patterns like: test_data = {"key": "value"}
            # or: gene = {"gene_id": ...}
            if (
                "=" in line
                and "{" in line
                and "}" in line
                and "(" not in line.split("=")[0]
                and not line.strip().startswith("#")
                and any(token in line.lower() for token in ("test_", "gene", "variant"))
                and any(
                    pattern in line.lower()
                    for pattern in [
                        "gene_id",
                        "variant_id",
                        "phenotype_id",
                        "evidence_id",
                        "publication_id",
                    ]
                )
                and not has_test_types_import
            ):
                self.result.violations.append(
                    Violation(
                        file_path=file_path,
                        line_number=i,
                        violation_type="test_fixture_usage",
                        message=(
                            "Test file should use typed fixtures from tests.test_types.fixtures "
                            "instead of plain dictionaries. See docs/type_examples.md for examples."
                        ),
                        severity="warning",
                    ),
                )

    def _check_api_response_types(
        self,
        tree: ast.AST,
        file_path: str,
        content: str,  # noqa: ARG002 - retained for call consistency
    ) -> None:
        """Check that route endpoints return ApiResponse or PaginatedResponse."""
        # Check for route decorators
        route_functions: list[ast.FunctionDef | ast.AsyncFunctionDef] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                for decorator in node.decorator_list:
                    decorator_str = _ast_to_string(decorator)
                    if any(
                        method in decorator_str
                        for method in [
                            "@router.get",
                            "@router.post",
                            "@router.put",
                            "@router.delete",
                            "@router.patch",
                        ]
                    ):
                        route_functions.append(node)
                        break

        # Check if file imports ApiResponse or PaginatedResponse
        has_api_response_import = False
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and (
                    "ApiResponse" in str(node.names)
                    or "PaginatedResponse" in str(node.names)
                )
            ):
                has_api_response_import = True
                break

        # Check return type annotations for route functions
        for func in route_functions:
            if func.returns:
                return_annotation = _ast_to_string(func.returns)

                # Check if return type uses ApiResponse or PaginatedResponse
                missing_response_types = (
                    "ApiResponse" not in return_annotation
                    and "PaginatedResponse" not in return_annotation
                    and "dict" not in return_annotation.lower()
                )
                if missing_response_types and has_api_response_import:
                    self.result.violations.append(
                        Violation(
                            file_path=file_path,
                            line_number=func.lineno,
                            violation_type="api_response_type",
                            message=(
                                f"Route function '{func.name}' should return ApiResponse or PaginatedResponse. "
                                "See docs/type_examples.md for examples."
                            ),
                            severity="warning",
                        ),
                    )

    def _check_route_async_usage(self, tree: ast.AST, file_path: str) -> None:
        """Flag FastAPI routes that are async but never await anything."""
        for node in tree.body:
            if not isinstance(node, ast.AsyncFunctionDef):
                continue

            if not self._is_fastapi_route(node):
                continue

            route_key = f"{file_path}:{node.name}"
            if route_key in ASYNC_ROUTE_NO_AWAIT_ALLOWLIST:
                continue

            if self._function_contains_async_work(node):
                continue

            self.result.violations.append(
                Violation(
                    file_path=file_path,
                    line_number=node.lineno,
                    violation_type="async_route_no_await",
                    message=(
                        "FastAPI route is async but performs no awaited work. "
                        "Use 'def' for sync DB/service handlers."
                    ),
                    severity="error",
                ),
            )

    def _check_async_hot_path_sync_calls(
        self,
        tree: ast.AST,
        file_path: str,
    ) -> None:
        """Flag direct sync calls inside async middleware and SSE hot paths."""
        banned_calls = ASYNC_HOT_PATH_BANNED_CALLS.get(file_path)
        if banned_calls is None:
            return

        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue

            for child in ast.walk(node):
                if not isinstance(child, ast.Call):
                    continue

                call_name = self._resolve_called_name(child.func)
                if call_name not in banned_calls:
                    continue

                self.result.violations.append(
                    Violation(
                        file_path=file_path,
                        line_number=child.lineno,
                        violation_type="async_sync_hot_path_call",
                        message=(
                            "Async middleware/SSE path directly calls sync DB or "
                            "service work. Offload it from the event loop."
                        ),
                        severity="error",
                    ),
                )

    @staticmethod
    def _function_contains_async_work(node: ast.AsyncFunctionDef) -> bool:
        return any(
            isinstance(child, ast.Await | ast.AsyncFor | ast.AsyncWith)
            for child in ast.walk(node)
        )

    @staticmethod
    def _is_fastapi_route(node: ast.AsyncFunctionDef) -> bool:
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if (
                isinstance(target, ast.Attribute)
                and target.attr in FASTAPI_ROUTE_DECORATORS
            ):
                return True
        return False

    @staticmethod
    def _resolve_called_name(func: ast.expr) -> str | None:
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        return None

    def _allows_file_size_override(self, file_path: str, lines: int) -> bool:
        """Return True when file size is within the documented override."""
        override = self.overrides.file_size.get(file_path)
        if not override:
            return False
        return lines <= override.max_lines

    def _allows_class_size_override(
        self,
        file_path: str,
        class_name: str,
        methods: int,
    ) -> bool:
        """Return True when class size is within the documented override."""
        override = self.overrides.class_size.get((file_path, class_name))
        if not override:
            return False
        return methods <= override.max_methods

    def _allows_import_count_override(self, file_path: str, imports: int) -> bool:
        """Return True when import count is within the documented override."""
        override = self.overrides.import_count.get(file_path)
        if not override:
            return False
        return imports <= override.max_imports


def print_results(result: ValidationResult) -> None:
    """Print validation results in a readable format."""
    print("\n" + "=" * 80)
    print("ARCHITECTURAL COMPLIANCE VALIDATION REPORT")
    print("=" * 80)
    print(f"\nFiles checked: {result.files_checked}")
    print(f"Total lines: {result.total_lines:,}")
    print(f"\nErrors: {result.error_count}")
    print(f"Warnings: {result.warning_count}")

    if result.violations:
        print("\n" + "-" * 80)
        print("VIOLATIONS")
        print("-" * 80)

        # Group by type
        by_type: dict[str, list[Violation]] = {}
        for violation in result.violations:
            by_type.setdefault(violation.violation_type, []).append(violation)

        max_violations_to_show = 10
        for violation_type, violations in sorted(by_type.items()):
            print(f"\n{violation_type.upper()} ({len(violations)} violations):")
            for v in violations[:max_violations_to_show]:
                severity_marker = "❌" if v.severity == "error" else "⚠️"
                print(
                    f"  {severity_marker} {v.file_path}:{v.line_number} - {v.message}",
                )
            if len(violations) > max_violations_to_show:
                print(f"  ... and {len(violations) - max_violations_to_show} more")

    print("\n" + "=" * 80)
    if result.is_valid():
        print("✅ VALIDATION PASSED - No architectural errors found")
    else:
        print("❌ VALIDATION FAILED - Architectural violations detected")
    print("=" * 80 + "\n")


def main() -> int:
    """Main entry point for the validator."""

    root_path = Path(__file__).parent.parent
    validator = ArchitectureValidator(root_path)
    result = validator.validate()

    print_results(result)

    return 0 if result.is_valid() else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
