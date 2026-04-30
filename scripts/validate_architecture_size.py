#!/usr/bin/env python3
"""Validate architecture file-size budget and override metadata.

Production Python files within the in-scope service and script trees must stay
under the default line budget. Files that exceed it must be explicitly
documented in ``architecture_overrides.json`` with a non-empty reason and an
ISO ``expires_on`` date. Overrides are a ratchet, not extra room for growth:
their ``max_lines`` value must match the current file size. The gate fails when:

* an in-scope production file exceeds the default budget without an override;
* an overridden file exceeds its declared ``max_lines``;
* an overridden file is smaller than its declared ``max_lines``;
* an overridden file is now within the default budget;
* an override path does not exist on disk;
* an override is missing ``reason``, ``tracking_ref``, or ``expires_on``;
* an override's ``tracking_ref`` is not an issue, URL, or existing docs path;
* an override's ``expires_on`` is on or before today;
* an override points outside the in-scope service/script tree.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
OVERRIDES_FILE = REPO_ROOT / "architecture_overrides.json"
DEFAULT_MAX_LINES = 1200

SCOPE_INCLUDE_PREFIXES: tuple[str, ...] = (
    "services/artana_evidence_api/",
    "services/artana_evidence_db/",
    "scripts/",
)
SCOPE_EXCLUDE_PREFIXES: tuple[str, ...] = (
    "services/artana_evidence_api/tests/",
    "services/artana_evidence_api/alembic/",
    "services/artana_evidence_db/tests/",
    "services/artana_evidence_db/alembic/",
    "scripts/ci/",
    "scripts/deploy/",
    "scripts/postgres-init/",
    "scripts/fixtures/",
)


@dataclass(frozen=True)
class FileSizeOverride:
    """A single allowlist entry for an oversized production module."""

    path: str
    max_lines: int
    reason: str
    tracking_ref: str
    expires_on: date


@dataclass(frozen=True)
class Violation:
    """An architecture-size rule violation, ready to print."""

    path: str
    message: str


def is_in_scope(relative_path: str) -> bool:
    """Return ``True`` for paths the size budget is enforced against."""
    if not relative_path.endswith(".py"):
        return False
    if not relative_path.startswith(SCOPE_INCLUDE_PREFIXES):
        return False
    return not relative_path.startswith(SCOPE_EXCLUDE_PREFIXES)


def count_lines(file_path: Path) -> int:
    """Return the physical line count of ``file_path``."""
    text = file_path.read_text(encoding="utf-8")
    if not text:
        return 0
    line_count = text.count("\n")
    if not text.endswith("\n"):
        line_count += 1
    return line_count


def scan_repo(repo_root: Path) -> dict[str, int]:
    """Return a mapping of in-scope relative paths to their physical line counts."""
    sizes: dict[str, int] = {}
    for prefix in SCOPE_INCLUDE_PREFIXES:
        root = repo_root / prefix
        if not root.exists():
            continue
        for file_path in root.rglob("*.py"):
            relative_path = file_path.relative_to(repo_root).as_posix()
            if not is_in_scope(relative_path):
                continue
            sizes[relative_path] = count_lines(file_path)
    return sizes


def parse_overrides(
    raw: object,
) -> tuple[list[FileSizeOverride], list[Violation]]:
    """Parse and validate the ``file_size`` overrides block."""
    if not isinstance(raw, dict):
        return [], [
            Violation(
                path="architecture_overrides.json",
                message="overrides root must be a JSON object",
            ),
        ]
    raw_entries = raw.get("file_size")
    if not isinstance(raw_entries, list):
        return [], [
            Violation(
                path="architecture_overrides.json",
                message='missing or invalid "file_size" array',
            ),
        ]

    overrides: list[FileSizeOverride] = []
    errors: list[Violation] = []
    seen_paths: set[str] = set()
    for index, entry in enumerate(raw_entries):
        location = f"architecture_overrides.json[file_size][{index}]"
        if not isinstance(entry, dict):
            errors.append(
                Violation(path=location, message="entry must be a JSON object"),
            )
            continue

        path = entry.get("path")
        max_lines = entry.get("max_lines")
        reason = entry.get("reason")
        tracking_ref = entry.get("tracking_ref")
        expires_on_raw = entry.get("expires_on")

        if not isinstance(path, str) or not path:
            errors.append(
                Violation(path=location, message='missing or empty "path"'),
            )
            continue
        if path in seen_paths:
            errors.append(
                Violation(
                    path=path,
                    message="duplicate override entry",
                ),
            )
            continue
        seen_paths.add(path)
        if not isinstance(max_lines, int) or max_lines <= 0:
            errors.append(
                Violation(
                    path=path,
                    message='"max_lines" must be a positive integer',
                ),
            )
            continue
        if not isinstance(reason, str) or not reason.strip():
            errors.append(
                Violation(
                    path=path,
                    message='"reason" must be a non-empty string',
                ),
            )
            continue
        if not isinstance(tracking_ref, str) or not tracking_ref.strip():
            errors.append(
                Violation(
                    path=path,
                    message='"tracking_ref" must be a non-empty issue or plan reference',
                ),
            )
            continue
        if not isinstance(expires_on_raw, str):
            errors.append(
                Violation(
                    path=path,
                    message='"expires_on" must be an ISO date string (YYYY-MM-DD)',
                ),
            )
            continue
        try:
            expires_on = date.fromisoformat(expires_on_raw)
        except ValueError:
            errors.append(
                Violation(
                    path=path,
                    message=(
                        f'"expires_on" is not a valid ISO date: {expires_on_raw!r}'
                    ),
                ),
            )
            continue

        overrides.append(
            FileSizeOverride(
                path=path,
                max_lines=max_lines,
                reason=reason.strip(),
                tracking_ref=tracking_ref.strip(),
                expires_on=expires_on,
            ),
        )
    return overrides, errors


def validate(
    *,
    file_sizes: dict[str, int],
    overrides: Iterable[FileSizeOverride],
    today: date,
    default_max: int = DEFAULT_MAX_LINES,
) -> list[Violation]:
    """Compare actual file sizes against the default budget and overrides."""
    overrides_by_path: dict[str, FileSizeOverride] = {}
    violations: list[Violation] = []

    for override in overrides:
        overrides_by_path[override.path] = override

        if not is_in_scope(override.path):
            violations.append(
                Violation(
                    path=override.path,
                    message=(
                        "override path is outside the enforced service/script scope"
                    ),
                ),
            )
            continue
        tracking_ref_error = _validate_tracking_ref(override.tracking_ref)
        if tracking_ref_error is not None:
            violations.append(
                Violation(
                    path=override.path,
                    message=tracking_ref_error,
                ),
            )
        if override.path not in file_sizes:
            violations.append(
                Violation(
                    path=override.path,
                    message="override path does not exist on disk",
                ),
            )
            continue
        if override.expires_on <= today:
            violations.append(
                Violation(
                    path=override.path,
                    message=(
                        f"override expired on {override.expires_on.isoformat()};"
                        f" refresh expires_on or split the file"
                    ),
                ),
            )
        actual = file_sizes[override.path]
        if actual <= default_max:
            violations.append(
                Violation(
                    path=override.path,
                    message=(
                        f"override is no longer needed because the file is"
                        f" {actual} lines, within the default {default_max}-line"
                        " budget; remove the override"
                    ),
                ),
            )
            continue
        if actual > override.max_lines:
            violations.append(
                Violation(
                    path=override.path,
                    message=(
                        f"file is {actual} lines but override allows"
                        f" only {override.max_lines}"
                    ),
                ),
            )
        elif actual < override.max_lines:
            violations.append(
                Violation(
                    path=override.path,
                    message=(
                        f"override allows {override.max_lines} lines but the file"
                        f" is only {actual}; lower max_lines to {actual} so the"
                        " guardrail cannot hide new growth"
                    ),
                ),
            )

    for path, line_count in sorted(file_sizes.items()):
        if path in overrides_by_path:
            continue
        if line_count > default_max:
            violations.append(
                Violation(
                    path=path,
                    message=(
                        f"file is {line_count} lines, exceeding the default"
                        f" {default_max}-line budget; split the module or add"
                        f" an entry to architecture_overrides.json"
                    ),
                ),
            )

    return violations


def _validate_tracking_ref(tracking_ref: str) -> str | None:
    """Return an error when a tracking reference is not actionable."""

    if tracking_ref.startswith(("http://", "https://")):
        parsed = urlparse(tracking_ref)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return None
        return "tracking_ref URL must include an http(s) scheme and host"
    if tracking_ref.startswith("#") and tracking_ref[1:].isdigit():
        return None
    if tracking_ref.startswith("docs/"):
        docs_path = tracking_ref.split("#", maxsplit=1)[0]
        candidate = (REPO_ROOT / docs_path).resolve()
        docs_root = (REPO_ROOT / "docs").resolve()
        if not candidate.is_relative_to(docs_root):
            return 'tracking_ref docs path must stay under "docs/"'
        if candidate.is_file():
            return None
        return f'tracking_ref docs path does not exist: "{docs_path}"'
    return (
        'tracking_ref must be a GitHub issue like "#123", an http(s) URL,'
        " or an existing docs/ path"
    )


def _load_overrides_from_disk() -> tuple[list[FileSizeOverride], list[Violation]]:
    if not OVERRIDES_FILE.exists():
        return [], [
            Violation(
                path="architecture_overrides.json",
                message="overrides file is missing",
            ),
        ]
    try:
        raw = json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [], [
            Violation(
                path="architecture_overrides.json",
                message=f"invalid JSON: {exc.msg} (line {exc.lineno})",
            ),
        ]
    return parse_overrides(raw)


def main() -> int:
    overrides, parse_errors = _load_overrides_from_disk()
    file_sizes = scan_repo(REPO_ROOT)
    rule_violations = validate(
        file_sizes=file_sizes,
        overrides=overrides,
        today=datetime.now(tz=UTC).date(),
    )
    violations = parse_errors + rule_violations
    if not violations:
        print("architecture_size: ok")
        return 0

    print("architecture_size: error")
    print(
        f"Default per-file budget is {DEFAULT_MAX_LINES} physical lines."
        " Add overrides under architecture_overrides.json `file_size`.",
    )
    for violation in violations:
        print(f"{violation.path}: {violation.message}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
