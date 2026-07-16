"""Typed source identity and exact evidence-locator contracts."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SourceKind = Literal[
    "pubmed",
    "pmc",
    "doi",
    "clinicaltrials",
    "clinvar",
    "publisher",
]
SourceProvenanceStatus = Literal["verified", "unverified", "invalid"]
SourceProvenanceReasonCode = Literal[
    "verified",
    "legacy_evidence_without_typed_provenance",
    "missing_source_document_id",
    "missing_source_identity",
    "missing_evidence_locator",
    "missing_source_snapshot_text",
    "source_attestation_capability_missing",
    "source_attestation_service_missing",
    "source_attestation_service_mismatch",
    "upstream_document_id_mismatch",
    "upstream_research_space_mismatch",
    "authoritative_identifier_invalid",
    "authoritative_identifier_mismatch",
    "source_identifier_field_missing",
    "source_identifier_field_mismatch",
    "source_version_unverifiable",
    "source_version_mismatch",
    "source_content_unavailable",
    "source_content_hash_mismatch",
    "identity_locator_hash_mismatch",
    "evidence_bounds_invalid",
    "evidence_quote_mismatch",
    "quote_hash_mismatch",
]
ClaimEvidenceProvenanceStatus = Literal[
    "VERIFIED",
    "UNVERIFIED",
    "INVALID",
    "LEGACY_UNVERIFIED",
]

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_PMID_RE = re.compile(r"^[0-9]+$", re.ASCII)
_PMCID_RE = re.compile(r"^PMC[0-9]+$", re.ASCII | re.IGNORECASE)
_DOI_RE = re.compile(r"^10\.[0-9]{4,9}/\S+$", re.ASCII | re.IGNORECASE)
_NCT_RE = re.compile(r"^NCT[0-9]{8}$", re.ASCII | re.IGNORECASE)
_CLINVAR_RE = re.compile(
    r"^(?:[0-9]+|(?:RCV|SCV|VCV)[0-9]+(?:\.[0-9]+)?)$",
    re.ASCII | re.IGNORECASE,
)


class SourceIdentity(BaseModel):
    """Canonical identity snapshot for one authoritative source record."""

    model_config = ConfigDict(strict=False, extra="forbid", frozen=True)

    source_kind: SourceKind
    authoritative_identifier: str = Field(..., min_length=1, max_length=512)
    canonical_url: str = Field(..., min_length=1, max_length=2048)
    retrieved_at: datetime
    content_sha256: str = Field(..., pattern=_SHA256_PATTERN)
    version: str | None = Field(default=None, max_length=255)
    pmid: str | None = Field(default=None, max_length=32)
    pmcid: str | None = Field(default=None, max_length=32)
    doi: str | None = Field(default=None, max_length=512)
    nct_id: str | None = Field(default=None, max_length=32)
    clinvar_accession: str | None = Field(default=None, max_length=64)
    publisher_record_id: str | None = Field(default=None, max_length=512)
    artifact_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)

    @field_validator("canonical_url")
    @classmethod
    def _validate_canonical_url(cls, value: str) -> str:
        normalized = value.strip()
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            msg = "canonical_url must be an absolute HTTP or HTTPS URL"
            raise ValueError(msg)
        return normalized

    @field_validator("retrieved_at")
    @classmethod
    def _validate_retrieved_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            msg = "retrieved_at must be timezone-aware"
            raise ValueError(msg)
        return value

    @field_validator("content_sha256", "artifact_sha256")
    @classmethod
    def _normalize_sha256(cls, value: str | None) -> str | None:
        return value.strip().lower() if value is not None else None

    @field_validator("authoritative_identifier")
    @classmethod
    def _normalize_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator(
        "version",
        "pmid",
        "pmcid",
        "doi",
        "nct_id",
        "clinvar_accession",
        "publisher_record_id",
    )
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def _validate_authority_binding(self) -> SourceIdentity:
        expected = _expected_authoritative_identifier(self)
        if self.authoritative_identifier.casefold() != expected.casefold():
            msg = (
                "authoritative_identifier does not match the identifier required "
                f"for source_kind={self.source_kind}"
            )
            raise ValueError(msg)
        expected_url = _expected_canonical_url(self)
        if expected_url is not None and self.canonical_url != expected_url:
            msg = (
                "canonical_url does not match the authoritative source identifier "
                f"for source_kind={self.source_kind}"
            )
            raise ValueError(msg)
        return self


class ExactEvidenceLocator(BaseModel):
    """Exact character-span locator against a hashed source snapshot."""

    model_config = ConfigDict(strict=False, extra="forbid", frozen=True)

    source_content_sha256: str = Field(..., pattern=_SHA256_PATTERN)
    char_start: int = Field(..., ge=0)
    char_end: int
    exact_quote: str = Field(..., min_length=1, max_length=12_000)
    quote_sha256: str = Field(..., pattern=_SHA256_PATTERN)
    section: str | None = Field(default=None, max_length=255)
    paragraph_index: int | None = Field(default=None, ge=0)
    sentence_index: int | None = Field(default=None, ge=0)
    page_number: int | None = Field(default=None, ge=1)
    table_reference: str | None = Field(default=None, max_length=255)
    figure_reference: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _validate_character_range(self) -> ExactEvidenceLocator:
        if self.char_end <= self.char_start:
            msg = "char_end must be greater than char_start"
            raise ValueError(msg)
        if self.char_end - self.char_start != len(self.exact_quote):
            msg = "locator character range must equal the exact quote length"
            raise ValueError(msg)
        expected_quote_hash = hashlib.sha256(
            self.exact_quote.encode("utf-8"),
        ).hexdigest()
        if self.quote_sha256 != expected_quote_hash:
            msg = "quote_sha256 does not match exact_quote"
            raise ValueError(msg)
        return self


class SourceEvidenceUpstream(BaseModel):
    """Authenticated upstream document identity for one evidence handoff."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    service: Literal["artana_evidence_api"] = "artana_evidence_api"
    research_space_id: UUID
    document_id: UUID
    attested_at: datetime

    @field_validator("attested_at")
    @classmethod
    def _validate_attested_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            msg = "attested_at must be timezone-aware"
            raise ValueError(msg)
        return value


class SourceEvidenceHandoff(BaseModel):
    """All-or-nothing local source proof accepted by Graph."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    upstream: SourceEvidenceUpstream
    identity: SourceIdentity
    canonical_text: str = Field(..., min_length=1)
    locator: ExactEvidenceLocator

    @model_validator(mode="after")
    def _validate_snapshot_binding(self) -> SourceEvidenceHandoff:
        content_hash = hashlib.sha256(self.canonical_text.encode("utf-8")).hexdigest()
        if content_hash != self.identity.content_sha256:
            msg = "canonical_text does not match source identity content_sha256"
            raise ValueError(msg)
        if self.locator.source_content_sha256 != content_hash:
            msg = "locator does not match canonical source content"
            raise ValueError(msg)
        exact_slice = self.canonical_text[
            self.locator.char_start : self.locator.char_end
        ]
        if exact_slice != self.locator.exact_quote:
            msg = "locator does not recover exact_quote from canonical_text"
            raise ValueError(msg)
        return self


def _expected_authoritative_identifier(identity: SourceIdentity) -> str:
    if identity.source_kind == "pubmed":
        return f"PMID:{_require_identifier(identity.pmid, 'pmid', _PMID_RE)}"
    if identity.source_kind == "pmc":
        value = _require_identifier(identity.pmcid, "pmcid", _PMCID_RE).upper()
        return f"PMCID:{value}"
    if identity.source_kind == "doi":
        return f"DOI:{_require_identifier(identity.doi, 'doi', _DOI_RE)}"
    if identity.source_kind == "clinicaltrials":
        value = _require_identifier(identity.nct_id, "nct_id", _NCT_RE).upper()
        return f"NCT:{value}"
    if identity.source_kind == "clinvar":
        value = _require_identifier(
            identity.clinvar_accession,
            "clinvar_accession",
            _CLINVAR_RE,
        ).upper()
        return f"CLINVAR:{value}"
    return f"PUBLISHER:{_require_non_empty(identity.publisher_record_id, 'publisher_record_id')}"


def _expected_canonical_url(identity: SourceIdentity) -> str | None:
    if identity.source_kind == "pubmed":
        return f"https://pubmed.ncbi.nlm.nih.gov/{identity.pmid}/"
    if identity.source_kind == "pmc":
        return (
            "https://www.ncbi.nlm.nih.gov/pmc/articles/"
            f"{identity.pmcid.upper() if identity.pmcid is not None else None}/"
        )
    if identity.source_kind == "doi":
        return f"https://doi.org/{identity.doi}"
    if identity.source_kind == "clinicaltrials":
        return (
            "https://clinicaltrials.gov/study/"
            f"{identity.nct_id.upper() if identity.nct_id is not None else None}"
        )
    if identity.source_kind == "clinvar":
        return (
            "https://www.ncbi.nlm.nih.gov/clinvar/variation/"
            f"{identity.clinvar_accession.upper() if identity.clinvar_accession is not None else None}/"
        )
    return None


def _require_identifier(
    value: str | None,
    field_name: str,
    pattern: re.Pattern[str],
) -> str:
    normalized = _require_non_empty(value, field_name)
    if pattern.fullmatch(normalized) is None:
        msg = f"{field_name} is not valid for the selected source kind"
        raise ValueError(msg)
    return normalized


def _require_non_empty(value: str | None, field_name: str) -> str:
    if value is None or value.strip() == "":
        msg = f"{field_name} is required for the selected source kind"
        raise ValueError(msg)
    return value.strip()


class SourceProvenanceVerification(BaseModel):
    """Server-computed source provenance verdict and stable reason codes."""

    model_config = ConfigDict(frozen=True)

    status: SourceProvenanceStatus
    reason_codes: tuple[SourceProvenanceReasonCode, ...]

    @property
    def is_verified(self) -> bool:
        return self.status == "verified"


__all__ = [
    "ExactEvidenceLocator",
    "ClaimEvidenceProvenanceStatus",
    "SourceIdentity",
    "SourceEvidenceHandoff",
    "SourceEvidenceUpstream",
    "SourceKind",
    "SourceProvenanceReasonCode",
    "SourceProvenanceStatus",
    "SourceProvenanceVerification",
]
