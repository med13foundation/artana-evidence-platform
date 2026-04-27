"""Unit tests for the architecture-size validator."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from scripts.validate_architecture_size import (
    DEFAULT_MAX_LINES,
    FileSizeOverride,
    Violation,
    count_lines,
    is_in_scope,
    parse_overrides,
    scan_repo,
    validate,
)

TODAY = date(2026, 4, 26)
FUTURE = date(2026, 12, 31)
PAST = date(2026, 1, 1)


def _override(
    path: str,
    *,
    max_lines: int = 1500,
    expires_on: date = FUTURE,
    reason: str = "transitional",
) -> FileSizeOverride:
    return FileSizeOverride(
        path=path,
        max_lines=max_lines,
        reason=reason,
        expires_on=expires_on,
    )


class TestIsInScope:
    @pytest.mark.parametrize(
        "path",
        [
            "services/artana_evidence_api/foo.py",
            "services/artana_evidence_api/routers/bar.py",
            "services/artana_evidence_db/baz.py",
            "scripts/run_eval.py",
        ],
    )
    def test_includes_production_python(self, path: str) -> None:
        assert is_in_scope(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "services/artana_evidence_api/tests/unit/test_x.py",
            "services/artana_evidence_api/alembic/versions/abc.py",
            "services/artana_evidence_db/tests/integration/test_y.py",
            "services/artana_evidence_db/alembic/env.py",
            "scripts/ci/plan_service_checks.py",
            "scripts/deploy/release.py",
            "scripts/postgres-init/seed.py",
            "scripts/fixtures/sample.py",
        ],
    )
    def test_excludes_tests_alembic_and_internal_scripts(self, path: str) -> None:
        assert is_in_scope(path) is False

    @pytest.mark.parametrize(
        "path",
        [
            "services/artana_evidence_api/foo.txt",
            "services/artana_evidence_api/Dockerfile",
            "tests/unit/test_other.py",
            "docs/notes.md",
        ],
    )
    def test_excludes_non_python_or_out_of_tree(self, path: str) -> None:
        assert is_in_scope(path) is False


class TestCountLines:
    def test_empty_file_is_zero_lines(self, tmp_path: Path) -> None:
        file_path = tmp_path / "empty.py"
        file_path.write_text("", encoding="utf-8")
        assert count_lines(file_path) == 0

    def test_trailing_newline_does_not_inflate(self, tmp_path: Path) -> None:
        file_path = tmp_path / "two.py"
        file_path.write_text("a\nb\n", encoding="utf-8")
        assert count_lines(file_path) == 2

    def test_missing_trailing_newline_still_counts_last_line(
        self,
        tmp_path: Path,
    ) -> None:
        file_path = tmp_path / "two.py"
        file_path.write_text("a\nb", encoding="utf-8")
        assert count_lines(file_path) == 2

    def test_single_line_without_newline(self, tmp_path: Path) -> None:
        file_path = tmp_path / "one.py"
        file_path.write_text("only", encoding="utf-8")
        assert count_lines(file_path) == 1


class TestParseOverrides:
    def test_accepts_minimal_valid_entry(self) -> None:
        raw = {
            "file_size": [
                {
                    "path": "services/artana_evidence_api/foo.py",
                    "max_lines": 1500,
                    "reason": "transitional",
                    "expires_on": "2026-12-31",
                },
            ],
        }
        overrides, errors = parse_overrides(raw)

        assert errors == []
        assert overrides == [
            FileSizeOverride(
                path="services/artana_evidence_api/foo.py",
                max_lines=1500,
                reason="transitional",
                expires_on=FUTURE,
            ),
        ]

    def test_rejects_non_object_root(self) -> None:
        overrides, errors = parse_overrides([])
        assert overrides == []
        assert len(errors) == 1
        assert "must be a JSON object" in errors[0].message

    def test_rejects_missing_file_size_array(self) -> None:
        overrides, errors = parse_overrides({})
        assert overrides == []
        assert len(errors) == 1
        assert "file_size" in errors[0].message

    @pytest.mark.parametrize(
        ("entry", "expected_fragment"),
        [
            ({"max_lines": 1500, "reason": "x", "expires_on": "2026-12-31"}, "path"),
            (
                {
                    "path": "services/artana_evidence_api/foo.py",
                    "max_lines": 0,
                    "reason": "x",
                    "expires_on": "2026-12-31",
                },
                "max_lines",
            ),
            (
                {
                    "path": "services/artana_evidence_api/foo.py",
                    "max_lines": 1500,
                    "reason": "   ",
                    "expires_on": "2026-12-31",
                },
                "reason",
            ),
            (
                {
                    "path": "services/artana_evidence_api/foo.py",
                    "max_lines": 1500,
                    "reason": "x",
                    "expires_on": "not-a-date",
                },
                "expires_on",
            ),
            (
                {
                    "path": "services/artana_evidence_api/foo.py",
                    "max_lines": 1500,
                    "reason": "x",
                },
                "expires_on",
            ),
        ],
    )
    def test_rejects_malformed_entries(
        self,
        entry: dict[str, object],
        expected_fragment: str,
    ) -> None:
        overrides, errors = parse_overrides({"file_size": [entry]})

        assert overrides == []
        assert len(errors) == 1
        assert expected_fragment in errors[0].message

    def test_flags_duplicate_paths(self) -> None:
        entry = {
            "path": "services/artana_evidence_api/foo.py",
            "max_lines": 1500,
            "reason": "x",
            "expires_on": "2026-12-31",
        }
        overrides, errors = parse_overrides({"file_size": [entry, dict(entry)]})

        assert len(overrides) == 1
        assert any("duplicate" in err.message for err in errors)


class TestValidate:
    def test_clean_repo_within_default_passes(self) -> None:
        violations = validate(
            file_sizes={
                "services/artana_evidence_api/small.py": 800,
                "services/artana_evidence_db/medium.py": 1200,
            },
            overrides=[],
            today=TODAY,
        )
        assert violations == []

    def test_oversized_file_without_override_fails(self) -> None:
        violations = validate(
            file_sizes={"services/artana_evidence_api/big.py": 1500},
            overrides=[],
            today=TODAY,
        )
        assert len(violations) == 1
        assert violations[0].path == "services/artana_evidence_api/big.py"
        assert "1500 lines" in violations[0].message
        assert f"{DEFAULT_MAX_LINES}-line budget" in violations[0].message

    def test_oversized_file_with_sufficient_override_passes(self) -> None:
        violations = validate(
            file_sizes={"services/artana_evidence_api/big.py": 1500},
            overrides=[_override("services/artana_evidence_api/big.py", max_lines=1700)],
            today=TODAY,
        )
        assert violations == []

    def test_file_exceeds_override_max_lines_fails(self) -> None:
        violations = validate(
            file_sizes={"services/artana_evidence_api/big.py": 1800},
            overrides=[_override("services/artana_evidence_api/big.py", max_lines=1700)],
            today=TODAY,
        )
        assert len(violations) == 1
        assert "1800 lines" in violations[0].message
        assert "1700" in violations[0].message

    def test_override_for_missing_file_fails(self) -> None:
        violations = validate(
            file_sizes={},
            overrides=[_override("services/artana_evidence_api/gone.py")],
            today=TODAY,
        )
        assert len(violations) == 1
        assert "does not exist" in violations[0].message

    def test_override_outside_scope_fails(self) -> None:
        violations = validate(
            file_sizes={"docs/large_essay.py": 5000},
            overrides=[_override("docs/large_essay.py", max_lines=6000)],
            today=TODAY,
        )
        assert any("outside" in v.message for v in violations)

    def test_expired_override_fails_even_if_within_max_lines(self) -> None:
        violations = validate(
            file_sizes={"services/artana_evidence_api/big.py": 1500},
            overrides=[
                _override(
                    "services/artana_evidence_api/big.py",
                    max_lines=1700,
                    expires_on=PAST,
                ),
            ],
            today=TODAY,
        )
        assert any("expired" in v.message for v in violations)

    def test_override_expiring_today_fails(self) -> None:
        """expires_on is interpreted as "must be after today", not "after-or-equal"."""
        violations = validate(
            file_sizes={"services/artana_evidence_api/big.py": 1500},
            overrides=[
                _override(
                    "services/artana_evidence_api/big.py",
                    max_lines=1700,
                    expires_on=TODAY,
                ),
            ],
            today=TODAY,
        )
        assert any("expired" in v.message for v in violations)


class TestScanRepo:
    def test_collects_only_in_scope_python_files(self, tmp_path: Path) -> None:
        api_root = tmp_path / "services" / "artana_evidence_api"
        db_root = tmp_path / "services" / "artana_evidence_db"
        scripts_root = tmp_path / "scripts"
        for parent in (api_root, db_root, scripts_root):
            parent.mkdir(parents=True)

        (api_root / "kept.py").write_text("a\nb\nc\n", encoding="utf-8")
        (api_root / "tests").mkdir()
        (api_root / "tests" / "skipped.py").write_text("x\n", encoding="utf-8")
        (api_root / "alembic").mkdir()
        (api_root / "alembic" / "skipped.py").write_text("x\n", encoding="utf-8")

        (db_root / "tests").mkdir()
        (db_root / "tests" / "skipped.py").write_text("x\n", encoding="utf-8")
        (db_root / "kept.py").write_text("a\nb\n", encoding="utf-8")

        (scripts_root / "ci").mkdir()
        (scripts_root / "ci" / "skipped.py").write_text("x\n", encoding="utf-8")
        (scripts_root / "kept.py").write_text("a\n", encoding="utf-8")

        sizes = scan_repo(tmp_path)

        assert sizes == {
            "services/artana_evidence_api/kept.py": 3,
            "services/artana_evidence_db/kept.py": 2,
            "scripts/kept.py": 1,
        }

    def test_handles_missing_root_dirs_gracefully(self, tmp_path: Path) -> None:
        assert scan_repo(tmp_path) == {}


class TestViolationDataclass:
    def test_is_immutable(self) -> None:
        violation = Violation(path="x", message="y")
        with pytest.raises(AttributeError):
            violation.path = "z"  # type: ignore[misc]
