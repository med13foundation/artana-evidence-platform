from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "scripts" / "generate_ts_types.py").exists():
            return candidate
    message = "Unable to locate repository root for TypeScript generation test"
    raise RuntimeError(message)


_SCRIPT_PATH = _repo_root() / "scripts" / "generate_ts_types.py"


def test_generate_ts_types_supports_output_and_check(tmp_path: Path) -> None:
    output_path = tmp_path / "artana-evidence-db.generated.ts"

    generate = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT_PATH),
            "--module",
            "artana_evidence_db.service_contracts",
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert generate.returncode == 0, generate.stderr
    contents = output_path.read_text(encoding="utf-8")
    assert "export interface KernelRelationResponse" in contents
    assert "export interface HypothesisResponse" in contents

    check = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT_PATH),
            "--module",
            "artana_evidence_db.service_contracts",
            "--output",
            str(output_path),
            "--check",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert check.returncode == 0, check.stderr


def test_generate_ts_types_check_fails_when_output_is_stale(tmp_path: Path) -> None:
    output_path = tmp_path / "artana-evidence-db.generated.ts"
    output_path.write_text("// stale\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT_PATH),
            "--module",
            "artana_evidence_db.service_contracts",
            "--output",
            str(output_path),
            "--check",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "TypeScript type output is out of date" in result.stderr
