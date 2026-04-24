from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast

from artana_evidence_api.config import get_settings


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "scripts" / "export_artana_evidence_api_openapi.py").exists():
            return candidate
    message = (
        "Unable to locate repository root for artana-evidence-api OpenAPI export test"
    )
    raise RuntimeError(message)


_SCRIPT_PATH = _repo_root() / "scripts" / "export_artana_evidence_api_openapi.py"


def _assert_accepted_post_contract(
    document: dict[str, object],
    *,
    path: str,
    accepted_schema_ref: str,
) -> None:
    paths = cast("dict[str, object]", document["paths"])
    post = cast("dict[str, object]", cast("dict[str, object]", paths[path])["post"])
    parameters = cast("list[object]", post["parameters"])
    assert any(
        (
            cast("dict[str, object]", parameter).get("in") == "header"
            and cast("dict[str, object]", parameter).get("name") == "prefer"
        )
        for parameter in parameters
    )

    responses = cast("dict[str, object]", post["responses"])
    accepted_response = cast("dict[str, object]", responses["202"])
    accepted_content = cast(
        "dict[str, object]",
        cast("dict[str, object]", accepted_response["content"])["application/json"],
    )
    accepted_schema = cast("dict[str, object]", accepted_content["schema"])
    assert accepted_schema["$ref"] == accepted_schema_ref


def test_export_artana_evidence_api_openapi_writes_and_checks_schema(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "artana-evidence-api-openapi.json"

    generate = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), "--output", str(output_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert generate.returncode == 0, generate.stderr
    contents = output_path.read_text(encoding="utf-8")
    assert '"/v1/spaces/{space_id}/agents/research-bootstrap/runs"' in contents
    assert '"/v1/spaces/{space_id}/agents/continuous-learning/runs"' in contents
    assert '"/v1/spaces/{space_id}/agents/mechanism-discovery/runs"' in contents
    assert '"/v1/spaces/{space_id}/agents/graph-curation/runs"' in contents
    assert '"/v1/spaces/{space_id}/agents/supervisor/runs"' in contents
    assert '"/v1/spaces/{space_id}/chat-sessions/{session_id}/messages"' in contents
    assert (
        '"/v1/spaces/{space_id}/chat-sessions/{session_id}/messages/{run_id}/stream"'
        in contents
    )
    assert '"/v1/spaces/{space_id}/documents/pdf"' in contents
    assert '"/v1/spaces/{space_id}/documents/{document_id}/extract"' in contents
    assert '"/v1/spaces/{space_id}/review-queue"' in contents
    assert '"/v1/spaces/{space_id}/pubmed/searches"' in contents
    assert '"/v2/spaces/{space_id}/tasks"' in contents
    assert '"/v2/spaces/{space_id}/tasks/{task_id}/outputs"' in contents
    assert '"/v2/spaces/{space_id}/review-items"' in contents
    assert '"/v2/spaces/{space_id}/evidence-map/entities"' in contents
    assert (
        '"/v2/spaces/{space_id}/workflows/evidence-curation/tasks"' in contents
    )
    assert '"/v2/spaces/{space_id}/workflows/full-research/tasks"' in contents
    assert '"stream_url"' in contents
    document = json.loads(contents)
    assert document["info"]["version"] == get_settings().version
    _assert_accepted_post_contract(
        document,
        path="/v1/spaces/{space_id}/agents/research-bootstrap/runs",
        accepted_schema_ref="#/components/schemas/HarnessAcceptedRunResponse",
    )
    _assert_accepted_post_contract(
        document,
        path="/v2/spaces/{space_id}/workflows/topic-setup/tasks",
        accepted_schema_ref="#/components/schemas/HarnessAcceptedRunResponse",
    )
    _assert_accepted_post_contract(
        document,
        path="/v1/spaces/{space_id}/agents/continuous-learning/runs",
        accepted_schema_ref="#/components/schemas/HarnessAcceptedRunResponse",
    )
    _assert_accepted_post_contract(
        document,
        path="/v2/spaces/{space_id}/workflows/continuous-review/tasks",
        accepted_schema_ref="#/components/schemas/HarnessAcceptedRunResponse",
    )
    _assert_accepted_post_contract(
        document,
        path="/v1/spaces/{space_id}/agents/mechanism-discovery/runs",
        accepted_schema_ref="#/components/schemas/HarnessAcceptedRunResponse",
    )
    _assert_accepted_post_contract(
        document,
        path="/v1/spaces/{space_id}/agents/graph-curation/runs",
        accepted_schema_ref="#/components/schemas/HarnessAcceptedRunResponse",
    )
    _assert_accepted_post_contract(
        document,
        path="/v1/spaces/{space_id}/agents/supervisor/runs",
        accepted_schema_ref="#/components/schemas/HarnessAcceptedRunResponse",
    )
    _assert_accepted_post_contract(
        document,
        path="/v1/spaces/{space_id}/chat-sessions/{session_id}/messages",
        accepted_schema_ref="#/components/schemas/ChatMessageAcceptedResponse",
    )

    check = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), "--output", str(output_path), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert check.returncode == 0, check.stderr


def test_export_artana_evidence_api_openapi_check_fails_when_schema_is_stale(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "artana-evidence-api-openapi.json"
    output_path.write_text('{"openapi":"stale"}\n', encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), "--output", str(output_path), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Artana Evidence API OpenAPI schema is out of date" in result.stderr
