"""Tests for consistent error response format (issue #164).

Every error response must have ``{"detail": "<string>"}``.
"""

from __future__ import annotations

from uuid import UUID

from artana_evidence_api.app import create_app
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel


class _Body(BaseModel):
    name: str
    count: int


class _SingleFieldBody(BaseModel):
    objective: str


class _TwoFieldBody(BaseModel):
    title: str
    text: str


# ---------------------------------------------------------------------------
# Minimal app that re-uses the same exception handlers registered by
# ``create_app`` without pulling in every dependency.
# ---------------------------------------------------------------------------


def _build_error_test_app() -> FastAPI:
    """Return a tiny FastAPI app with the production exception handlers."""
    app = create_app()

    # Add test-only routes that trigger each error shape.

    @app.get("/test/string-detail")
    def _string_detail() -> None:
        raise HTTPException(status_code=400, detail="bad request")

    @app.get("/test/dict-detail-with-message")
    def _dict_detail_message() -> None:
        raise HTTPException(
            status_code=400,
            detail={"message": "something went wrong", "code": "ERR"},
        )

    @app.get("/test/dict-detail-no-message")
    def _dict_detail_no_message() -> None:
        raise HTTPException(
            status_code=400,
            detail={"foo": "bar"},
        )

    @app.get("/test/list-detail")
    def _list_detail() -> None:
        raise HTTPException(status_code=400, detail=["err1", "err2"])

    @app.post("/test/validation")
    def _validation(body: _Body) -> _Body:
        return body

    @app.post("/test/single-field-validation")
    def _single_field_validation(
        body: _SingleFieldBody,
    ) -> _SingleFieldBody:
        return body

    @app.post("/test/two-field-validation")
    def _two_field_validation(
        body: _TwoFieldBody,
    ) -> _TwoFieldBody:
        return body

    @app.get("/test/path-validation/{item_id}")
    def _path_validation(item_id: UUID) -> dict[str, str]:
        return {"item_id": str(item_id)}

    @app.get("/test/not-found")
    def _not_found() -> None:
        raise HTTPException(status_code=404, detail="not found")

    return app


_client = TestClient(_build_error_test_app(), raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _assert_error_detail(
    body: dict[str, object],
    *,
    detail: str,
) -> None:
    assert body["detail"] == detail
    assert isinstance(body.get("request_id"), str)
    assert body["request_id"] != ""


def test_string_detail_stays_string() -> None:
    resp = _client.get("/test/string-detail")
    assert resp.status_code == 400
    body = resp.json()
    _assert_error_detail(body, detail="bad request")


def test_dict_detail_extracts_message() -> None:
    resp = _client.get("/test/dict-detail-with-message")
    assert resp.status_code == 400
    body = resp.json()
    assert isinstance(body["detail"], str)
    assert body["detail"] == "something went wrong"


def test_dict_detail_without_message_key_stringifies() -> None:
    resp = _client.get("/test/dict-detail-no-message")
    assert resp.status_code == 400
    body = resp.json()
    assert isinstance(body["detail"], str)
    # Falls back to str(dict)
    assert "foo" in body["detail"]


def test_list_detail_joins_items() -> None:
    resp = _client.get("/test/list-detail")
    assert resp.status_code == 400
    body = resp.json()
    assert isinstance(body["detail"], str)
    assert "err1" in body["detail"]
    assert "err2" in body["detail"]


def test_validation_error_returns_string_detail() -> None:
    resp = _client.post(
        "/test/validation",
        json={"wrong_field": "value"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert isinstance(body["detail"], str)
    # Should contain human-readable validation info
    assert "required" in body["detail"].lower()


def test_single_validation_error_includes_field_location() -> None:
    resp = _client.post(
        "/test/single-field-validation",
        json={},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"] == "body -> objective: Field required"


def test_multiple_validation_errors_preserve_input_order() -> None:
    resp = _client.post(
        "/test/two-field-validation",
        json={},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"] == (
        "body -> title: Field required; body -> text: Field required"
    )


def test_path_validation_errors_are_deduplicated() -> None:
    resp = _client.get("/test/path-validation/xyz")
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"].startswith("path -> item_id: Input should be a valid UUID")
    assert body["detail"].count("path -> item_id:") == 1
    assert "; " not in body["detail"]


def test_not_found_preserves_status_code() -> None:
    resp = _client.get("/test/not-found")
    assert resp.status_code == 404
    body = resp.json()
    _assert_error_detail(body, detail="not found")
