"""Build authoritative source identity and exact locators from stored documents."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.types.common import JSONObject, json_object_or_empty
from artana_evidence_api.types.source_provenance import (
    ClaimSourceProvenance,
    ExactEvidenceLocator,
    SourceEvidenceHandoff,
    SourceEvidenceUpstream,
    SourceIdentity,
    SourceKind,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_store import (
        HarnessDocumentRecord,
        HarnessDocumentStore,
    )
    from artana_evidence_api.proposal_store import (
        HarnessProposalDraft,
        HarnessProposalRecord,
    )

_CHAR_RANGE_RE = re.compile(
    r"(?:char(?:s|_range)?\s*[:=]\s*)?([0-9]+)\s*[-:]\s*([0-9]+)",
    re.ASCII | re.IGNORECASE,
)
_PAGE_RE = re.compile(r"\bpage\s*[:=]?\s*([0-9]+)\b", re.ASCII | re.IGNORECASE)
_TABLE_RE = re.compile(r"\b(table\s+[A-Za-z0-9.-]+)", re.ASCII | re.IGNORECASE)
_FIGURE_RE = re.compile(r"\b(fig(?:ure)?\s+[A-Za-z0-9.-]+)", re.ASCII | re.IGNORECASE)
_PARAGRAPH_BOUNDARY_RE = re.compile(r"\n\s*\n")
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


class SourceProvenanceError(ValueError):
    """A categorical source provenance failure safe to expose to review flows."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class ResolvedSourceProvenance:
    """Verified source identity and locator ready for a graph request."""

    source_identity: SourceIdentity
    evidence_locator: ExactEvidenceLocator
    source_snapshot_text: str


@dataclass(frozen=True, slots=True)
class _SourceIdentifiers:
    pmid: str | None
    pmcid: str | None
    doi: str | None
    nct_id: str | None
    clinvar_accession: str | None
    publisher_record_id: str | None
    content_source_kind: str | None


def source_evidence_handoff(
    *,
    research_space_id: UUID,
    document_id: UUID,
    provenance: ResolvedSourceProvenance,
) -> SourceEvidenceHandoff:
    """Build one authenticated, space-bound local source handoff."""

    return SourceEvidenceHandoff(
        upstream=SourceEvidenceUpstream(
            research_space_id=research_space_id,
            document_id=document_id,
            attested_at=datetime.now(UTC),
        ),
        identity=provenance.source_identity,
        canonical_text=provenance.source_snapshot_text,
        locator=provenance.evidence_locator,
    )


def load_proposal_source_document(
    *,
    document_store: HarnessDocumentStore,
    proposal: HarnessProposalRecord,
) -> HarnessDocumentRecord | None:
    """Load the proposal's original document without accepting substitutes."""

    if proposal.document_id is None:
        return None
    return document_store.get_document(
        space_id=proposal.space_id,
        document_id=proposal.document_id,
    )


def source_identity_for_document(document: HarnessDocumentRecord) -> SourceIdentity:
    """Return the authoritative identity for a stored source-text snapshot."""

    metadata = document.metadata
    source_capture = json_object_or_empty(metadata.get("source_capture"))
    identifiers = _source_identifiers(
        metadata=metadata,
        source_capture=source_capture,
    )
    source_kind, authoritative_identifier, canonical_url = _source_authority(
        identifiers=identifiers,
        metadata=metadata,
        source_capture=source_capture,
    )

    source_text_sha256 = hashlib.sha256(
        document.text_content.encode("utf-8"),
    ).hexdigest()
    return SourceIdentity(
        source_kind=source_kind,
        authoritative_identifier=authoritative_identifier,
        canonical_url=canonical_url,
        retrieved_at=_retrieved_at(document=document, source_capture=source_capture),
        content_sha256=source_text_sha256,
        version=_source_version(metadata=metadata, source_capture=source_capture),
        pmid=identifiers.pmid,
        pmcid=identifiers.pmcid,
        doi=identifiers.doi,
        nct_id=identifiers.nct_id,
        clinvar_accession=identifiers.clinvar_accession,
        publisher_record_id=identifiers.publisher_record_id,
        artifact_sha256=document.sha256,
    )


def _source_identifiers(
    *,
    metadata: JSONObject,
    source_capture: JSONObject,
) -> _SourceIdentifiers:
    pubmed = json_object_or_empty(metadata.get("pubmed"))
    selected_record = json_object_or_empty(metadata.get("selected_record"))
    normalized_record = json_object_or_empty(metadata.get("normalized_record"))
    query_payload = json_object_or_empty(source_capture.get("query_payload"))
    source_capture_key = _first_text(source_capture.get("source_key"))
    capture_external_id = _first_text(source_capture.get("external_id"))
    pmid = _first_text(pubmed.get("pmid"), query_payload.get("pmid"))
    nct_id = _first_text(
        metadata.get("nct_id"),
        selected_record.get("nct_id"),
        selected_record.get("nctId"),
        normalized_record.get("nct_id"),
        query_payload.get("nct_id"),
    )
    clinvar_accession = _first_text(
        metadata.get("clinvar_accession"),
        metadata.get("variation_id"),
        selected_record.get("clinvar_accession"),
        selected_record.get("accession"),
        selected_record.get("variation_id"),
        normalized_record.get("clinvar_accession"),
        query_payload.get("clinvar_accession"),
    )
    return _SourceIdentifiers(
        pmid=(
            capture_external_id
            if source_capture_key == "pubmed" and pmid is None
            else pmid
        ),
        pmcid=_first_text(
            pubmed.get("pmc_id"),
            pubmed.get("pmcid"),
            query_payload.get("pmc_id"),
            query_payload.get("pmcid"),
        ),
        doi=_first_text(pubmed.get("doi"), query_payload.get("doi")),
        nct_id=(
            capture_external_id
            if source_capture_key in {"clinical_trials", "clinicaltrials"}
            and nct_id is None
            else nct_id
        ),
        clinvar_accession=(
            capture_external_id
            if source_capture_key == "clinvar" and clinvar_accession is None
            else clinvar_accession
        ),
        publisher_record_id=_first_text(
            metadata.get("publisher_record_id"),
            query_payload.get("publisher_record_id"),
        ),
        content_source_kind=_first_text(
            metadata.get("content_source_kind"),
            source_capture.get("content_source_kind"),
            query_payload.get("content_source_kind"),
        ),
    )


def _source_authority(
    *,
    identifiers: _SourceIdentifiers,
    metadata: JSONObject,
    source_capture: JSONObject,
) -> tuple[SourceKind, str, str]:
    authority: tuple[SourceKind, str, str] | None = None
    if identifiers.content_source_kind == "pmc" and identifiers.pmcid is not None:
        authority = _pmc_authority(identifiers.pmcid)
    elif identifiers.pmid is not None:
        authority = (
            "pubmed",
            f"PMID:{identifiers.pmid}",
            f"https://pubmed.ncbi.nlm.nih.gov/{identifiers.pmid}/",
        )
    elif identifiers.pmcid is not None:
        authority = _pmc_authority(identifiers.pmcid)
    elif identifiers.doi is not None:
        authority = (
            "doi",
            f"DOI:{identifiers.doi}",
            f"https://doi.org/{identifiers.doi}",
        )
    elif identifiers.nct_id is not None:
        normalized_nct_id = identifiers.nct_id.upper()
        authority = (
            "clinicaltrials",
            f"NCT:{normalized_nct_id}",
            f"https://clinicaltrials.gov/study/{normalized_nct_id}",
        )
    elif identifiers.clinvar_accession is not None:
        normalized_accession = identifiers.clinvar_accession.upper()
        authority = (
            "clinvar",
            f"CLINVAR:{normalized_accession}",
            "https://www.ncbi.nlm.nih.gov/clinvar/variation/"
            f"{normalized_accession}/",
        )
    elif identifiers.publisher_record_id is not None:
        authority = _publisher_authority(
            publisher_record_id=identifiers.publisher_record_id,
            metadata=metadata,
            source_capture=source_capture,
        )
    if authority is None:
        raise SourceProvenanceError(
            "missing_authoritative_source_identifier",
            "The source document has no PMID, PMCID, DOI, NCT ID, ClinVar "
            "accession, or publisher record identifier.",
        )
    return authority


def _pmc_authority(pmcid: str) -> tuple[SourceKind, str, str]:
    normalized_pmcid = pmcid.upper()
    return (
        "pmc",
        f"PMCID:{normalized_pmcid}",
        f"https://www.ncbi.nlm.nih.gov/pmc/articles/{normalized_pmcid}/",
    )


def _publisher_authority(
    *,
    publisher_record_id: str,
    metadata: JSONObject,
    source_capture: JSONObject,
) -> tuple[SourceKind, str, str]:
    publisher_url = _first_text(
        metadata.get("publisher_url"),
        source_capture.get("locator"),
    )
    if publisher_url is None:
        raise SourceProvenanceError(
            "missing_publisher_url",
            "Publisher source identity requires an authoritative URL.",
        )
    return "publisher", f"PUBLISHER:{publisher_record_id}", publisher_url


def exact_locator_for_quote(
    *,
    source_text: str,
    exact_quote: str,
    source_content_sha256: str,
    legacy_locator: str | None = None,
    section: str | None = None,
) -> ExactEvidenceLocator:
    """Resolve one verbatim quote to an exact, hash-bound source location."""

    quote = exact_quote.strip()
    if quote == "":
        raise SourceProvenanceError(
            "missing_exact_quote",
            "An exact non-empty source quote is required.",
        )
    computed_source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    if computed_source_hash != source_content_sha256:
        raise SourceProvenanceError(
            "source_content_hash_mismatch",
            "The source text does not match the declared source snapshot hash.",
        )

    hinted_range = _hinted_char_range(legacy_locator)
    if hinted_range is not None:
        start, end = hinted_range
        if start < 0 or end > len(source_text) or source_text[start:end] != quote:
            raise SourceProvenanceError(
                "locator_hint_mismatch",
                "The supplied character range does not recover the exact quote.",
            )
    else:
        occurrences = _literal_occurrences(source_text, quote)
        if not occurrences:
            raise SourceProvenanceError(
                "quote_not_in_source_snapshot",
                "The exact quote is not present in the stored source snapshot.",
            )
        if len(occurrences) > 1:
            raise SourceProvenanceError(
                "ambiguous_repeated_quote",
                "The exact quote occurs more than once; an exact character range "
                "is required.",
            )
        start = occurrences[0]
        end = start + len(quote)

    locator_text = legacy_locator or ""
    return ExactEvidenceLocator(
        source_content_sha256=source_content_sha256,
        char_start=start,
        char_end=end,
        exact_quote=quote,
        quote_sha256=hashlib.sha256(quote.encode("utf-8")).hexdigest(),
        section=_normalized_optional_text(section),
        paragraph_index=_paragraph_index(source_text, start),
        sentence_index=_sentence_index(source_text, start),
        page_number=_matched_positive_int(_PAGE_RE, locator_text),
        table_reference=_matched_text(_TABLE_RE, locator_text),
        figure_reference=_matched_text(_FIGURE_RE, locator_text),
    )


def source_provenance_for_proposal(
    *,
    document: HarnessDocumentRecord,
    proposal: HarnessProposalRecord,
) -> ResolvedSourceProvenance:
    """Resolve authoritative, source-local provenance for one claim proposal."""

    if proposal.document_id is None:
        raise SourceProvenanceError(
            "missing_source_document",
            "The proposal does not identify the source document it was extracted from.",
        )
    if document.id != proposal.document_id or document.space_id != proposal.space_id:
        raise SourceProvenanceError(
            "source_document_binding_mismatch",
            "The supplied source document is not the proposal's original document.",
        )

    source_identity = source_identity_for_document(document)
    quote, legacy_locator = _proposal_quote_and_locator(proposal)
    section = _first_text(
        proposal.reasoning_path.get("claim_section"),
        proposal.reasoning_path.get("section"),
    )
    evidence_locator = exact_locator_for_quote(
        source_text=document.text_content,
        exact_quote=quote,
        source_content_sha256=source_identity.content_sha256,
        legacy_locator=legacy_locator,
        section=section,
    )
    return ResolvedSourceProvenance(
        source_identity=source_identity,
        evidence_locator=evidence_locator,
        source_snapshot_text=document.text_content,
    )


def bind_source_provenance_to_drafts(
    *,
    document: HarnessDocumentRecord,
    drafts: Sequence[HarnessProposalDraft],
) -> tuple[HarnessProposalDraft, ...]:
    """Freeze deterministic source provenance on document-backed claim drafts."""

    bound: list[HarnessProposalDraft] = []
    for draft in drafts:
        if draft.proposal_type != "candidate_claim":
            bound.append(draft)
            continue
        try:
            envelope = _claim_source_provenance_for_draft(
                document=document,
                draft=draft,
            )
        except SourceProvenanceError as exc:
            envelope = ClaimSourceProvenance(
                status="invalid",
                reason_code=exc.reason_code,
            )
        except ValueError:
            envelope = ClaimSourceProvenance(
                status="invalid",
                reason_code="invalid_source_identity",
            )
        bound.append(replace(draft, source_provenance=envelope))
    return tuple(bound)


def _claim_source_provenance_for_draft(
    *,
    document: HarnessDocumentRecord,
    draft: HarnessProposalDraft,
) -> ClaimSourceProvenance:
    if draft.document_id is None:
        raise SourceProvenanceError(
            "missing_source_document",
            "The claim draft does not identify its extraction document.",
        )
    if draft.document_id != document.id:
        raise SourceProvenanceError(
            "source_document_binding_mismatch",
            "The claim draft is not bound to the supplied extraction document.",
        )
    source_identity = source_identity_for_document(document)
    quote, legacy_locator = _evidence_quote_and_locator(
        evidence_bundle=draft.evidence_bundle,
        reasoning_path=draft.reasoning_path,
    )
    locator = exact_locator_for_quote(
        source_text=document.text_content,
        exact_quote=quote,
        source_content_sha256=source_identity.content_sha256,
        legacy_locator=legacy_locator,
        section=_first_text(
            draft.reasoning_path.get("claim_section"),
            draft.reasoning_path.get("section"),
        ),
    )
    return ClaimSourceProvenance(
        status="verified",
        source_identity=source_identity,
        evidence_locator=locator,
    )


def verify_persisted_source_provenance(
    *,
    document: HarnessDocumentRecord,
    proposal: HarnessProposalRecord,
) -> ResolvedSourceProvenance:
    """Verify the proposal-time envelope against its current stored document."""

    if proposal.document_id is None or proposal.document_id != document.id:
        raise SourceProvenanceError(
            "source_document_binding_mismatch",
            "The supplied source document is not the proposal's original document.",
        )
    if proposal.space_id != document.space_id:
        raise SourceProvenanceError(
            "source_document_binding_mismatch",
            "The source document and proposal belong to different research spaces.",
        )
    envelope = proposal.source_provenance
    if envelope is None:
        raise SourceProvenanceError(
            "legacy_unverified_source_provenance",
            "The proposal predates immutable source provenance.",
        )
    if envelope.status != "verified":
        raise SourceProvenanceError(
            envelope.reason_code or "unverified_source_provenance",
            "The proposal does not carry verified source provenance.",
        )
    source_identity = envelope.source_identity
    locator = envelope.evidence_locator
    if source_identity is None or locator is None:  # pragma: no cover - model invariant
        raise SourceProvenanceError(
            "malformed_source_provenance",
            "The persisted source provenance envelope is incomplete.",
        )
    try:
        current_identity = source_identity_for_document(document)
    except ValueError as exc:
        raise SourceProvenanceError(
            "source_identity_snapshot_mismatch",
            "The source identity can no longer be reconstructed.",
        ) from exc
    if current_identity != source_identity:
        raise SourceProvenanceError(
            "source_identity_snapshot_mismatch",
            "The source identity or immutable content snapshot changed after extraction.",
        )
    if document.text_content[locator.char_start : locator.char_end] != locator.exact_quote:
        raise SourceProvenanceError(
            "persisted_locator_mismatch",
            "The persisted exact locator no longer recovers its source quote.",
        )
    return ResolvedSourceProvenance(
        source_identity=source_identity,
        evidence_locator=locator,
        source_snapshot_text=document.text_content,
    )


def _proposal_quote_and_locator(
    proposal: HarnessProposalRecord,
) -> tuple[str, str | None]:
    return _evidence_quote_and_locator(
        evidence_bundle=proposal.evidence_bundle,
        reasoning_path=proposal.reasoning_path,
    )


def _evidence_quote_and_locator(
    *,
    evidence_bundle: Sequence[JSONObject],
    reasoning_path: JSONObject,
) -> tuple[str, str | None]:
    for raw_evidence in evidence_bundle:
        evidence = json_object_or_empty(raw_evidence)
        quote = _first_text(evidence.get("excerpt"), evidence.get("exact_quote"))
        if quote is not None:
            return quote, _first_text(evidence.get("locator"))
    reasoning_quote = _first_text(
        reasoning_path.get("evidence_excerpt"),
        reasoning_path.get("sentence"),
    )
    if reasoning_quote is not None:
        return reasoning_quote, _first_text(
            reasoning_path.get("evidence_locator"),
        )
    raise SourceProvenanceError(
        "missing_exact_quote",
        "The proposal has no agent-returned verbatim source quote.",
    )


def _retrieved_at(
    *,
    document: HarnessDocumentRecord,
    source_capture: JSONObject,
) -> datetime:
    raw_retrieved_at = source_capture.get("retrieved_at")
    if isinstance(raw_retrieved_at, str) and raw_retrieved_at.strip() != "":
        try:
            parsed = datetime.fromisoformat(
                raw_retrieved_at.strip().replace("Z", "+00:00"),
            )
        except ValueError as exc:
            raise SourceProvenanceError(
                "invalid_retrieved_at",
                "Source retrieval time is not a valid ISO-8601 timestamp.",
            ) from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise SourceProvenanceError(
                "invalid_retrieved_at",
                "Source retrieval time must include a timezone.",
            )
        return parsed
    created_at = document.created_at
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        return created_at.replace(tzinfo=UTC)
    return created_at.astimezone(UTC)


def _source_version(
    *,
    metadata: JSONObject,
    source_capture: JSONObject,
) -> str | None:
    provenance = json_object_or_empty(source_capture.get("provenance"))
    return _first_text(
        metadata.get("source_version"),
        metadata.get("version"),
        provenance.get("version"),
        provenance.get("etag"),
        provenance.get("last_modified"),
    )


def _hinted_char_range(locator: str | None) -> tuple[int, int] | None:
    if locator is None:
        return None
    match = _CHAR_RANGE_RE.search(locator)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def _literal_occurrences(source_text: str, quote: str) -> tuple[int, ...]:
    offsets: list[int] = []
    cursor = 0
    while True:
        offset = source_text.find(quote, cursor)
        if offset < 0:
            return tuple(offsets)
        offsets.append(offset)
        cursor = offset + 1


def _paragraph_index(source_text: str, char_start: int) -> int:
    return sum(1 for match in _PARAGRAPH_BOUNDARY_RE.finditer(source_text[:char_start]))


def _sentence_index(source_text: str, char_start: int) -> int:
    return sum(1 for match in _SENTENCE_BOUNDARY_RE.finditer(source_text[:char_start]))


def _matched_positive_int(pattern: re.Pattern[str], value: str) -> int | None:
    match = pattern.search(value)
    if match is None:
        return None
    parsed = int(match.group(1))
    return parsed if parsed > 0 else None


def _matched_text(pattern: re.Pattern[str], value: str) -> str | None:
    match = pattern.search(value)
    return match.group(1).strip() if match is not None else None


def _first_text(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip() != "":
            return value.strip()
    return None


def _normalized_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


__all__ = [
    "ResolvedSourceProvenance",
    "SourceProvenanceError",
    "exact_locator_for_quote",
    "source_identity_for_document",
    "source_evidence_handoff",
    "source_provenance_for_proposal",
]
