"""Graph audit HTTP helpers for live evidence session audits."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from scripts.full_ai_real_space_canary.utils import (
    _dict_value,
    _list_of_dicts,
    _maybe_string,
    _request_json,
)
from scripts.live_evidence_session_audit.constants import _HTTP_OK
from scripts.live_evidence_session_audit.values import _int_value, _string_list

if TYPE_CHECKING:
    import httpx
    from artana_evidence_api.types.common import JSONObject


def _graph_claim_total(
    *,
    client: httpx.Client,
    headers: dict[str, str],
    space_id: str,
    request_timeout_seconds: float,
) -> int:
    payload = _request_json(
        client=client,
        method="GET",
        path=f"/v2/spaces/{space_id}/evidence-map/claims?offset=0&limit=1",
        headers=headers,
        timeout_seconds=request_timeout_seconds,
    )
    return _int_value(payload.get("total"))


def _list_all_graph_claims(
    *,
    client: httpx.Client,
    headers: dict[str, str],
    space_id: str,
    request_timeout_seconds: float,
    limit: int = 200,
) -> JSONObject:
    all_claims: list[JSONObject] = []
    offset = 0
    total = 0
    while True:
        payload = _request_json(
            client=client,
            method="GET",
            path=(
                f"/v2/spaces/{space_id}/evidence-map/claims?"
                f"offset={offset}&limit={limit}"
            ),
            headers=headers,
            timeout_seconds=request_timeout_seconds,
        )
        total = _int_value(payload.get("total"))
        claims = _list_of_dicts(payload.get("claims"))
        all_claims.extend(claims)
        offset += len(claims)
        if not claims or offset >= total:
            break
    return {"claims": all_claims, "total": total, "offset": 0, "limit": limit}


def _locate_target_claim(
    *,
    claims: Sequence[JSONObject],
    graph_claim_id: str | None,
    expected_source_document_ref: str | None,
) -> JSONObject | None:
    if graph_claim_id is not None:
        for claim in claims:
            if _maybe_string(claim.get("id")) == graph_claim_id:
                return dict(claim)
    if expected_source_document_ref is not None:
        for claim in claims:
            if (
                _maybe_string(claim.get("source_document_ref"))
                == expected_source_document_ref
            ):
                return dict(claim)
    return None


def _graph_audit_errors(
    graph_audit: JSONObject | None,
    *,
    require_graph_activity: bool,
) -> list[str]:
    payload = _dict_value(graph_audit)
    errors = _string_list(payload.get("errors"))
    if require_graph_activity:
        if _int_value(payload.get("claim_delta")) <= 0:
            errors.append("No graph claim delta was observed after promotion.")
        if payload.get("target_claim_found") is not True:
            errors.append("Promoted claim was not visible through graph-explorer.")
        if _int_value(payload.get("evidence_total")) <= 0:
            errors.append("Promoted claim did not expose any claim_evidence rows.")
    return errors


def _step_errors(step_payload: JSONObject | None) -> list[str]:
    payload = _dict_value(step_payload)
    return _string_list(payload.get("errors"))


def _request_json_with_status(  # noqa: PLR0913
    *,
    client: httpx.Client,
    method: str,
    path: str,
    headers: dict[str, str],
    json_body: JSONObject | None = None,
    acceptable_statuses: tuple[int, ...] = (_HTTP_OK,),
    timeout_seconds: float | None = None,
) -> tuple[int, JSONObject]:
    response = client.request(
        method=method,
        url=path,
        headers=headers,
        json=json_body,
        timeout=timeout_seconds,
    )
    if response.status_code not in acceptable_statuses:
        detail = response.text.strip()
        raise RuntimeError(
            f"{method} {path} returned HTTP {response.status_code}: {detail}",
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError(f"{method} {path} returned a non-object JSON payload")
    return response.status_code, dict(payload)


__all__ = [
    "_graph_audit_errors",
    "_graph_claim_total",
    "_list_all_graph_claims",
    "_locate_target_claim",
    "_request_json_with_status",
    "_step_errors",
]
