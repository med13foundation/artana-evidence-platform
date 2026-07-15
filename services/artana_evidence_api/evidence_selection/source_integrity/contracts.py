"""Categorical contracts for authoritative source-integrity findings."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Literal

from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class SourceIdentityStatus(StrEnum):
    """Whether the authority returned the record that was requested."""

    MATCHED = "matched"
    MISMATCHED = "mismatched"
    UNRESOLVED = "unresolved"


class SourceIntegrityStatus(StrEnum):
    """Categorical publication-integrity status reported by an authority."""

    CLEAR = "clear"
    CORRECTION_REVIEW = "correction_review"
    EXPRESSION_OF_CONCERN = "expression_of_concern"
    RETRACTED = "retracted"
    UNRESOLVED = "unresolved"


class SourceValidationRelation(BaseModel):
    """One authority-provided relationship to another source record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    relation_type: str = Field(min_length=1)
    target_id: str | None = None
    citation: str = Field(min_length=1)


class AuthoritativeSourceValidation(BaseModel):
    """Typed, categorical source facts used by deterministic safety policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["authoritative_source_validation.v1"]
    authority: str = Field(min_length=1)
    validation_method: str = Field(min_length=1)
    authority_record_id: str | None = None
    source_identity: SourceIdentityStatus
    source_integrity: SourceIntegrityStatus
    explanation: str = Field(min_length=1)
    relations: tuple[SourceValidationRelation, ...] = ()

    def to_json(self) -> JSONObject:
        """Serialize the validated contract at the source-record boundary."""

        return self.model_dump(mode="json")


def parse_authoritative_source_validation(
    raw_validation: object,
) -> AuthoritativeSourceValidation | None:
    """Return a strict validation contract or ``None`` for untrusted payloads."""

    if not isinstance(raw_validation, Mapping):
        return None
    try:
        return AuthoritativeSourceValidation.model_validate(raw_validation)
    except ValidationError:
        return None


__all__ = [
    "AuthoritativeSourceValidation",
    "SourceIdentityStatus",
    "SourceIntegrityStatus",
    "SourceValidationRelation",
    "parse_authoritative_source_validation",
]
