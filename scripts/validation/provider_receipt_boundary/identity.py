"""Extract and compare immutable provider response identity."""

from __future__ import annotations

from scripts.validation.provider_receipt_boundary.contracts import ReceiptIdentity


class ReceiptIdentityError(ValueError):
    """Provider response identity is missing, malformed, or changed."""


def extract_receipt_identity(
    response: dict[str, object], *, expected_model: str
) -> ReceiptIdentity:
    response_id = _string(response, "id")
    object_type = _string(response, "object")
    if object_type != "response":
        raise ReceiptIdentityError("provider object type is not response")
    model = _string(response, "model")
    if model != expected_model:
        raise ReceiptIdentityError("returned model differs from requested model")
    status = _string(response, "status")
    if status != "completed" or response.get("error") is not None:
        raise ReceiptIdentityError("provider response is not completed without error")
    if response.get("incomplete_details") is not None:
        raise ReceiptIdentityError("provider response has incomplete details")
    created_at = response.get("created_at")
    if not isinstance(created_at, int | float) or created_at <= 0:
        raise ReceiptIdentityError("provider creation timestamp is invalid")
    output = response.get("output")
    if not isinstance(output, list) or not output:
        raise ReceiptIdentityError("provider output identity is absent")
    output_items: list[tuple[str, str]] = []
    for item in output:
        if not isinstance(item, dict):
            raise ReceiptIdentityError("provider output identity is malformed")
        output_items.append((_string(item, "type"), _string(item, "id")))
    return ReceiptIdentity(
        response_id=response_id,
        object_type=object_type,
        created_at=float(created_at),
        model=model,
        status=status,
        output_items=tuple(output_items),
    )


def require_same_identity(
    creation: ReceiptIdentity, retrieval: ReceiptIdentity
) -> ReceiptIdentity:
    if creation != retrieval:
        raise ReceiptIdentityError("creation and retrieval identities differ")
    return creation


def _string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ReceiptIdentityError(f"provider {key} is missing")
    return value


__all__ = [
    "ReceiptIdentityError",
    "extract_receipt_identity",
    "require_same_identity",
]
