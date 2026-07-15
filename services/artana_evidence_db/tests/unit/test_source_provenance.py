"""Deterministic and persistence tests for authoritative source provenance."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from artana_evidence_db._relation_repository_shared import _source_family_key
from artana_evidence_db.kernel_claim_models import ClaimEvidenceModel
from artana_evidence_db.source_provenance.eligibility import (
    ClaimEvidenceEligibilityService,
)
from artana_evidence_db.source_provenance.models import (
    ExactEvidenceLocator,
    SourceEvidenceHandoff,
    SourceEvidenceUpstream,
    SourceIdentity,
)
from artana_evidence_db.source_provenance.service import SourceProvenanceService
from artana_evidence_db.source_provenance.snapshot_repository import (
    SourceEvidenceSnapshotConflictError,
    SqlAlchemySourceEvidenceSnapshotRepository,
)
from artana_evidence_db.source_provenance.verifier import verify_source_provenance
from artana_evidence_db.space_models import GraphSpaceModel
from pydantic import ValidationError
from sqlalchemy.orm import Session


def test_verified_unicode_locator_round_trips_through_immutable_snapshot(
    db_session: Session,
) -> None:
    space_id = _seed_space(db_session)
    source_document_id = uuid4()
    text = "Résumé. MED13 β-variant supports cardiomyopathy. End."
    quote = "MED13 β-variant supports cardiomyopathy."
    start = text.index(quote)
    identity = _identity(text=text)
    locator = _locator(text=text, quote=quote, start=start)

    submission = SourceProvenanceService(db_session).verify_and_snapshot(
        research_space_id=space_id,
        source_document_id=source_document_id,
        source_evidence=_handoff(
            space_id=space_id,
            document_id=source_document_id,
            text=text,
            identity=identity,
            locator=locator,
        ),
        source_attestation_capability=True,
        authenticated_attestation_service="artana_evidence_api",
    )

    assert submission.verification.status == "verified"
    assert submission.snapshot is not None
    assert submission.snapshot.canonical_text == text
    assert submission.snapshot.source_identity == identity
    assert submission.snapshot.upstream_service == "artana_evidence_api"
    assert submission.snapshot.upstream_research_space_id == space_id
    assert submission.snapshot.upstream_document_id == source_document_id


def test_valid_looking_authority_without_service_attestation_is_unverified() -> None:
    text = "MED13 is associated with cardiomyopathy."
    identity = _identity(text=text)
    locator = _locator(text=text, quote=text, start=0)
    space_id = uuid4()
    document_id = uuid4()

    verdict = verify_source_provenance(
        research_space_id=space_id,
        source_document_id=document_id,
        source_evidence=_handoff(
            space_id=space_id,
            document_id=document_id,
            text=text,
            identity=identity,
            locator=locator,
        ),
        source_attestation_capability=False,
        authenticated_attestation_service=None,
    )

    assert verdict.status == "unverified"
    assert verdict.reason_codes == ("source_attestation_capability_missing",)


@pytest.mark.parametrize(
    ("mutated_text", "expected_reason"),
    [
        ("Changed source text.", "source_content_hash_mismatch"),
        ("xMED13 is associated with cardiomyopathy.", "source_content_hash_mismatch"),
    ],
)
def test_mutated_source_snapshot_fails_closed(
    mutated_text: str,
    expected_reason: str,
) -> None:
    original = "MED13 is associated with cardiomyopathy."
    space_id = uuid4()
    document_id = uuid4()
    handoff = _handoff(
        space_id=space_id,
        document_id=document_id,
        text=original,
    ).model_copy(update={"canonical_text": mutated_text})
    verdict = verify_source_provenance(
        research_space_id=space_id,
        source_document_id=document_id,
        source_evidence=handoff,
        source_attestation_capability=True,
        authenticated_attestation_service="artana_evidence_api",
    )

    assert verdict.status == "invalid"
    assert verdict.reason_codes == (expected_reason,)


def test_repeated_quote_requires_the_persisted_exact_offset() -> None:
    quote = "Same evidence."
    text = f"{quote} Different. {quote}"
    second_start = text.rindex(quote)
    identity = _identity(text=text)
    space_id = uuid4()
    document_id = uuid4()

    valid = verify_source_provenance(
        research_space_id=space_id,
        source_document_id=document_id,
        source_evidence=_handoff(
            space_id=space_id,
            document_id=document_id,
            text=text,
            identity=identity,
            locator=_locator(text=text, quote=quote, start=second_start),
        ),
        source_attestation_capability=True,
        authenticated_attestation_service="artana_evidence_api",
    )
    wrong_handoff = _handoff(
        space_id=space_id,
        document_id=document_id,
        text=text,
        identity=identity,
        locator=_locator(text=text, quote=quote, start=second_start),
    ).model_copy(
        update={"locator": _locator(text=text, quote=quote, start=1)},
    )
    wrong_offset = verify_source_provenance(
        research_space_id=space_id,
        source_document_id=document_id,
        source_evidence=wrong_handoff,
        source_attestation_capability=True,
        authenticated_attestation_service="artana_evidence_api",
    )

    assert valid.status == "verified"
    assert wrong_offset.status == "invalid"
    assert wrong_offset.reason_codes == ("evidence_quote_mismatch",)


def test_immutable_snapshot_rejects_conflicting_content(db_session: Session) -> None:
    space_id = _seed_space(db_session)
    identity = _identity(text="Canonical source.")
    repository = SqlAlchemySourceEvidenceSnapshotRepository(db_session)
    upstream = _upstream(space_id=space_id, document_id=uuid4())
    repository.get_or_create(
        research_space_id=space_id,
        upstream=upstream,
        source_identity=identity,
        canonical_text="Canonical source.",
    )

    with pytest.raises(SourceEvidenceSnapshotConflictError):
        repository.get_or_create(
            research_space_id=space_id,
            upstream=upstream,
            source_identity=identity,
            canonical_text="Conflicting source.",
        )


def test_eligibility_revalidates_persisted_snapshot_and_locator(
    db_session: Session,
) -> None:
    space_id = _seed_space(db_session)
    text = "MED13 is associated with cardiomyopathy."
    locator = _locator(text=text, quote=text, start=0)
    document_id = uuid4()
    submission = SourceProvenanceService(db_session).verify_and_snapshot(
        research_space_id=space_id,
        source_document_id=document_id,
        source_evidence=_handoff(
            space_id=space_id,
            document_id=document_id,
            text=text,
            locator=locator,
        ),
        source_attestation_capability=True,
        authenticated_attestation_service="artana_evidence_api",
    )
    assert submission.snapshot is not None
    evidence = ClaimEvidenceModel(
        id=uuid4(),
        claim_id=uuid4(),
        source_document_id=document_id,
        source_snapshot_id=submission.snapshot.id,
        evidence_locator_payload=locator.model_dump(mode="json"),
        provenance_status="VERIFIED",
        provenance_reason_codes=["verified"],
        confidence=0.9,
        metadata_payload={},
    )

    verdict = ClaimEvidenceEligibilityService(db_session).evaluate(
        evidence,
        research_space_id=space_id,
    )

    assert verdict.eligible is True
    assert verdict.reason is None


def test_legacy_and_forged_references_are_never_eligible(db_session: Session) -> None:
    space_id = _seed_space(db_session)
    legacy = ClaimEvidenceModel(
        id=uuid4(),
        claim_id=uuid4(),
        source_document_id=uuid4(),
        source_document_ref="PMID:12345678",
        agent_run_id="agent-run-forged",
        provenance_status="LEGACY_UNVERIFIED",
        provenance_reason_codes=["legacy_evidence_without_typed_provenance"],
        confidence=1.0,
        metadata_payload={"provenance_id": str(uuid4())},
    )

    verdict = ClaimEvidenceEligibilityService(db_session).evaluate(
        legacy,
        research_space_id=space_id,
    )

    assert verdict.eligible is False
    assert verdict.reason == "provenance_status_not_verified"


def test_source_identity_contract_accepts_nct_and_numeric_clinvar_authorities() -> None:
    common = {
        "retrieved_at": datetime.now(UTC),
        "content_sha256": _sha256("source"),
    }

    nct = SourceIdentity(
        source_kind="clinicaltrials",
        authoritative_identifier="NCT:NCT12345678",
        canonical_url="https://clinicaltrials.gov/study/NCT12345678",
        nct_id="NCT12345678",
        **common,
    )
    clinvar = SourceIdentity(
        source_kind="clinvar",
        authoritative_identifier="CLINVAR:12345",
        canonical_url="https://www.ncbi.nlm.nih.gov/clinvar/variation/12345/",
        clinvar_accession="12345",
        **common,
    )

    assert nct.authoritative_identifier == "NCT:NCT12345678"
    assert clinvar.authoritative_identifier == "CLINVAR:12345"


@pytest.mark.parametrize(
    ("service", "expected_status", "expected_reason"),
    [
        (None, "unverified", "source_attestation_service_missing"),
        ("forged_evidence_api", "invalid", "source_attestation_service_mismatch"),
    ],
)
def test_attestation_service_is_required_and_must_match(
    service: str | None,
    expected_status: str,
    expected_reason: str,
) -> None:
    space_id = uuid4()
    document_id = uuid4()
    verdict = verify_source_provenance(
        research_space_id=space_id,
        source_document_id=document_id,
        source_evidence=_handoff(
            space_id=space_id,
            document_id=document_id,
            text="Source.",
        ),
        source_attestation_capability=True,
        authenticated_attestation_service=service,
    )

    assert verdict.status == expected_status
    assert verdict.reason_codes == (expected_reason,)


@pytest.mark.parametrize(
    ("wrong_binding", "expected_reason"),
    [
        ("space", "upstream_research_space_mismatch"),
        ("document", "upstream_document_id_mismatch"),
    ],
)
def test_handoff_cannot_cross_space_or_document_boundaries(
    wrong_binding: str,
    expected_reason: str,
) -> None:
    space_id = uuid4()
    document_id = uuid4()
    handoff = _handoff(
        space_id=uuid4() if wrong_binding == "space" else space_id,
        document_id=uuid4() if wrong_binding == "document" else document_id,
        text="Source.",
    )

    verdict = verify_source_provenance(
        research_space_id=space_id,
        source_document_id=document_id,
        source_evidence=handoff,
        source_attestation_capability=True,
        authenticated_attestation_service="artana_evidence_api",
    )

    assert verdict.status == "invalid"
    assert verdict.reason_codes == (expected_reason,)


def test_same_document_and_source_identity_reuses_snapshot_across_retries(
    db_session: Session,
) -> None:
    space_id = _seed_space(db_session)
    repository = SqlAlchemySourceEvidenceSnapshotRepository(db_session)
    text = "Stable source text."
    identity = _identity(text=text)
    document_id = uuid4()

    first = repository.get_or_create(
        research_space_id=space_id,
        upstream=_upstream(space_id=space_id, document_id=document_id),
        source_identity=identity,
        canonical_text=text,
    )
    second = repository.get_or_create(
        research_space_id=space_id,
        upstream=_upstream(space_id=space_id, document_id=document_id),
        source_identity=identity,
        canonical_text=text,
    )

    assert second.id == first.id


def test_different_upstream_documents_never_share_a_snapshot(
    db_session: Session,
) -> None:
    space_id = _seed_space(db_session)
    repository = SqlAlchemySourceEvidenceSnapshotRepository(db_session)
    text = "Stable source text."
    identity = _identity(text=text)

    first = repository.get_or_create(
        research_space_id=space_id,
        upstream=_upstream(space_id=space_id, document_id=uuid4()),
        source_identity=identity,
        canonical_text=text,
    )
    second = repository.get_or_create(
        research_space_id=space_id,
        upstream=_upstream(space_id=space_id, document_id=uuid4()),
        source_identity=identity,
        canonical_text=text,
    )

    assert second.id != first.id


def test_eligibility_rejects_a_different_upstream_document_binding(
    db_session: Session,
) -> None:
    space_id = _seed_space(db_session)
    text = "MED13 is associated with cardiomyopathy."
    locator = _locator(text=text, quote=text, start=0)
    document_id = uuid4()
    submission = SourceProvenanceService(db_session).verify_and_snapshot(
        research_space_id=space_id,
        source_document_id=document_id,
        source_evidence=_handoff(
            space_id=space_id,
            document_id=document_id,
            text=text,
            locator=locator,
        ),
        source_attestation_capability=True,
        authenticated_attestation_service="artana_evidence_api",
    )
    assert submission.snapshot is not None
    evidence = ClaimEvidenceModel(
        id=uuid4(),
        claim_id=uuid4(),
        source_document_id=uuid4(),
        source_snapshot_id=submission.snapshot.id,
        evidence_locator_payload=locator.model_dump(mode="json"),
        provenance_status="VERIFIED",
        provenance_reason_codes=["verified"],
        confidence=0.9,
        metadata_payload={},
    )

    verdict = ClaimEvidenceEligibilityService(db_session).evaluate(
        evidence,
        research_space_id=space_id,
    )

    assert verdict.eligible is False
    assert verdict.reason == "source_snapshot_document_mismatch"


def test_source_family_collapses_versions_from_same_authoritative_record() -> None:
    first = SimpleNamespace(
        source_snapshot=SimpleNamespace(
            source_kind="pubmed",
            authoritative_identifier="PMID:12345678",
        ),
    )
    second = SimpleNamespace(
        source_snapshot=SimpleNamespace(
            source_kind="PUBMED",
            authoritative_identifier="pmid:12345678",
        ),
    )

    assert _source_family_key(first) == _source_family_key(second)


def test_source_identity_contract_rejects_internal_only_authority() -> None:
    with pytest.raises(ValidationError):
        SourceIdentity(
            source_kind="pubmed",
            authoritative_identifier="harness_proposal:123",
            canonical_url="https://example.org/source",
            retrieved_at=datetime.now(UTC),
            content_sha256=_sha256("source"),
            pmid="12345678",
        )


def _seed_space(session: Session):  # noqa: ANN202
    space_id = uuid4()
    session.add(
        GraphSpaceModel(
            id=space_id,
            slug=f"source-proof-{space_id.hex[:12]}",
            name="Source proof",
            owner_id=uuid4(),
            status="active",
            settings={},
        ),
    )
    session.flush()
    return space_id


def _identity(*, text: str) -> SourceIdentity:
    return SourceIdentity(
        source_kind="pubmed",
        authoritative_identifier="PMID:12345678",
        canonical_url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
        retrieved_at=datetime.now(UTC),
        content_sha256=_sha256(text),
        pmid="12345678",
    )


def _upstream(
    *,
    space_id: UUID,
    document_id: UUID,
) -> SourceEvidenceUpstream:
    return SourceEvidenceUpstream(
        research_space_id=space_id,
        document_id=document_id,
        attested_at=datetime.now(UTC),
    )


def _handoff(
    *,
    space_id: UUID,
    document_id: UUID,
    text: str,
    identity: SourceIdentity | None = None,
    locator: ExactEvidenceLocator | None = None,
) -> SourceEvidenceHandoff:
    return SourceEvidenceHandoff(
        upstream=_upstream(space_id=space_id, document_id=document_id),
        identity=identity or _identity(text=text),
        canonical_text=text,
        locator=locator or _locator(text=text, quote=text, start=0),
    )


def _locator(*, text: str, quote: str, start: int) -> ExactEvidenceLocator:
    return ExactEvidenceLocator(
        source_content_sha256=_sha256(text),
        char_start=start,
        char_end=start + len(quote),
        exact_quote=quote,
        quote_sha256=_sha256(quote),
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
