"""Repository for immutable graph-owned source evidence snapshots."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from artana_evidence_db.source_provenance.models import (
    SourceEvidenceUpstream,
    SourceIdentity,
)
from artana_evidence_db.source_provenance.snapshot_model import (
    SourceEvidenceSnapshotModel,
)
from artana_evidence_db.source_provenance.snapshot_models import SourceEvidenceSnapshot
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class SourceEvidenceSnapshotConflictError(ValueError):
    """An existing immutable snapshot conflicts with an attempted upsert."""


class SqlAlchemySourceEvidenceSnapshotRepository:
    """Create-once and read operations for immutable source snapshots."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_or_create(
        self,
        *,
        research_space_id: UUID,
        upstream: SourceEvidenceUpstream,
        source_identity: SourceIdentity,
        canonical_text: str,
    ) -> SourceEvidenceSnapshot:
        fingerprint = source_identity_fingerprint(
            upstream=upstream,
            source_identity=source_identity,
        )
        existing = self._session.scalar(
            select(SourceEvidenceSnapshotModel).where(
                SourceEvidenceSnapshotModel.research_space_id == research_space_id,
                SourceEvidenceSnapshotModel.identity_fingerprint == fingerprint,
            ),
        )
        if existing is not None:
            return _validate_existing_snapshot(
                existing,
                upstream=upstream,
                source_identity=source_identity,
                canonical_text=canonical_text,
            )

        model = SourceEvidenceSnapshotModel(
            id=uuid4(),
            research_space_id=research_space_id,
            upstream_service=upstream.service,
            upstream_research_space_id=upstream.research_space_id,
            upstream_document_id=upstream.document_id,
            attested_at=upstream.attested_at.astimezone(UTC),
            identity_fingerprint=fingerprint,
            source_kind=source_identity.source_kind,
            authoritative_identifier=source_identity.authoritative_identifier,
            canonical_url=source_identity.canonical_url,
            retrieved_at=source_identity.retrieved_at.astimezone(UTC),
            content_sha256=source_identity.content_sha256,
            version=source_identity.version,
            artifact_sha256=source_identity.artifact_sha256,
            canonical_text=canonical_text,
            source_identity_payload=source_identity.model_dump(mode="json"),
        )
        self._session.add(model)
        self._session.flush()
        return _to_domain(model)

    def get_by_id(self, snapshot_id: UUID) -> SourceEvidenceSnapshot | None:
        model = self._session.get(SourceEvidenceSnapshotModel, snapshot_id)
        return _to_domain(model) if model is not None else None

    def get_models_by_ids(
        self,
        snapshot_ids: set[UUID],
    ) -> dict[UUID, SourceEvidenceSnapshotModel]:
        if not snapshot_ids:
            return {}
        models = self._session.scalars(
            select(SourceEvidenceSnapshotModel).where(
                SourceEvidenceSnapshotModel.id.in_(snapshot_ids),
            ),
        ).all()
        return {model.id: model for model in models}


def source_identity_fingerprint(
    *,
    upstream: SourceEvidenceUpstream,
    source_identity: SourceIdentity,
) -> str:
    """Identify one exact upstream-document and source-identity attestation."""

    serialized = json.dumps(
        {
            "upstream_service": upstream.service,
            "upstream_research_space_id": str(upstream.research_space_id),
            "upstream_document_id": str(upstream.document_id),
            "source_identity": source_identity.model_dump(mode="json"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _validate_existing_snapshot(
    model: SourceEvidenceSnapshotModel,
    *,
    upstream: SourceEvidenceUpstream,
    source_identity: SourceIdentity,
    canonical_text: str,
) -> SourceEvidenceSnapshot:
    stored_identity = SourceIdentity.model_validate(model.source_identity_payload)
    provenance_conflicts = (
        model.upstream_service != upstream.service
        or model.upstream_research_space_id != upstream.research_space_id
        or model.upstream_document_id != upstream.document_id
        or stored_identity != source_identity
    )
    if provenance_conflicts or model.canonical_text != canonical_text:
        msg = "immutable source evidence snapshot conflicts with submitted content"
        raise SourceEvidenceSnapshotConflictError(msg)
    return _to_domain(model)


def _to_domain(model: SourceEvidenceSnapshotModel) -> SourceEvidenceSnapshot:
    return SourceEvidenceSnapshot(
        id=model.id,
        research_space_id=model.research_space_id,
        upstream_service=model.upstream_service,
        upstream_research_space_id=model.upstream_research_space_id,
        upstream_document_id=model.upstream_document_id,
        attested_at=model.attested_at,
        identity_fingerprint=model.identity_fingerprint,
        source_identity=SourceIdentity.model_validate(model.source_identity_payload),
        canonical_text=model.canonical_text,
        created_at=model.created_at,
    )


__all__ = [
    "SourceEvidenceSnapshotConflictError",
    "SqlAlchemySourceEvidenceSnapshotRepository",
    "source_identity_fingerprint",
]
