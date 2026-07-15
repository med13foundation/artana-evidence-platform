"""Typed authoritative source identity and exact evidence locator contracts."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse
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

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_PMID_RE = re.compile(r"^[0-9]+$", re.ASCII)
_PMCID_RE = re.compile(r"^PMC[0-9]+$", re.ASCII | re.IGNORECASE)
_DOI_RE = re.compile(r"^10\.[0-9]{4,9}/\S+$", re.ASCII | re.IGNORECASE)
_NCT_RE = re.compile(r"^NCT[0-9]{8}$", re.ASCII | re.IGNORECASE)
_CLINVAR_RE = re.compile(
    r"^(?:[0-9]+|(?:RCV|SCV|VCV)[0-9]+(?:\.[0-9]+)?)$",
    re.ASCII | re.IGNORECASE,
)


class SourceIdentity(BaseModel):
    """Authoritative identity for one immutable source-text snapshot."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_kind: SourceKind
    authoritative_identifier: str = Field(..., min_length=1, max_length=512)
    canonical_url: str = Field(..., min_length=1, max_length=2048)
    retrieved_at: datetime
    content_sha256: str = Field(..., min_length=64, max_length=64)
    version: str | None = Field(default=None, max_length=255)
    pmid: str | None = Field(default=None, max_length=32)
    pmcid: str | None = Field(default=None, max_length=32)
    doi: str | None = Field(default=None, max_length=512)
    nct_id: str | None = Field(default=None, max_length=32)
    clinvar_accession: str | None = Field(default=None, max_length=64)
    publisher_record_id: str | None = Field(default=None, max_length=512)
    artifact_sha256: str | None = Field(default=None, min_length=64, max_length=64)

    @field_validator("content_sha256", "artifact_sha256")
    @classmethod
    def _validate_sha256(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if _SHA256_RE.fullmatch(normalized) is None:
            msg = "SHA-256 values must be 64 lowercase ASCII hexadecimal characters"
            raise ValueError(msg)
        return normalized

    @field_validator("canonical_url")
    @classmethod
    def _validate_canonical_url(cls, value: str) -> str:
        normalized = value.strip()
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or parsed.netloc == "":
            msg = "canonical_url must be an absolute HTTP(S) URL"
            raise ValueError(msg)
        return normalized

    @field_validator("retrieved_at")
    @classmethod
    def _validate_retrieved_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            msg = "retrieved_at must include a timezone"
            raise ValueError(msg)
        return value

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
    """Exact source-local quote location bound to one source snapshot hash."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_content_sha256: str = Field(..., min_length=64, max_length=64)
    char_start: int = Field(..., ge=0)
    char_end: int = Field(..., gt=0)
    exact_quote: str = Field(..., min_length=1, max_length=12_000)
    quote_sha256: str = Field(..., min_length=64, max_length=64)
    section: str | None = Field(default=None, max_length=255)
    paragraph_index: int | None = Field(default=None, ge=0)
    sentence_index: int | None = Field(default=None, ge=0)
    page_number: int | None = Field(default=None, ge=1)
    table_reference: str | None = Field(default=None, max_length=255)
    figure_reference: str | None = Field(default=None, max_length=255)

    @field_validator("source_content_sha256", "quote_sha256")
    @classmethod
    def _validate_sha256(cls, value: str) -> str:
        normalized = value.strip().lower()
        if _SHA256_RE.fullmatch(normalized) is None:
            msg = "SHA-256 values must be 64 lowercase ASCII hexadecimal characters"
            raise ValueError(msg)
        return normalized

    @field_validator(
        "exact_quote",
        "section",
        "table_reference",
        "figure_reference",
    )
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def _validate_quote_binding(self) -> ExactEvidenceLocator:
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


class ClaimSourceProvenance(BaseModel):
    """Frozen proposal-time source envelope; legacy absence is unverified."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: SourceProvenanceStatus
    source_identity: SourceIdentity | None = None
    evidence_locator: ExactEvidenceLocator | None = None
    reason_code: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def _validate_status_contract(self) -> ClaimSourceProvenance:
        if self.status == "verified":
            if self.source_identity is None or self.evidence_locator is None:
                msg = "verified provenance requires source identity and exact locator"
                raise ValueError(msg)
            if (
                self.source_identity.content_sha256
                != self.evidence_locator.source_content_sha256
            ):
                msg = "source identity and locator must bind to the same snapshot"
                raise ValueError(msg)
            if self.reason_code is not None:
                msg = "verified provenance cannot include a failure reason"
                raise ValueError(msg)
        elif self.reason_code is None:
            msg = "unverified or invalid provenance requires a categorical reason"
            raise ValueError(msg)
        return self


class SourceEvidenceUpstream(BaseModel):
    """Evidence API document attestation bound to one graph research space."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    service: Literal["artana_evidence_api"] = "artana_evidence_api"
    research_space_id: UUID
    document_id: UUID
    attested_at: datetime

    @field_validator("attested_at")
    @classmethod
    def _validate_attested_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            msg = "attested_at must include a timezone"
            raise ValueError(msg)
        return value


class SourceEvidenceHandoff(BaseModel):
    """All-or-nothing local source proof sent to the Graph service."""

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
        pmid = _require_identifier(identity.pmid, "pmid", _PMID_RE)
        return f"PMID:{pmid}"
    if identity.source_kind == "pmc":
        pmcid = _require_identifier(identity.pmcid, "pmcid", _PMCID_RE).upper()
        return f"PMCID:{pmcid}"
    if identity.source_kind == "doi":
        doi = _require_identifier(identity.doi, "doi", _DOI_RE)
        return f"DOI:{doi}"
    if identity.source_kind == "clinicaltrials":
        nct_id = _require_identifier(identity.nct_id, "nct_id", _NCT_RE).upper()
        return f"NCT:{nct_id}"
    if identity.source_kind == "clinvar":
        accession = _require_identifier(
            identity.clinvar_accession,
            "clinvar_accession",
            _CLINVAR_RE,
        ).upper()
        return f"CLINVAR:{accession}"
    publisher_record_id = _require_non_empty(
        identity.publisher_record_id,
        "publisher_record_id",
    )
    return f"PUBLISHER:{publisher_record_id}"


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


__all__ = [
    "ClaimSourceProvenance",
    "ExactEvidenceLocator",
    "SourceIdentity",
    "SourceEvidenceHandoff",
    "SourceEvidenceUpstream",
    "SourceKind",
    "SourceProvenanceStatus",
]
