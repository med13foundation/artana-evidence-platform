#!/usr/bin/env python3
"""
Pre-commit hook to block usage of `Any` (Python) or `any` (TypeScript/JavaScript).

The MED13 codebase enforces strict type safety; this hook guards against new
loosely-typed additions in staged files.
"""

from __future__ import annotations

import re
import sys
import tokenize
from io import StringIO
from pathlib import Path

PY_EXTENSIONS: set[str] = {".py", ".pyi"}
TS_EXTENSIONS: set[str] = {".ts", ".tsx", ".js", ".jsx"}

# Paths to skip (generated assets or external deps)
SKIP_PATHS: set[Path] = {
    Path("src/web/types/generated.ts"),
}
SKIP_PARTS: set[str] = {"node_modules", ".next"}

# Artana integration files with documented Any usage
# See docs/artana-kernel/docs/agent_migration.md
ARTANA_ALLOWED_ANY: set[Path] = {
    Path("src/infrastructure/llm/adapters/query_agent_adapter.py"),
}

TS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r":\s*any\b"),
    re.compile(r"\bas\s+any\b"),
    re.compile(r"<\s*any\b"),
    re.compile(r"\bArray\s*<\s*any\b"),
    re.compile(r"\bPromise\s*<\s*any\b"),
    re.compile(r"\bany\s*\["),
)


def is_skipped(path: Path) -> bool:
    if any(part in SKIP_PARTS for part in path.parts):
        return True
    if path in SKIP_PATHS:
        return True
    # Allow documented Any usage in Artana integration files
    return path in ARTANA_ALLOWED_ANY


def detect_any_tokens(path: Path, lines: list[str]) -> list[str]:
    matches: list[str] = []
    if path.suffix in PY_EXTENSIONS:
        text = "\n".join(lines)
        try:
            python_tokens = [
                f"{path}:{token.start[0]}"
                for token in tokenize.generate_tokens(StringIO(text).readline)
                if token.type == tokenize.NAME and token.string == "Any"
            ]
            matches.extend(python_tokens)
        except tokenize.TokenError:
            return matches
        return matches

    pattern_set = TS_PATTERNS
    for line_number, line in enumerate(lines, start=1):
        if any(pattern.search(line) for pattern in pattern_set):
            matches.append(f"{path}:{line_number}")
    return matches


def main(argv: list[str]) -> int:
    if len(argv) <= 1:
        return 0

    files = [Path(arg) for arg in argv[1:]]
    offending_locations: list[str] = []

    for path in files:
        if path.suffix not in PY_EXTENSIONS | TS_EXTENSIONS:
            continue
        if is_skipped(path):
            continue
        try:
            contents = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            # Skip files that are not UTF-8 text
            continue

        offending_locations.extend(detect_any_tokens(path, contents))

    if offending_locations:
        print("❌ Forbidden `Any`/`any` type usage detected:")
        for location in offending_locations:
            print(f"  - {location}")
        print(
            "Use precise types (see src/type_definitions and docs/type_examples.md) "
            "instead of `Any`/`any`.",
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
