#!/usr/bin/env python3
"""
Dependency Graph Validator for Artana Resource Library.

Validates import dependencies to ensure:
1. No circular dependencies
2. Clean Architecture layer boundaries respected
3. Proper dependency direction (domain ← application ← infrastructure ← routes)
"""

import ast
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# Layer hierarchy (lower layers can import from higher layers)
LAYER_HIERARCHY = {
    "routes": 0,  # Presentation - highest level
    "infrastructure": 1,
    "application": 2,
    "domain": 3,  # Domain - lowest level (most fundamental)
}

# Allowed cross-layer imports (application can use infrastructure repositories)
ALLOWED_CROSS_LAYER_IMPORTS = {
    "application": [
        "src.infrastructure.repositories",  # Application can use repository implementations
    ],
}

# Layer path mappings
LAYER_PATHS = {
    "routes": "src/routes",
    "infrastructure": "src/infrastructure",
    "application": "src/application",
    "domain": "src/domain",
}


@dataclass
class DependencyViolation:
    """Represents a dependency violation."""

    file_path: str
    imported_module: str
    violation_type: str
    message: str
    severity: str  # "error" or "warning"


@dataclass
class DependencyResult:
    """Results of dependency validation."""

    violations: list[DependencyViolation] = field(default_factory=list)
    circular_dependencies: list[list[str]] = field(default_factory=list)
    files_checked: int = 0

    @property
    def error_count(self) -> int:
        """Count of error-level violations."""
        return sum(1 for v in self.violations if v.severity == "error")

    def is_valid(self) -> bool:
        """Check if validation passed (no errors)."""
        return self.error_count == 0 and len(self.circular_dependencies) == 0


class DependencyValidator:
    """Validates import dependencies in the codebase."""

    def __init__(self, root_path: Path) -> None:
        """Initialize validator with root path."""
        self.root_path = root_path
        self.result = DependencyResult()
        self.import_graph: dict[str, set[str]] = defaultdict(set)
        self.file_to_layer: dict[str, str] = {}

    def validate(self) -> DependencyResult:
        """Run all dependency validation checks."""
        python_files = self._find_python_files()
        self.result.files_checked = len(python_files)

        # Build import graph
        for file_path in python_files:
            self._build_import_graph(file_path)

        # Check for circular dependencies
        self._check_circular_dependencies()

        # Check layer boundaries
        self._check_layer_boundaries()

        return self.result

    def _find_python_files(self) -> list[Path]:
        """Find all Python files in src directory."""
        python_files: list[Path] = []
        src_path = self.root_path / "src"

        if not src_path.exists():
            return python_files

        for py_file in src_path.rglob("*.py"):
            if "__pycache__" in str(py_file) or "test_" in py_file.name:
                continue
            python_files.append(py_file)

        return python_files

    def _get_file_layer(self, file_path: Path) -> str | None:
        """Determine which layer a file belongs to."""
        relative_path = str(file_path.relative_to(self.root_path))

        for layer, path_prefix in LAYER_PATHS.items():
            if relative_path.startswith(path_prefix):
                return layer

        return None

    def _build_import_graph(self, file_path: Path) -> None:
        """Build graph of imports between files."""
        parsed_module = self._parse_module(file_path)
        if parsed_module is None:
            return

        relative_path, tree = parsed_module
        self._record_file_layer(file_path=file_path, relative_path=relative_path)
        parent_by_child = self._build_parent_lookup(tree)
        import_modules = self._collect_import_modules(
            tree=tree,
            parent_by_child=parent_by_child,
        )
        self.import_graph[relative_path].update(import_modules)

    def _parse_module(self, file_path: Path) -> tuple[str, ast.AST] | None:
        """Parse a Python module and return relative path plus AST."""
        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(file_path))
            relative_path = str(file_path.relative_to(self.root_path))
        except Exception:  # noqa: BLE001, S110
            # Skip files that can't be parsed (syntax errors, etc.)
            return None
        else:
            return relative_path, tree

    def _record_file_layer(self, *, file_path: Path, relative_path: str) -> None:
        """Record architecture layer metadata for a module file."""
        layer = self._get_file_layer(file_path)
        if layer is not None:
            self.file_to_layer[relative_path] = layer

    @staticmethod
    def _build_parent_lookup(tree: ast.AST) -> dict[ast.AST, ast.AST]:
        """Build a parent lookup for AST nodes."""
        parent_by_child: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parent_by_child[child] = parent
        return parent_by_child

    def _collect_import_modules(
        self,
        *,
        tree: ast.AST,
        parent_by_child: dict[ast.AST, ast.AST],
    ) -> set[str]:
        """Extract `src/*` import module paths from an AST."""
        import_modules: set[str] = set()
        for node in ast.walk(tree):
            if self._is_type_checking_import(
                node=node,
                parent_by_child=parent_by_child,
            ):
                continue
            import_modules.update(self._extract_node_import_modules(node))
        return import_modules

    @staticmethod
    def _extract_node_import_modules(node: ast.AST) -> set[str]:
        """Extract `src/*` import module paths from a single import node."""
        if isinstance(node, ast.ImportFrom):
            return DependencyValidator._extract_import_from_module(node)
        if isinstance(node, ast.Import):
            return DependencyValidator._extract_import_alias_modules(node)
        return set()

    @staticmethod
    def _extract_import_from_module(node: ast.ImportFrom) -> set[str]:
        """Extract module path from `from x import y` nodes."""
        if node.module is None:
            return set()
        module_path = node.module.replace(".", "/")
        if not module_path.startswith("src/"):
            return set()
        return {module_path}

    @staticmethod
    def _extract_import_alias_modules(node: ast.Import) -> set[str]:
        """Extract module paths from `import x` nodes."""
        import_modules: set[str] = set()
        for alias in node.names:
            module_path = alias.name.replace(".", "/")
            if module_path.startswith("src/"):
                import_modules.add(module_path)
        return import_modules

    @staticmethod
    def _is_type_checking_guard(test_node: ast.expr) -> bool:
        """Return True when the condition matches TYPE_CHECKING guards."""
        return (
            isinstance(test_node, ast.Name) and test_node.id == "TYPE_CHECKING"
        ) or (
            isinstance(test_node, ast.Attribute)
            and isinstance(test_node.value, ast.Name)
            and test_node.value.id == "typing"
            and test_node.attr == "TYPE_CHECKING"
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
            ) and DependencyValidator._is_type_checking_guard(
                current.test,
            ):
                return True
            current = parent_by_child.get(current)
        return False

    def _check_circular_dependencies(self) -> None:
        """Detect circular dependencies using DFS."""
        visited: set[str] = set()
        rec_stack: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in self.import_graph.get(node, set()):
                # Find actual file path for neighbor
                neighbor_file = self._find_file_for_module(neighbor)
                if not neighbor_file:
                    continue

                if neighbor_file not in visited:
                    dfs(neighbor_file)
                elif neighbor_file in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor_file)
                    cycle = path[cycle_start:] + [neighbor_file]
                    min_cycle_length = 2  # Only report meaningful cycles
                    if len(cycle) > min_cycle_length:
                        self.result.circular_dependencies.append(cycle.copy())

            rec_stack.remove(node)
            path.pop()

        for file_path in self.import_graph:
            if file_path not in visited:
                dfs(file_path)

    def _find_file_for_module(self, module_path: str) -> str | None:
        """Find file path for a module path."""
        # Try different variations
        variations = [
            module_path + ".py",
            module_path + "/__init__.py",
        ]

        for var in variations:
            if var in self.file_to_layer:
                return var

        # Try to find matching file
        for file_path in self.file_to_layer:
            if file_path.startswith(module_path):
                return file_path

        return None

    def _check_layer_boundaries(self) -> None:
        """Check that imports respect layer boundaries."""
        for file_path, imports in self.import_graph.items():
            file_layer = self.file_to_layer.get(file_path)
            if not file_layer:
                continue

            file_layer_level = LAYER_HIERARCHY.get(file_layer, 999)

            for imported_module in imports:
                imported_file = self._find_file_for_module(imported_module)
                if not imported_file:
                    continue

                imported_layer = self.file_to_layer.get(imported_file)
                if not imported_layer:
                    continue

                imported_layer_level = LAYER_HIERARCHY.get(imported_layer, 999)

                # Check if this is an allowed cross-layer import
                is_allowed = False
                if file_layer in ALLOWED_CROSS_LAYER_IMPORTS:
                    for allowed_pattern in ALLOWED_CROSS_LAYER_IMPORTS[file_layer]:
                        # Convert pattern to file path format
                        pattern_path = allowed_pattern.replace(".", "/")
                        # Check if imported module matches the pattern
                        if imported_module.startswith(pattern_path):
                            is_allowed = True
                            break

                # Lower level (higher number) should not import from higher level (lower number)
                # Exception: Application can import infrastructure repositories
                if file_layer_level > imported_layer_level and not is_allowed:
                    self.result.violations.append(
                        DependencyViolation(
                            file_path=file_path,
                            imported_module=imported_module,
                            violation_type="layer_violation",
                            message=(
                                f"Layer violation: {file_layer} layer (level {file_layer_level}) "
                                f"imports from {imported_layer} layer (level {imported_layer_level}). "
                                "Lower layers should not depend on higher layers. "
                                "Use repository interfaces instead of concrete implementations."
                            ),
                            severity="error",
                        ),
                    )


def print_results(result: DependencyResult) -> None:
    """Print validation results."""
    print("\n" + "=" * 80)
    print("DEPENDENCY VALIDATION REPORT")
    print("=" * 80)
    print(f"\nFiles checked: {result.files_checked}")
    print(f"Errors: {result.error_count}")
    print(f"Circular dependencies: {len(result.circular_dependencies)}")

    if result.circular_dependencies:
        print("\n" + "-" * 80)
        print("CIRCULAR DEPENDENCIES")
        print("-" * 80)
        for i, cycle in enumerate(result.circular_dependencies, 1):
            print(f"\nCycle {i}:")
            for file_path in cycle:
                print(f"  → {file_path}")

    if result.violations:
        print("\n" + "-" * 80)
        print("LAYER VIOLATIONS")
        print("-" * 80)
        for v in result.violations[:20]:  # Show first 20
            print(f"  ❌ {v.file_path}")
            print(f"     Imports: {v.imported_module}")
            print(f"     {v.message}\n")

    print("\n" + "=" * 80)
    if result.is_valid():
        print("✅ VALIDATION PASSED - No dependency violations found")
    else:
        print("❌ VALIDATION FAILED - Dependency violations detected")
    print("=" * 80 + "\n")


def main() -> int:
    """Main entry point."""

    root_path = Path(__file__).parent.parent
    validator = DependencyValidator(root_path)
    result = validator.validate()

    print_results(result)

    return 0 if result.is_valid() else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
