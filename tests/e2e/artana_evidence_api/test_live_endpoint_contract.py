"""Live black-box endpoint coverage for the Artana Evidence API service."""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import cast
from uuid import uuid4

import httpx
import pytest

BASE_URL_ENV = "ARTANA_EVIDENCE_API_LIVE_BASE_URL"
BOOTSTRAP_KEY_ENV = "ARTANA_EVIDENCE_API_BOOTSTRAP_KEY"
DEFAULT_BASE_URL = "http://localhost:8091"
RUNTIME_BLOCK_STATUSES = {500, 502, 503}
DECIDED_PROPOSAL_STATUSES = {"promoted", "rejected"}
LIVE_SEED_ENTITY_ID = "11111111-1111-4111-8111-111111111111"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_OPENAPI_ARTIFACT_PATH = (
    _REPO_ROOT / "services" / "artana_evidence_api" / "openapi.json"
)


def _emit_progress(message: str) -> None:
    sys.stderr.write(f"{message}\n")
    sys.stderr.flush()


def _now_suffix() -> str:
    return str(int(time.time()))


def _tiny_pdf_bytes() -> bytes:
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 36 120 Td (Artana PDF) Tj ET\n"
        b"endstream\nendobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000010 00000 n \n0000000053 00000 n \n"
        b"0000000110 00000 n \n0000000241 00000 n \n0000000336 00000 n \n"
        b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n406\n%%EOF\n"
    )


def _test_auth_headers(unique: str) -> dict[str, str]:
    user_id = str(uuid4())
    email = f"codex-live-{unique}@example.com"
    return {
        "X-TEST-USER-ID": user_id,
        "X-TEST-USER-EMAIL": email,
        "X-TEST-USER-ROLE": "admin",
    }


def _as_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"Expected dict payload, received {type(value)!r}")
    return cast("dict[str, object]", value)


def _as_list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"Expected list payload, received {type(value)!r}")
    return cast("list[object]", value)


def _resolve_local_ref(spec: dict[str, object], ref: str) -> dict[str, object]:
    if not ref.startswith("#/"):
        raise AssertionError(f"Unsupported schema ref: {ref}")
    node: object = spec
    for segment in ref.removeprefix("#/").split("/"):
        node = _as_dict(node)[segment]
    return _as_dict(node)


def _response_schema_for_operation(
    spec: dict[str, object],
    path: str,
    method: str,
    status_code: int,
) -> dict[str, object] | None:
    operation_path = _resolve_operation_path(spec, path, method)
    operation = _as_dict(_as_dict(_as_dict(spec["paths"])[operation_path])[method])
    responses = _as_dict(operation["responses"])
    response = responses.get(str(status_code))
    if not isinstance(response, dict):
        return None
    content = _as_dict(response).get("content")
    if not isinstance(content, dict):
        return None
    json_content = _as_dict(content).get("application/json")
    if not isinstance(json_content, dict):
        return None
    schema = _as_dict(json_content).get("schema")
    if not isinstance(schema, dict):
        return None
    if "$ref" in schema:
        return _resolve_local_ref(spec, str(schema["$ref"]))
    return schema


def _assert_top_level_contract(
    spec: dict[str, object],
    path: str,
    method: str,
    status_code: int,
    payload: object,
) -> None:
    schema = _response_schema_for_operation(spec, path, method, status_code)
    if schema is None:
        return
    schema_type = schema.get("type")
    if schema_type == "object":
        payload_dict = _as_dict(payload)
        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if isinstance(key, str):
                    assert key in payload_dict, f"Missing required key '{key}'"
    elif schema_type == "array":
        _as_list(payload)


def _expected_success_status(
    spec: dict[str, object],
    path: str,
    method: str,
) -> int:
    operation_path = _resolve_operation_path(spec, path, method)
    operation = _as_dict(_as_dict(_as_dict(spec["paths"])[operation_path])[method])
    responses = _as_dict(operation["responses"])
    for code in responses:
        if code.startswith("2") and code.isdigit():
            return int(code)
    raise AssertionError(f"No success response declared for {method.upper()} {path}")


@dataclass(slots=True)
class EndpointResult:
    method: str
    path: str
    expected_status: int | None
    actual_status: int | None
    outcome: str
    detail: str = ""


@dataclass(slots=True)
class LiveContext:
    base_url: str
    bootstrap_key: str
    client: httpx.Client
    spec: dict[str, object]
    results: list[EndpointResult] = field(default_factory=list)
    created_ids: dict[str, str] = field(default_factory=dict)
    seen_operations: set[tuple[str, str]] = field(default_factory=set)
    known_harness_id: str = ""
    valid_proposal_ids: list[str] = field(default_factory=list)
    artifact_keys: list[str] = field(default_factory=list)
    approval_keys: list[str] = field(default_factory=list)
    chat_candidate_count: int = 0
    supervisor_candidate_count: int = 0

    def auth_headers(self) -> dict[str, str]:
        return {"X-Artana-Key": self.created_ids["api_key"]}

    def mark(
        self,
        *,
        method: str,
        path: str,
        expected_status: int | None,
        actual_status: int | None,
        outcome: str,
        detail: str = "",
    ) -> None:
        normalized_path = path
        try:
            normalized_path = _resolve_operation_path(self.spec, path, method.lower())
        except KeyError:
            normalized_path = path
        self.seen_operations.add((method.lower(), normalized_path))
        _emit_progress(
            f"[live-contract] {outcome.upper()} {method.upper()} {path}"
            f" expected={expected_status} actual={actual_status}"
            + (f" detail={detail}" if detail else ""),
        )
        self.results.append(
            EndpointResult(
                method=method.upper(),
                path=path,
                expected_status=expected_status,
                actual_status=actual_status,
                outcome=outcome,
                detail=detail,
            ),
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        expected_status: int | None = None,
        acceptable_statuses: set[int] | None = None,
        headers: dict[str, str] | None = None,
        json_body: dict[str, object] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        params: dict[str, object] | None = None,
        allow_blocked: bool = False,
        timeout: float | None = None,
    ) -> httpx.Response:
        _emit_progress(f"[live-contract] REQUEST {method.upper()} {path}")
        try:
            response = self.client.request(
                method=method,
                url=path,
                headers=headers,
                json=json_body,
                files=files,
                params=params,
                timeout=timeout,
            )
        except httpx.TimeoutException as exc:
            if allow_blocked:
                self.mark(
                    method=method,
                    path=path,
                    expected_status=expected_status,
                    actual_status=None,
                    outcome="blocked",
                    detail=f"timeout: {exc}",
                )
                request = self.client.build_request(
                    method=method,
                    url=path,
                    headers=headers,
                    json=json_body,
                    files=files,
                    params=params,
                )
                return httpx.Response(status_code=599, request=request, text="timeout")
            raise
        expected_values = (
            acceptable_statuses
            if acceptable_statuses is not None
            else ({expected_status} if expected_status is not None else set())
        )
        if response.status_code in expected_values:
            payload: object
            if response.headers.get("content-type", "").startswith("application/json"):
                payload = response.json()
                if expected_status is not None and 200 <= response.status_code < 300:
                    _assert_top_level_contract(
                        self.spec,
                        path,
                        method.lower(),
                        response.status_code,
                        payload,
                    )
            self.mark(
                method=method,
                path=path,
                expected_status=expected_status,
                actual_status=response.status_code,
                outcome="passed",
            )
            return response
        if allow_blocked and response.status_code in RUNTIME_BLOCK_STATUSES:
            self.mark(
                method=method,
                path=path,
                expected_status=expected_status,
                actual_status=response.status_code,
                outcome="blocked",
                detail=response.text[:240],
            )
            return response
        self.mark(
            method=method,
            path=path,
            expected_status=expected_status,
            actual_status=response.status_code,
            outcome="failed",
            detail=response.text[:240],
        )
        raise AssertionError(
            f"{method.upper()} {path} returned {response.status_code},"
            f" expected {sorted(expected_values)}. Body: {response.text[:300]}",
        )


def _operation_set(spec: dict[str, object]) -> set[tuple[str, str]]:
    operations: set[tuple[str, str]] = set()
    for path, value in _as_dict(spec["paths"]).items():
        path_item = _as_dict(value)
        for method in path_item:
            operations.add((method.lower(), path))
    return operations


def _direct_live_operation_set(spec: dict[str, object]) -> set[tuple[str, str]]:
    """Return canonical operations this black-box live suite must hit directly."""

    return {
        operation
        for operation in _operation_set(spec)
        if operation[1] == "/health" or operation[1].startswith("/v1/")
    }


def _resolve_operation_path(
    spec: dict[str, object],
    actual_path: str,
    method: str,
) -> str:
    paths = _as_dict(spec["paths"])
    if actual_path in paths and method in _as_dict(paths[actual_path]):
        return actual_path

    actual_segments = [segment for segment in actual_path.split("/") if segment != ""]
    for template_path, value in paths.items():
        path_item = _as_dict(value)
        if method not in path_item:
            continue
        template_segments = [
            segment for segment in template_path.split("/") if segment != ""
        ]
        if len(template_segments) != len(actual_segments):
            continue
        if all(
            template.startswith("{") and template.endswith("}") or template == actual
            for template, actual in zip(template_segments, actual_segments, strict=True)
        ):
            return template_path
    raise KeyError(f"Unable to resolve OpenAPI path for {method.upper()} {actual_path}")


def _proposal_id_if_open(raw_proposal: object) -> str | None:
    proposal = _as_dict(raw_proposal)
    raw_id = proposal.get("id")
    if not isinstance(raw_id, str):
        return None
    status = proposal.get("status")
    if isinstance(status, str) and status.lower() in DECIDED_PROPOSAL_STATUSES:
        return None
    return raw_id


def _poll_for_proposals(ctx: LiveContext, *, timeout_seconds: float = 8.0) -> None:
    deadline = time.time() + timeout_seconds
    ctx.valid_proposal_ids = []
    while time.time() < deadline:
        response = ctx.client.get(
            f"/v1/spaces/{ctx.created_ids['space_id']}/proposals",
            headers=ctx.auth_headers(),
        )
        if response.status_code == 200:
            payload = _as_dict(response.json())
            proposals = _as_list(payload["proposals"])
            if proposals:
                ctx.valid_proposal_ids = [
                    proposal_id
                    for proposal in proposals
                    if (proposal_id := _proposal_id_if_open(proposal)) is not None
                ]
                if ctx.valid_proposal_ids:
                    return
        time.sleep(0.5)


def _load_openapi(base_url: str) -> dict[str, object]:
    response = httpx.get(f"{base_url}/openapi.json", timeout=10.0)
    response.raise_for_status()
    return cast("dict[str, object]", response.json())


def _load_repo_openapi() -> dict[str, object]:
    return cast(
        "dict[str, object]",
        json.loads(_OPENAPI_ARTIFACT_PATH.read_text(encoding="utf-8")),
    )


def _build_live_context(base_url: str, bootstrap_key: str) -> LiveContext:
    spec = _load_openapi(base_url)
    repo_spec = _load_repo_openapi()
    live_operations = _operation_set(spec)
    repo_operations = _operation_set(repo_spec)
    assert live_operations == repo_operations, (
        "Live OpenAPI operations differ from the checked-in contract artifact. "
        f"live_only={sorted(live_operations - repo_operations)} "
        f"repo_only={sorted(repo_operations - live_operations)}"
    )
    client = httpx.Client(base_url=base_url, timeout=20.0, follow_redirects=True)
    return LiveContext(
        base_url=base_url,
        bootstrap_key=bootstrap_key,
        client=client,
        spec=spec,
    )


def _exercise_auth_and_space_setup(ctx: LiveContext, *, unique: str) -> None:
    spec = ctx.spec
    expected_200 = _expected_success_status(spec, "/health", "get")
    bootstrap_headers = {"X-Artana-Bootstrap-Key": ctx.bootstrap_key}
    test_auth_headers = _test_auth_headers(unique)
    ctx.request("GET", "/health", expected_status=expected_200)
    ctx.request(
        "GET",
        "/v1/harnesses",
        acceptable_statuses={401, 403},
        headers={},
    )
    ctx.request(
        "POST",
        "/v1/auth/bootstrap",
        expected_status=422,
        headers=bootstrap_headers,
        json_body={},
    )
    bootstrap_response = ctx.request(
        "POST",
        "/v1/auth/bootstrap",
        acceptable_statuses={
            _expected_success_status(spec, "/v1/auth/bootstrap", "post"),
            409,
        },
        headers=bootstrap_headers,
        json_body={
            "email": f"codex-live-{unique}@example.com",
            "username": f"codex_live_{unique}",
            "full_name": "Codex Live Contract",
            "role": "admin",
            "api_key_name": "Codex Live Key",
            "create_default_space": True,
        },
    )
    if bootstrap_response.status_code == 201:
        bootstrap_payload = _as_dict(bootstrap_response.json())
        issued_key = _as_dict(bootstrap_payload["api_key"])
        ctx.created_ids["api_key"] = str(issued_key["api_key"])
        ctx.created_ids["api_key_id"] = str(issued_key["id"])
        default_space = bootstrap_payload.get("default_space")
        if isinstance(default_space, dict):
            ctx.created_ids["default_space_id"] = str(_as_dict(default_space)["id"])
    else:
        default_space_response = ctx.request(
            "PUT",
            "/v1/spaces/default",
            expected_status=_expected_success_status(spec, "/v1/spaces/default", "put"),
            headers=test_auth_headers,
        )
        default_space_payload = _as_dict(default_space_response.json())
        ctx.created_ids["default_space_id"] = str(default_space_payload["id"])
        primary_key_response = ctx.request(
            "POST",
            "/v1/auth/api-keys",
            expected_status=_expected_success_status(spec, "/v1/auth/api-keys", "post"),
            headers=test_auth_headers,
            json_body={"name": "Codex Live Key", "description": "live contract"},
        )
        primary_key_payload = _as_dict(primary_key_response.json())
        issued_key = _as_dict(primary_key_payload["api_key"])
        ctx.created_ids["api_key"] = str(issued_key["api_key"])
        ctx.created_ids["api_key_id"] = str(issued_key["id"])

    ctx.request(
        "GET",
        "/v1/auth/me",
        expected_status=_expected_success_status(spec, "/v1/auth/me", "get"),
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "GET",
        "/v1/auth/me",
        acceptable_statuses={401, 403},
        headers={"X-Artana-Key": "invalid"},
    )
    ctx.request(
        "GET",
        "/v1/auth/api-keys",
        expected_status=_expected_success_status(spec, "/v1/auth/api-keys", "get"),
        headers=ctx.auth_headers(),
    )
    secondary_key_response = ctx.request(
        "POST",
        "/v1/auth/api-keys",
        expected_status=_expected_success_status(spec, "/v1/auth/api-keys", "post"),
        headers=ctx.auth_headers(),
        json_body={"name": "Codex Secondary Key", "description": "live contract"},
    )
    secondary_key_payload = _as_dict(secondary_key_response.json())
    secondary_issued_key = _as_dict(secondary_key_payload["api_key"])
    ctx.created_ids["secondary_api_key"] = str(
        secondary_issued_key["api_key"],
    )
    ctx.created_ids["secondary_api_key_id"] = str(secondary_issued_key["id"])
    rotated_key_response = ctx.request(
        "POST",
        f"/v1/auth/api-keys/{ctx.created_ids['secondary_api_key_id']}/rotate",
        expected_status=_expected_success_status(
            spec,
            "/v1/auth/api-keys/{key_id}/rotate",
            "post",
        ),
        headers=ctx.auth_headers(),
    )
    rotated_key_payload = _as_dict(rotated_key_response.json())
    rotated_key = _as_dict(rotated_key_payload["new_key"])
    ctx.created_ids["rotated_api_key_id"] = str(rotated_key["id"])
    ctx.request(
        "DELETE",
        f"/v1/auth/api-keys/{ctx.created_ids['rotated_api_key_id']}",
        expected_status=_expected_success_status(
            spec,
            "/v1/auth/api-keys/{key_id}",
            "delete",
        ),
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "GET",
        "/v1/auth/api-keys",
        expected_status=_expected_success_status(spec, "/v1/auth/api-keys", "get"),
        headers=ctx.auth_headers(),
    )

    harnesses_response = ctx.request(
        "GET",
        "/v1/harnesses",
        expected_status=_expected_success_status(spec, "/v1/harnesses", "get"),
        headers=ctx.auth_headers(),
    )
    harnesses_payload = _as_dict(harnesses_response.json())
    harnesses = _as_list(harnesses_payload["harnesses"])
    assert harnesses, "Expected at least one harness in discovery response"
    known_harness = _as_dict(harnesses[0])
    ctx.known_harness_id = str(known_harness["id"])
    ctx.request(
        "GET",
        f"/v1/harnesses/{ctx.known_harness_id}",
        expected_status=_expected_success_status(
            spec,
            "/v1/harnesses/{harness_id}",
            "get",
        ),
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "GET",
        "/v1/harnesses/unknown-harness-id",
        acceptable_statuses={404},
        headers=ctx.auth_headers(),
    )

    ctx.request(
        "GET",
        "/v1/spaces",
        expected_status=_expected_success_status(spec, "/v1/spaces", "get"),
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "POST",
        "/v1/spaces",
        expected_status=422,
        headers=ctx.auth_headers(),
        json_body={},
    )
    primary_space_response = ctx.request(
        "POST",
        "/v1/spaces",
        expected_status=_expected_success_status(spec, "/v1/spaces", "post"),
        headers=ctx.auth_headers(),
        json_body={
            "name": f"Codex Live Space {unique}",
            "description": "Primary space",
        },
    )
    primary_space_payload = _as_dict(primary_space_response.json())
    ctx.created_ids["space_id"] = str(primary_space_payload["id"])
    ctx.request(
        "PATCH",
        f"/v1/spaces/{ctx.created_ids['space_id']}/settings",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/settings",
            "patch",
        ),
        headers=ctx.auth_headers(),
        json_body={
            "research_orchestration_mode": "full_ai_guarded",
            "full_ai_guarded_rollout_profile": "guarded_dry_run",
        },
    )
    ctx.request(
        "GET",
        f"/v1/spaces/{ctx.created_ids['space_id']}/members",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/members",
            "get",
        ),
        headers=ctx.auth_headers(),
    )
    member_response = ctx.request(
        "POST",
        "/v1/auth/testers",
        expected_status=_expected_success_status(
            spec,
            "/v1/auth/testers",
            "post",
        ),
        headers=ctx.auth_headers(),
        json_body={
            "email": f"member-{unique}@artana.dev",
            "username": f"member-{unique}",
            "full_name": "Live Contract Member",
            "role": "viewer",
            "api_key_name": "Live Contract Member Key",
            "create_default_space": False,
        },
    )
    member_payload = _as_dict(member_response.json())
    member_user = _as_dict(member_payload["user"])
    member_user_id = str(member_user["id"])
    ctx.created_ids["member_user_id"] = member_user_id
    ctx.request(
        "POST",
        f"/v1/spaces/{ctx.created_ids['space_id']}/members",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/members",
            "post",
        ),
        headers=ctx.auth_headers(),
        json_body={"user_id": member_user_id, "role": "viewer"},
    )
    ctx.request(
        "DELETE",
        f"/v1/spaces/{ctx.created_ids['space_id']}/members/{member_user_id}",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/members/{user_id}",
            "delete",
        ),
        headers=ctx.auth_headers(),
    )

    throwaway_space_response = ctx.request(
        "POST",
        "/v1/spaces",
        expected_status=_expected_success_status(spec, "/v1/spaces", "post"),
        headers=ctx.auth_headers(),
        json_body={
            "name": f"Codex Throwaway {unique}",
            "description": "Cleanup space",
        },
    )
    throwaway_payload = _as_dict(throwaway_space_response.json())
    ctx.created_ids["throwaway_space_id"] = str(throwaway_payload["id"])

    ctx.request(
        "PUT",
        "/v1/spaces/default",
        expected_status=_expected_success_status(spec, "/v1/spaces/default", "put"),
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "GET",
        "/v1/spaces",
        expected_status=_expected_success_status(spec, "/v1/spaces", "get"),
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "DELETE",
        "/v1/spaces/not-a-uuid",
        expected_status=422,
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "DELETE",
        f"/v1/spaces/{str(uuid4())}",
        acceptable_statuses={404},
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "DELETE",
        f"/v1/spaces/{ctx.created_ids['throwaway_space_id']}",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}",
            "delete",
        ),
        headers=ctx.auth_headers(),
    )


def _exercise_documents(ctx: LiveContext, space_id: str) -> None:
    spec = ctx.spec
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/documents",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/documents",
            "get",
        ),
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/documents/text",
        expected_status=422,
        headers=ctx.auth_headers(),
        json_body={"title": "Missing text"},
    )
    text_document_response = ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/documents/text",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/documents/text",
            "post",
        ),
        headers=ctx.auth_headers(),
        json_body={
            "title": "Live MED13 note",
            "text": "MED13 shows grounded evidence in a live contract test.",
            "metadata": {"source": "codex-live"},
        },
    )
    text_document_payload = _as_dict(text_document_response.json())
    text_document = _as_dict(text_document_payload["document"])
    ctx.created_ids["document_id"] = str(text_document["id"])
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/documents/{ctx.created_ids['document_id']}",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/documents/{document_id}",
            "get",
        ),
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/documents/{str(uuid4())}",
        acceptable_statuses={404},
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/documents/pdf",
        acceptable_statuses={400, 422},
        headers=ctx.auth_headers(),
    )
    pdf_document_response = ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/documents/pdf",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/documents/pdf",
            "post",
        ),
        headers=ctx.auth_headers(),
        files={
            "file": ("live-contract.pdf", _tiny_pdf_bytes(), "application/pdf"),
        },
    )
    pdf_document_payload = _as_dict(pdf_document_response.json())
    pdf_document = _as_dict(pdf_document_payload["document"])
    ctx.created_ids["pdf_document_id"] = str(pdf_document["id"])
    extract_response = ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/documents/{ctx.created_ids['document_id']}/extract",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/documents/{document_id}/extract",
            "post",
        ),
        headers=ctx.auth_headers(),
        allow_blocked=True,
    )
    if extract_response.status_code < 500:
        extract_payload = _as_dict(extract_response.json())
        extracted_proposals = _as_list(extract_payload.get("proposals", []))
        ctx.valid_proposal_ids = [
            proposal_id
            for proposal in extracted_proposals
            if (proposal_id := _proposal_id_if_open(proposal)) is not None
        ]
        if not ctx.valid_proposal_ids:
            _poll_for_proposals(ctx)


def _exercise_pubmed(ctx: LiveContext, space_id: str) -> None:
    spec = ctx.spec
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/pubmed/searches",
        expected_status=422,
        headers=ctx.auth_headers(),
        json_body={},
    )
    pubmed_search_response = ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/pubmed/searches",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/pubmed/searches",
            "post",
        ),
        headers=ctx.auth_headers(),
        json_body={
            "parameters": {
                "gene_symbol": "MED13",
                "search_term": "congenital heart disease",
                "max_results": 3,
                "sort_by": "relevance",
            },
        },
        allow_blocked=True,
    )
    if pubmed_search_response.status_code < 500:
        pubmed_payload = _as_dict(pubmed_search_response.json())
        ctx.created_ids["job_id"] = str(pubmed_payload["id"])
        ctx.request(
            "GET",
            f"/v1/spaces/{space_id}/pubmed/searches/{ctx.created_ids['job_id']}",
            expected_status=_expected_success_status(
                spec,
                "/v1/spaces/{space_id}/pubmed/searches/{job_id}",
                "get",
            ),
            headers=ctx.auth_headers(),
        )
    else:
        ctx.mark(
            method="GET",
            path="/v1/spaces/{space_id}/pubmed/searches/{job_id}",
            expected_status=_expected_success_status(
                spec,
                "/v1/spaces/{space_id}/pubmed/searches/{job_id}",
                "get",
            ),
            actual_status=None,
            outcome="blocked",
            detail="Skipped because live PubMed search creation was blocked",
        )
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/pubmed/searches/{str(uuid4())}",
        acceptable_statuses={404},
        headers=ctx.auth_headers(),
    )


def _exercise_chat(ctx: LiveContext, space_id: str) -> None:
    spec = ctx.spec
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/chat-sessions",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/chat-sessions",
            "get",
        ),
        headers=ctx.auth_headers(),
    )
    chat_session_response = ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/chat-sessions",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/chat-sessions",
            "post",
        ),
        headers=ctx.auth_headers(),
        json_body={"title": "Live MED13 briefing"},
    )
    chat_session_payload = _as_dict(chat_session_response.json())
    ctx.created_ids["session_id"] = str(chat_session_payload["id"])
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/chat-sessions/{ctx.created_ids['session_id']}",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/chat-sessions/{session_id}",
            "get",
        ),
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/chat-sessions/{str(uuid4())}",
        acceptable_statuses={404},
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/chat-sessions/{ctx.created_ids['session_id']}/messages",
        expected_status=422,
        headers=ctx.auth_headers(),
        json_body={},
    )
    chat_message_success_status = _expected_success_status(
        spec,
        "/v1/spaces/{space_id}/chat-sessions/{session_id}/messages",
        "post",
    )
    chat_message_response = ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/chat-sessions/{ctx.created_ids['session_id']}/messages",
        acceptable_statuses={chat_message_success_status, 202, 409},
        headers=ctx.auth_headers(),
        json_body={
            "content": "Summarize the MED13 evidence in the uploaded note.",
            "document_ids": [ctx.created_ids["document_id"]],
            "max_depth": 1,
            "top_k": 5,
            "refresh_pubmed_if_needed": False,
        },
        allow_blocked=True,
    )
    if chat_message_response.status_code in {chat_message_success_status, 202}:
        chat_message_payload = _as_dict(chat_message_response.json())
        run_payload = _as_dict(chat_message_payload["run"])
        ctx.created_ids["chat_run_id"] = str(run_payload["id"])
        graph_result = chat_message_payload.get("graph_chat_result")
        if isinstance(graph_result, dict):
            candidates = _as_list(
                _as_dict(graph_result).get("graph_write_candidates", []),
            )
            ctx.chat_candidate_count = len(candidates)
    else:
        ctx.created_ids["chat_run_id"] = str(uuid4())
    ctx.request(
        "GET",
        (
            f"/v1/spaces/{space_id}/chat-sessions/{ctx.created_ids['session_id']}"
            f"/messages/{ctx.created_ids['chat_run_id']}/stream"
        ),
        acceptable_statuses={200, 404},
        headers=ctx.auth_headers(),
        allow_blocked=True,
        timeout=5.0,
    )
    proposal_from_chat_response = ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/chat-sessions/{ctx.created_ids['session_id']}/proposals/graph-write",
        acceptable_statuses={201, 404, 409, 422},
        headers=ctx.auth_headers(),
        json_body={},
        allow_blocked=True,
    )
    if proposal_from_chat_response.status_code == 201:
        _poll_for_proposals(ctx)
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/chat-sessions/{ctx.created_ids['session_id']}/graph-write-candidates/0/review",
        acceptable_statuses={200, 201, 404, 409, 422},
        headers=ctx.auth_headers(),
        json_body={"decision": "reject", "reason": "Live contract review"},
        allow_blocked=True,
    )


def _exercise_generic_runs(ctx: LiveContext, space_id: str) -> None:
    spec = ctx.spec
    generic_run_payload = {
        "harness_id": ctx.known_harness_id,
        "title": "Live generic run",
        "input_payload": {"objective": "Test run contract"},
    }
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/runs",
        expected_status=422,
        headers=ctx.auth_headers(),
        json_body={},
    )
    generic_run_response = ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/runs",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/runs",
            "post",
        ),
        headers=ctx.auth_headers(),
        json_body=generic_run_payload,
        allow_blocked=True,
    )
    if generic_run_response.status_code < 500:
        generic_run_response_payload = _as_dict(generic_run_response.json())
        ctx.created_ids["run_id"] = str(generic_run_response_payload["id"])
    else:
        ctx.created_ids["run_id"] = str(uuid4())
    run_id = ctx.created_ids["run_id"]

    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/runs",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/runs",
            "get",
        ),
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/runs/{run_id}",
        acceptable_statuses={200, 404},
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/runs/{str(uuid4())}",
        acceptable_statuses={404},
        headers=ctx.auth_headers(),
    )
    for suffix, path_template in (
        ("progress", "/v1/spaces/{space_id}/runs/{run_id}/progress"),
        ("events", "/v1/spaces/{space_id}/runs/{run_id}/events"),
        ("capabilities", "/v1/spaces/{space_id}/runs/{run_id}/capabilities"),
        ("policy-decisions", "/v1/spaces/{space_id}/runs/{run_id}/policy-decisions"),
        ("workspace", "/v1/spaces/{space_id}/runs/{run_id}/workspace"),
        ("artifacts", "/v1/spaces/{space_id}/runs/{run_id}/artifacts"),
    ):
        formatted_path = path_template.format(space_id=space_id, run_id=run_id)
        response = ctx.request(
            "GET",
            formatted_path,
            acceptable_statuses={200, 404},
            headers=ctx.auth_headers(),
        )
        if suffix == "artifacts" and response.status_code == 200:
            artifact_payload = _as_dict(response.json())
            artifacts = _as_list(artifact_payload.get("artifacts", []))
            ctx.artifact_keys = [
                str(_as_dict(artifact)["artifact_key"])
                for artifact in artifacts
                if "artifact_key" in _as_dict(artifact)
            ]
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/runs/{run_id}/intent",
        expected_status=422,
        headers=ctx.auth_headers(),
        json_body={},
    )
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/runs/{run_id}/intent",
        acceptable_statuses={200, 201, 404},
        headers=ctx.auth_headers(),
        json_body={
            "summary": "Review potential changes",
            "proposed_actions": [
                {
                    "approval_key": "live-approval-1",
                    "title": "Review live action",
                    "risk_level": "low",
                    "target_type": "claim",
                    "target_id": "claim-live-1",
                    "requires_approval": True,
                    "metadata": {},
                },
            ],
            "metadata": {},
        },
    )
    approvals_response = ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/runs/{run_id}/approvals",
        acceptable_statuses={200, 404},
        headers=ctx.auth_headers(),
    )
    if approvals_response.status_code == 200:
        approvals_payload = _as_dict(approvals_response.json())
        approvals = _as_list(approvals_payload.get("approvals", []))
        ctx.approval_keys = [
            str(_as_dict(approval)["approval_key"])
            for approval in approvals
            if "approval_key" in _as_dict(approval)
        ]
    approval_key = ctx.approval_keys[0] if ctx.approval_keys else "missing-approval"
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/runs/{run_id}/approvals/{approval_key}",
        acceptable_statuses={200, 404, 409, 422},
        headers=ctx.auth_headers(),
        json_body={"decision": "approved", "reason": "Live approval check"},
    )
    artifact_key = ctx.artifact_keys[0] if ctx.artifact_keys else "missing-artifact"
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/runs/{run_id}/artifacts/{artifact_key}",
        acceptable_statuses={200, 404},
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/runs/{run_id}/artifacts/missing-artifact",
        acceptable_statuses={404},
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/runs/{run_id}/resume",
        acceptable_statuses={200, 404, 409, 422},
        headers=ctx.auth_headers(),
        json_body={},
        allow_blocked=True,
    )


def _exercise_proposals(ctx: LiveContext, space_id: str) -> None:
    spec = ctx.spec
    proposals_list_response = ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/proposals",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/proposals",
            "get",
        ),
        headers=ctx.auth_headers(),
    )
    proposals_payload = _as_dict(proposals_list_response.json())
    proposals = _as_list(proposals_payload["proposals"])
    all_proposal_ids = [
        str(_as_dict(proposal)["id"])
        for proposal in proposals
        if "id" in _as_dict(proposal)
    ]
    ctx.valid_proposal_ids = [
        proposal_id
        for proposal in proposals
        if (proposal_id := _proposal_id_if_open(proposal)) is not None
    ]
    known_proposal_id = all_proposal_ids[0] if all_proposal_ids else str(uuid4())
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/proposals/{known_proposal_id}",
        acceptable_statuses={200, 404},
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/proposals/{str(uuid4())}",
        acceptable_statuses={404},
        headers=ctx.auth_headers(),
    )
    promote_target = (
        ctx.valid_proposal_ids[0] if ctx.valid_proposal_ids else str(uuid4())
    )
    reject_target = (
        ctx.valid_proposal_ids[1] if len(ctx.valid_proposal_ids) >= 2 else str(uuid4())
    )
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/proposals/{promote_target}/promote",
        acceptable_statuses={200, 404, 409, 422},
        headers=ctx.auth_headers(),
        json_body={"reason": "Live promote review", "metadata": {"source": "codex"}},
        allow_blocked=True,
    )
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/proposals/{reject_target}/reject",
        acceptable_statuses={200, 404, 409, 422},
        headers=ctx.auth_headers(),
        json_body={"reason": "Live reject review", "metadata": {"source": "codex"}},
    )
    decided_targets = {promote_target, reject_target}
    ctx.valid_proposal_ids = [
        proposal_id
        for proposal_id in ctx.valid_proposal_ids
        if proposal_id not in decided_targets
    ]


def _exercise_review_queue(ctx: LiveContext, space_id: str) -> None:
    spec = ctx.spec
    queue_response = ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/review-queue",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/review-queue",
            "get",
        ),
        headers=ctx.auth_headers(),
    )
    queue_payload = _as_dict(queue_response.json())
    items = _as_list(queue_payload.get("items", []))
    if items:
        first_item = _as_dict(items[0])
        item_id = str(first_item["id"])
        ctx.request(
            "GET",
            f"/v1/spaces/{space_id}/review-queue/{item_id}",
            expected_status=_expected_success_status(
                spec,
                "/v1/spaces/{space_id}/review-queue/{item_id}",
                "get",
            ),
            headers=ctx.auth_headers(),
        )
        available_actions = [
            str(action)
            for action in _as_list(first_item.get("available_actions", []))
            if isinstance(action, str)
        ]
        if available_actions:
            ctx.request(
                "POST",
                f"/v1/spaces/{space_id}/review-queue/{item_id}/actions",
                expected_status=_expected_success_status(
                    spec,
                    "/v1/spaces/{space_id}/review-queue/{item_id}/actions",
                    "post",
                ),
                headers=ctx.auth_headers(),
                json_body={
                    "action": available_actions[0],
                    "reason": "Live queue action",
                    "metadata": {"source": "codex-live"},
                },
                allow_blocked=True,
            )
            return
    missing_item_id = f"review_item:{uuid4()}"
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/review-queue/{missing_item_id}",
        acceptable_statuses={404},
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/review-queue/{missing_item_id}/actions",
        acceptable_statuses={404},
        headers=ctx.auth_headers(),
        json_body={"action": "dismiss", "reason": "Missing item check"},
    )


def _exercise_graph_explorer(ctx: LiveContext, space_id: str) -> None:
    spec = ctx.spec
    claims_response = ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/graph-explorer/claims",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/graph-explorer/claims",
            "get",
        ),
        headers=ctx.auth_headers(),
        params={"offset": 0, "limit": 10},
    )
    claims_payload = _as_dict(claims_response.json())
    claims = _as_list(claims_payload.get("claims", []))
    known_claim_id = (
        str(_as_dict(claims[0])["id"])
        if claims and "id" in _as_dict(claims[0])
        else str(uuid4())
    )
    entities_response = ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/graph-explorer/entities",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/graph-explorer/entities",
            "get",
        ),
        headers=ctx.auth_headers(),
        params={"q": "MED13", "offset": 0, "limit": 10},
    )
    entities_payload = _as_dict(entities_response.json())
    entities = _as_list(entities_payload.get("entities", []))
    known_entity_id = (
        str(_as_dict(entities[0])["id"])
        if entities and "id" in _as_dict(entities[0])
        else LIVE_SEED_ENTITY_ID
    )
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/graph-explorer/entities/{known_entity_id}/claims",
        acceptable_statuses={200, 404},
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/graph-explorer/claims/{known_claim_id}/evidence",
        acceptable_statuses={200, 404},
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/graph-explorer/document",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/graph-explorer/document",
            "post",
        ),
        headers=ctx.auth_headers(),
        json_body={
            "mode": "starter",
            "depth": 2,
            "top_k": 10,
            "include_claims": True,
            "include_evidence": True,
        },
        allow_blocked=True,
    )


def _exercise_research_init_and_state(ctx: LiveContext, space_id: str) -> None:
    spec = ctx.spec
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/research-init",
        expected_status=422,
        headers=ctx.auth_headers(),
        json_body={},
    )
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/research-init",
        acceptable_statuses={
            _expected_success_status(
                spec, "/v1/spaces/{space_id}/research-init", "post"
            ),
            202,
        },
        headers=ctx.auth_headers(),
        json_body={
            "objective": "Initialize a MED13-focused research space for live verification.",
            "seed_terms": ["MED13"],
            "title": "Live research init",
            "sources": {
                "pubmed": True,
                "clinvar": True,
                "marrvel": False,
                "mondo": True,
            },
        },
        allow_blocked=True,
        timeout=90.0,
    )
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/research-state",
        acceptable_statuses={200, 404},
        headers=ctx.auth_headers(),
        allow_blocked=True,
    )


def _exercise_marrvel(ctx: LiveContext, space_id: str) -> None:
    spec = ctx.spec
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/marrvel/searches",
        expected_status=422,
        headers=ctx.auth_headers(),
        json_body={},
    )
    search_response = ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/marrvel/searches",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/marrvel/searches",
            "post",
        ),
        headers=ctx.auth_headers(),
        json_body={"gene_symbol": "MED13"},
        allow_blocked=True,
        timeout=60.0,
    )
    if search_response.status_code < 500:
        search_payload = _as_dict(search_response.json())
        result_id = str(search_payload["id"])
        ctx.request(
            "GET",
            f"/v1/spaces/{space_id}/marrvel/searches/{result_id}",
            expected_status=_expected_success_status(
                spec,
                "/v1/spaces/{space_id}/marrvel/searches/{result_id}",
                "get",
            ),
            headers=ctx.auth_headers(),
        )
    else:
        ctx.mark(
            method="GET",
            path="/v1/spaces/{space_id}/marrvel/searches/{result_id}",
            expected_status=_expected_success_status(
                spec,
                "/v1/spaces/{space_id}/marrvel/searches/{result_id}",
                "get",
            ),
            actual_status=None,
            outcome="blocked",
            detail="Skipped because live MARRVEL search creation was blocked",
        )
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/marrvel/ingest",
        acceptable_statuses={
            _expected_success_status(
                spec, "/v1/spaces/{space_id}/marrvel/ingest", "post"
            ),
            422,
        },
        headers=ctx.auth_headers(),
        json_body={"gene_symbols": ["MED13"]},
        allow_blocked=True,
        timeout=60.0,
    )


def _exercise_typed_runs(ctx: LiveContext, space_id: str) -> None:
    spec = ctx.spec
    evidence_selection_candidate = {
        "source_key": "pubmed",
        "search_id": str(uuid4()),
        "max_records": 1,
    }
    typed_run_requests: list[tuple[str, dict[str, object], bool]] = [
        (
            "/v1/spaces/{space_id}/agents/continuous-learning/runs",
            {
                "title": "Live continuous learning",
                "seed_entity_ids": [LIVE_SEED_ENTITY_ID],
            },
            True,
        ),
        (
            "/v1/spaces/{space_id}/agents/graph-connections/runs",
            {"seed_entity_ids": [LIVE_SEED_ENTITY_ID]},
            True,
        ),
        (
            "/v1/spaces/{space_id}/agents/evidence-selection/runs",
            {
                "goal": "Select MED13 evidence from a saved source-search candidate.",
                "instructions": "Use deterministic screening for live contract coverage.",
                "planner_mode": "deterministic",
                "candidate_searches": [evidence_selection_candidate],
                "max_records_per_search": 1,
            },
            True,
        ),
        (
            "/v1/spaces/{space_id}/agents/full-ai-orchestrator/runs",
            {
                "objective": "Run the deterministic full AI orchestrator baseline.",
                "seed_terms": ["MED13"],
                "planner_mode": "shadow",
            },
            True,
        ),
        (
            "/v1/spaces/{space_id}/agents/graph-curation/runs",
            {"proposal_ids": ctx.valid_proposal_ids[:1] or [str(uuid4())]},
            True,
        ),
        (
            "/v1/spaces/{space_id}/agents/graph-search/runs",
            {"question": "What is known about MED13?"},
            True,
        ),
        (
            "/v1/spaces/{space_id}/agents/hypotheses/runs",
            {"title": "Live hypothesis run", "seed_entity_ids": [LIVE_SEED_ENTITY_ID]},
            True,
        ),
        (
            "/v1/spaces/{space_id}/agents/mechanism-discovery/runs",
            {"seed_entity_ids": [LIVE_SEED_ENTITY_ID]},
            True,
        ),
        (
            "/v1/spaces/{space_id}/agents/research-bootstrap/runs",
            {"objective": "Bootstrap MED13 evidence"},
            True,
        ),
        (
            "/v1/spaces/{space_id}/agents/research-onboarding/runs",
            {
                "research_title": "MED13 live onboarding",
                "primary_objective": "Test onboarding",
            },
            True,
        ),
        (
            "/v1/spaces/{space_id}/agents/research-onboarding/turns",
            {
                "thread_id": "thread-live",
                "message_id": "message-live",
                "intent": "refine",
                "mode": "reply",
                "reply_text": "Please focus on MED13 evidence.",
                "attachments": [],
            },
            True,
        ),
    ]
    for path_template, body, allow_blocked in typed_run_requests:
        path = path_template.format(space_id=space_id)
        ctx.request(
            "POST",
            path,
            acceptable_statuses={400, 422},
            headers=ctx.auth_headers(),
            json_body={},
        )
        success_status = _expected_success_status(spec, path_template, "post")
        # Queue-backed run endpoints may either create immediately (201),
        # accept the run for asynchronous worker execution (202), or report
        # that a dependency artifact is not ready yet (409) on persistent live
        # databases with existing queued work.
        acceptable_success_statuses = {success_status, 202, 409}
        if path_template == "/v1/spaces/{space_id}/agents/graph-curation/runs":
            acceptable_success_statuses.add(404)
        response = ctx.request(
            "POST",
            path,
            acceptable_statuses=acceptable_success_statuses,
            headers=ctx.auth_headers(),
            json_body=body,
            allow_blocked=allow_blocked,
            timeout=90.0 if "research-onboarding" in path_template else None,
        )
        typed_run_id: object = None
        if (
            response.status_code < 500
            and path_template
            != "/v1/spaces/{space_id}/agents/research-onboarding/turns"
        ):
            typed_payload = _as_dict(response.json())
            typed_run_id = typed_payload.get("id")
            if not isinstance(typed_run_id, str):
                raw_run = typed_payload.get("run")
                if isinstance(raw_run, dict):
                    typed_run_id = raw_run.get("id")
            if isinstance(typed_run_id, str):
                ctx.request(
                    "GET",
                    f"/v1/spaces/{space_id}/runs/{typed_run_id}",
                    acceptable_statuses={200, 404},
                    headers=ctx.auth_headers(),
                )
        if path_template == "/v1/spaces/{space_id}/agents/evidence-selection/runs":
            parent_run_id = (
                typed_run_id if isinstance(typed_run_id, str) else str(uuid4())
            )
            ctx.request(
                "POST",
                (
                    f"/v1/spaces/{space_id}/agents/evidence-selection/runs/"
                    f"{parent_run_id}/follow-ups"
                ),
                acceptable_statuses={201, 202, 404, 409},
                headers={**ctx.auth_headers(), "Prefer": "respond-async"},
                json_body={
                    "instructions": "Refine the deterministic live evidence slice.",
                    "planner_mode": "deterministic",
                    "candidate_searches": [evidence_selection_candidate],
                    "max_records_per_search": 1,
                },
                allow_blocked=True,
            )


def _exercise_schedules(ctx: LiveContext, space_id: str) -> None:
    spec = ctx.spec
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/schedules",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/schedules",
            "get",
        ),
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/schedules",
        expected_status=422,
        headers=ctx.auth_headers(),
        json_body={},
    )
    schedule_response = ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/schedules",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/schedules",
            "post",
        ),
        headers=ctx.auth_headers(),
        json_body={
            "cadence": "daily",
            "title": "Live daily schedule",
            "seed_entity_ids": [LIVE_SEED_ENTITY_ID],
        },
    )
    schedule_payload = _as_dict(schedule_response.json())
    ctx.created_ids["schedule_id"] = str(schedule_payload["id"])
    schedule_id = ctx.created_ids["schedule_id"]
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/schedules/{schedule_id}",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/schedules/{schedule_id}",
            "get",
        ),
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/schedules/{str(uuid4())}",
        acceptable_statuses={404},
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "PATCH",
        f"/v1/spaces/{space_id}/schedules/{schedule_id}",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/schedules/{schedule_id}",
            "patch",
        ),
        headers=ctx.auth_headers(),
        json_body={"title": "Updated live schedule"},
    )
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/schedules/{schedule_id}/pause",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/schedules/{schedule_id}/pause",
            "post",
        ),
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/schedules/{schedule_id}/resume",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/schedules/{schedule_id}/resume",
            "post",
        ),
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/schedules/{schedule_id}/run-now",
        acceptable_statuses={200, 201, 202, 409},
        headers=ctx.auth_headers(),
        allow_blocked=True,
        timeout=90.0,
    )


def _exercise_supervisor(ctx: LiveContext, space_id: str) -> None:
    spec = ctx.spec
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/agents/supervisor/runs",
            "get",
        ),
        headers=ctx.auth_headers(),
    )
    ctx.request(
        "GET",
        f"/v1/spaces/{space_id}/agents/supervisor/dashboard",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/agents/supervisor/dashboard",
            "get",
        ),
        headers=ctx.auth_headers(),
    )
    supervisor_response = ctx.request(
        "POST",
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/agents/supervisor/runs",
            "post",
        ),
        headers=ctx.auth_headers(),
        json_body={
            "objective": "Live supervisor workflow",
            "briefing_question": "What is known about MED13?",
        },
        allow_blocked=True,
        timeout=120.0,
    )
    if supervisor_response.status_code < 500:
        supervisor_payload = _as_dict(supervisor_response.json())
        supervisor_run_id = str(_as_dict(supervisor_payload["run"])["id"])
        ctx.created_ids["supervisor_run_id"] = supervisor_run_id
        supervisor_reviews = _as_list(
            supervisor_payload.get("chat_graph_write_reviews", []),
        )
        ctx.supervisor_candidate_count = len(supervisor_reviews)
        ctx.request(
            "GET",
            f"/v1/spaces/{space_id}/agents/supervisor/runs/{supervisor_run_id}",
            expected_status=_expected_success_status(
                spec,
                "/v1/spaces/{space_id}/agents/supervisor/runs/{run_id}",
                "get",
            ),
            headers=ctx.auth_headers(),
        )
        ctx.request(
            "POST",
            (
                f"/v1/spaces/{space_id}/agents/supervisor/runs/"
                f"{supervisor_run_id}/chat-graph-write-candidates/0/review"
            ),
            acceptable_statuses={200, 201, 404, 409, 422},
            headers=ctx.auth_headers(),
            json_body={"decision": "reject", "reason": "Live supervisor review"},
            allow_blocked=True,
        )
        return
    ctx.mark(
        method="GET",
        path="/v1/spaces/{space_id}/agents/supervisor/runs/{run_id}",
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/agents/supervisor/runs/{run_id}",
            "get",
        ),
        actual_status=None,
        outcome="blocked",
        detail="Skipped because supervisor creation was blocked",
    )
    ctx.mark(
        method="POST",
        path=(
            "/v1/spaces/{space_id}/agents/supervisor/runs/{run_id}/"
            "chat-graph-write-candidates/{candidate_index}/review"
        ),
        expected_status=_expected_success_status(
            spec,
            "/v1/spaces/{space_id}/agents/supervisor/runs/{run_id}/chat-graph-write-candidates/{candidate_index}/review",
            "post",
        ),
        actual_status=None,
        outcome="blocked",
        detail="Skipped because supervisor creation was blocked",
    )


def _assert_all_operations_seen(ctx: LiveContext) -> None:
    missing = sorted(_direct_live_operation_set(ctx.spec) - ctx.seen_operations)
    if missing:
        missing_text = ", ".join(f"{method.upper()} {path}" for method, path in missing)
        raise AssertionError(f"Live suite missed operations: {missing_text}")


def _redacted_created_ids(created_ids: dict[str, str]) -> dict[str, str]:
    """Return created ids with generated credential values removed."""

    sensitive_keys = {"api_key", "secondary_api_key"}
    return {
        key: "<redacted>" if key in sensitive_keys else value
        for key, value in created_ids.items()
    }


def _write_live_report(ctx: LiveContext, base_url: str) -> None:
    report_dir = Path("logs")
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / "artana_evidence_api_live_contract_report.json"
    report_payload = {
        "base_url": base_url,
        "created_ids": _redacted_created_ids(ctx.created_ids),
        "summary": {
            "passed": sum(result.outcome == "passed" for result in ctx.results),
            "failed": sum(result.outcome == "failed" for result in ctx.results),
            "blocked": sum(result.outcome == "blocked" for result in ctx.results),
        },
        "results": [asdict(result) for result in ctx.results],
    }
    report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")


def _run_live_suite(base_url: str, bootstrap_key: str) -> LiveContext:
    ctx = _build_live_context(base_url=base_url, bootstrap_key=bootstrap_key)
    try:
        unique = _now_suffix()
        _exercise_auth_and_space_setup(ctx, unique=unique)
        space_id = ctx.created_ids["space_id"]
        _exercise_documents(ctx, space_id)
        _exercise_pubmed(ctx, space_id)
        _exercise_chat(ctx, space_id)
        _exercise_generic_runs(ctx, space_id)
        _exercise_proposals(ctx, space_id)
        _exercise_review_queue(ctx, space_id)
        _exercise_research_init_and_state(ctx, space_id)
        _exercise_graph_explorer(ctx, space_id)
        _exercise_marrvel(ctx, space_id)
        _exercise_typed_runs(ctx, space_id)
        _exercise_schedules(ctx, space_id)
        _exercise_supervisor(ctx, space_id)
        _assert_all_operations_seen(ctx)
        _write_live_report(ctx, base_url)
        return ctx
    finally:
        ctx.client.close()


@pytest.mark.e2e
@pytest.mark.live
def test_live_artana_evidence_api_endpoint_contract() -> None:
    """Exercise the live Artana Evidence API on localhost through OpenAPI."""
    base_url = os.getenv(BASE_URL_ENV, DEFAULT_BASE_URL).rstrip("/")
    bootstrap_key = os.getenv(BOOTSTRAP_KEY_ENV, "").strip()
    if bootstrap_key == "":
        pytest.skip(
            f"Set {BOOTSTRAP_KEY_ENV} to run the live Artana Evidence API contract suite.",
        )

    ctx = _run_live_suite(base_url=base_url, bootstrap_key=bootstrap_key)

    failed = [result for result in ctx.results if result.outcome == "failed"]
    summary = {
        "passed": sum(result.outcome == "passed" for result in ctx.results),
        "blocked": sum(result.outcome == "blocked" for result in ctx.results),
        "failed": len(failed),
    }
    _emit_progress(f"live endpoint summary: {json.dumps(summary, indent=2)}")
    _emit_progress(
        f"created ids: {json.dumps(_redacted_created_ids(ctx.created_ids), indent=2)}",
    )
    assert not failed, json.dumps([asdict(result) for result in failed], indent=2)
