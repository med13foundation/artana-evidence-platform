"""Produce redacted field-path differences for provider response envelopes."""

from __future__ import annotations

from dataclasses import dataclass

from scripts.validation.provider_receipt_boundary.canonical_payload import (
    canonical_sha256,
)
from scripts.validation.provider_receipt_boundary.contracts import FieldDifference

_MISSING = object()


@dataclass(frozen=True, slots=True)
class RawDifference:
    path: str
    difference: str
    creation: object
    retrieval: object

    @property
    def creation_missing(self) -> bool:
        return self.creation is _MISSING

    @property
    def retrieval_missing(self) -> bool:
        return self.retrieval is _MISSING

    def redacted(self, *, allowlisted: bool, rationale: str | None) -> FieldDifference:
        return FieldDifference(
            path=self.path,
            difference=self.difference,
            creation_sha256=canonical_sha256(_redactable(self.creation)),
            retrieval_sha256=canonical_sha256(_redactable(self.retrieval)),
            allowlisted=allowlisted,
            rationale=rationale,
        )


def structural_diff(creation: object, retrieval: object) -> tuple[RawDifference, ...]:
    differences: list[RawDifference] = []
    _walk("$", creation, retrieval, differences)
    return tuple(differences)


def _walk(
    path: str,
    creation: object,
    retrieval: object,
    differences: list[RawDifference],
) -> None:
    if isinstance(creation, dict) and isinstance(retrieval, dict):
        for key in sorted(set(creation) | set(retrieval)):
            _walk(
                f"{path}.{key}",
                creation.get(key, _MISSING),
                retrieval.get(key, _MISSING),
                differences,
            )
        return
    if isinstance(creation, list) and isinstance(retrieval, list):
        for index in range(max(len(creation), len(retrieval))):
            left = creation[index] if index < len(creation) else _MISSING
            right = retrieval[index] if index < len(retrieval) else _MISSING
            _walk(f"{path}[{index}]", left, right, differences)
        return
    if creation != retrieval:
        differences.append(
            RawDifference(
                path=path,
                difference=_difference_kind(creation, retrieval),
                creation=creation,
                retrieval=retrieval,
            )
        )


def _difference_kind(creation: object, retrieval: object) -> str:
    if creation is _MISSING:
        return "ADDED_ON_RETRIEVAL"
    if retrieval is _MISSING:
        return "OMITTED_ON_RETRIEVAL"
    return "VALUE_CHANGED"


def _redactable(value: object) -> object:
    return {"presence": "MISSING"} if value is _MISSING else value


__all__ = ["RawDifference", "structural_diff"]
