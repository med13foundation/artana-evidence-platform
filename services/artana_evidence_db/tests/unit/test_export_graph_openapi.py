from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from artana_evidence_db.product_contract import GRAPH_SERVICE_VERSION


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "scripts" / "export_graph_openapi.py").exists():
            return candidate
    message = "Unable to locate repository root for graph OpenAPI export test"
    raise RuntimeError(message)


_SCRIPT_PATH = _repo_root() / "scripts" / "export_graph_openapi.py"


def test_export_graph_openapi_writes_and_checks_schema(tmp_path: Path) -> None:
    output_path = tmp_path / "graph-openapi.json"

    generate = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), "--output", str(output_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert generate.returncode == 0, generate.stderr
    contents = output_path.read_text(encoding="utf-8")
    assert '"/v1/spaces/{space_id}/relations"' in contents
    assert '"/v1/admin/operations/runs"' in contents
    document = json.loads(contents)
    assert document["info"]["version"] == GRAPH_SERVICE_VERSION

    check = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), "--output", str(output_path), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert check.returncode == 0, check.stderr


def test_export_graph_openapi_check_fails_when_schema_is_stale(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "graph-openapi.json"
    output_path.write_text('{"openapi":"stale"}\n', encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), "--output", str(output_path), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Graph-service OpenAPI schema is out of date" in result.stderr
