"""Validate that graph runtime surfaces no longer depend on MED13 aliases."""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POLICY_DOC = PROJECT_ROOT / "docs/graph/reference/runtime-alias-policy.md"
MAKEFILE_PATH = PROJECT_ROOT / "Makefile"
TARGET_PATHS = (
    PROJECT_ROOT / "src/graph",
    PROJECT_ROOT / "services/artana_evidence_db",
    PROJECT_ROOT / "docs/graph/admins",
    PROJECT_ROOT / "docs/graph/developers",
    PROJECT_ROOT / "docs/graph/reference",
    PROJECT_ROOT / "src/web/app/(dashboard)/spaces/[spaceId]/curation/page.tsx",
    PROJECT_ROOT / "scripts/_graph_service_client_support.py",
    PROJECT_ROOT / "scripts/deploy/sync_graph_cloud_run_runtime_config.sh",
)
_MED13_ENV_PATTERN = re.compile(r"\b(MED13_[A-Z0-9_]+)\b")
_TEXT_FILE_SUFFIXES = {
    ".md",
    ".py",
    ".pyi",
    ".json",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".toml",
    ".yaml",
    ".yml",
}
_GRAPH_ALIAS_PREFIXES = (
    "MED13_DEV_JWT_SECRET",
    "MED13_BYPASS_TEST_AUTH_HEADERS",
    "MED13_ENABLE_",
    "MED13_RELATION_AUTOPROMOTE_",
)
_ALLOWED_MED13_ALIASES = frozenset({"MED13_ENABLE_PHI_ENCRYPTION"})
_EXCLUDED_PATHS = {POLICY_DOC}


def _iter_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix in _TEXT_FILE_SUFFIXES
    ]


def _validate_no_legacy_aliases() -> list[str]:
    errors: list[str] = []
    for root in TARGET_PATHS:
        for path in _iter_files(root):
            if path in _EXCLUDED_PATHS:
                continue
            contents = path.read_text(encoding="utf-8")
            errors.extend(
                f"{path.relative_to(PROJECT_ROOT)} still references removed MED13 graph alias {match}"
                for match in sorted(set(_MED13_ENV_PATTERN.findall(contents)))
                if match.startswith(_GRAPH_ALIAS_PREFIXES)
                and match not in _ALLOWED_MED13_ALIASES
            )
    return errors


def _validate_policy_doc() -> list[str]:
    if not POLICY_DOC.exists():
        return [f"Missing graph runtime alias policy doc: {POLICY_DOC}"]
    contents = POLICY_DOC.read_text(encoding="utf-8")
    required_markers = (
        "# Graph Runtime Alias Policy",
        "Removed on `2026-03-13`.",
        "`GRAPH_*` env names are now the only supported graph runtime contract.",
        "make graph-phase1-alias-check",
    )
    return [
        f"Alias policy doc is missing marker {marker!r}"
        for marker in required_markers
        if marker not in contents
    ]


def _validate_make_target() -> list[str]:
    contents = MAKEFILE_PATH.read_text(encoding="utf-8")
    if "graph-phase1-alias-check:" in contents:
        return []
    return ["Missing Make target for Phase 1 alias policy: graph-phase1-alias-check"]


def main() -> int:
    errors = [
        *_validate_no_legacy_aliases(),
        *_validate_policy_doc(),
        *_validate_make_target(),
    ]
    if errors:
        print("graph_phase1_alias_policy: error")
        for error in errors:
            print(f" - {error}")
        return 1

    print("graph_phase1_alias_policy: ok")
    print(
        "graph_phase1_alias_policy: removed MED13 graph runtime aliases are absent from live graph surfaces",
    )
    print(
        "graph_phase1_alias_policy: GRAPH_* names are the only supported graph runtime contract",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
