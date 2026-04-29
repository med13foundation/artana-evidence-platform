"""Shared helpers for public direct-source route plugins."""

from __future__ import annotations

from typing import TypeVar
from uuid import UUID

from artana_evidence_api.direct_source_search import DirectSourceSearchStore
from artana_evidence_api.source_route_errors import validation_error_text
from artana_evidence_api.types.common import JSONObject, json_object_or_empty
from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ValidationError

_RequestT = TypeVar("_RequestT", bound=BaseModel)
_GatewayT = TypeVar("_GatewayT")


def parse_source_search_payload(
    payload: JSONObject,
    request_model: type[_RequestT],
) -> _RequestT:
    """Validate a generic JSON payload against a typed source request model."""

    try:
        return request_model.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=validation_error_text(exc),
        ) from exc


def stored_source_search_payload(
    *,
    space_id: UUID,
    source_key: str,
    search_id: UUID,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    """Return a stored direct-source search payload or raise a route error."""

    stored_result = direct_source_search_store.get(
        space_id=space_id,
        source_key=source_key,
        search_id=search_id,
    )
    if stored_result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source search was not found for this space and source.",
        )
    return source_result_payload(stored_result)


def source_result_payload(result: object) -> JSONObject:
    """Encode a direct-source search result into a JSON object."""

    return json_object_or_empty(jsonable_encoder(result))


def require_gateway(
    gateway: _GatewayT | None,
    *,
    unavailable_detail: str,
) -> _GatewayT:
    """Require a source gateway dependency for public route execution."""

    if gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=unavailable_detail,
        )
    return gateway


def gateway_unavailable(exc: RuntimeError) -> HTTPException:
    """Translate source gateway runtime failures into public route errors."""

    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=str(exc),
    )


__all__ = [
    "gateway_unavailable",
    "parse_source_search_payload",
    "require_gateway",
    "source_result_payload",
    "stored_source_search_payload",
]
