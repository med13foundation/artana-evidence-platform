"""Graph write boundary for source-document entity recognition."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from artana_evidence_api.source_document_entity_extraction import (
    RecognizedEntityCandidate,
)
from artana_evidence_api.source_document_models import SourceDocument
from artana_evidence_api.types.common import JSONObject
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session


class SourceDocumentGraphWriter:
    """Persist deterministic source-document candidates as graph observations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def persist_candidates(
        self,
        *,
        source_document: SourceDocument,
        candidates: list[RecognizedEntityCandidate],
    ) -> dict[str, str]:
        """Persist candidate entities and observations, returning ids by label."""

        entity_ids_by_label: dict[str, str] = {}
        for candidate in candidates:
            entity_id = self._upsert_candidate_entity(
                source_document=source_document,
                candidate=candidate,
            )
            entity_ids_by_label[candidate.label] = str(entity_id)
            self._insert_candidate_observation(
                source_document=source_document,
                candidate=candidate,
                entity_id=entity_id,
            )
        self._commit()
        return entity_ids_by_label

    def _upsert_candidate_entity(
        self,
        *,
        source_document: SourceDocument,
        candidate: RecognizedEntityCandidate,
    ) -> UUID:
        research_space_id = _require_research_space_id(source_document)
        existing_id = self._execute_scalar(
            """
            SELECT id FROM entities
            WHERE research_space_id = :research_space_id
              AND entity_type = :entity_type
              AND display_label_normalized = :display_label_normalized
            LIMIT 1
            """,
            {
                "research_space_id": str(research_space_id),
                "entity_type": candidate.entity_type,
                "display_label_normalized": candidate.normalized_label,
            },
        )
        if isinstance(existing_id, UUID):
            return existing_id
        if isinstance(existing_id, str) and existing_id.strip():
            return UUID(existing_id)

        entity_id = uuid5(
            NAMESPACE_URL,
            (
                "artana-evidence-api:observation-bridge:"
                f"{research_space_id}:"
                f"{candidate.entity_type}:{candidate.normalized_label}"
            ),
        )
        metadata: JSONObject = {
            "source": "research_init_observation_bridge",
            "source_document_id": str(source_document.id),
            "external_record_id": source_document.external_record_id,
            "evidence_text": candidate.evidence_text,
        }
        self._execute_write(
            """
            INSERT INTO entities (
                id,
                research_space_id,
                entity_type,
                display_label,
                display_label_normalized,
                metadata_payload,
                created_at,
                updated_at
            ) VALUES (
                :id,
                :research_space_id,
                :entity_type,
                :display_label,
                :display_label_normalized,
                :metadata_payload,
                :created_at,
                :updated_at
            )
            """,
            {
                "id": str(entity_id),
                "research_space_id": str(research_space_id),
                "entity_type": candidate.entity_type,
                "display_label": candidate.label,
                "display_label_normalized": candidate.normalized_label,
                "metadata_payload": json.dumps(metadata, sort_keys=True),
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
        )
        return entity_id

    def _insert_candidate_observation(
        self,
        *,
        source_document: SourceDocument,
        candidate: RecognizedEntityCandidate,
        entity_id: UUID,
    ) -> None:
        research_space_id = _require_research_space_id(source_document)
        self._execute_write(
            """
            INSERT INTO observations (
                id,
                research_space_id,
                subject_id,
                variable_id,
                value_text,
                confidence,
                observed_at,
                created_at,
                updated_at
            ) VALUES (
                :id,
                :research_space_id,
                :subject_id,
                :variable_id,
                :value_text,
                :confidence,
                :observed_at,
                :created_at,
                :updated_at
            )
            """,
            {
                "id": str(uuid4()),
                "research_space_id": str(research_space_id),
                "subject_id": str(entity_id),
                "variable_id": "document_entity_mention",
                "value_text": candidate.evidence_text,
                "confidence": 0.72,
                "observed_at": datetime.now(UTC),
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
        )

    def _execute_scalar(
        self,
        statement: str,
        parameters: Mapping[str, object],
    ) -> object | None:
        result = self._execute(statement, parameters)
        scalar_one_or_none = getattr(result, "scalar_one_or_none", None)
        if callable(scalar_one_or_none):
            return cast("object | None", scalar_one_or_none())
        return None

    def _execute_write(
        self,
        statement: str,
        parameters: Mapping[str, object],
    ) -> None:
        self._execute(statement, parameters)

    def _execute(self, statement: str, parameters: Mapping[str, object]) -> object:
        execute = getattr(self._session, "execute", None)
        if not callable(execute):
            msg = "Observation bridge session does not expose execute()"
            raise TypeError(msg)
        return cast("object", execute(sa_text(statement), parameters))

    def _commit(self) -> None:
        commit = getattr(self._session, "commit", None)
        if callable(commit):
            commit()


def _require_research_space_id(source_document: SourceDocument) -> UUID:
    if source_document.research_space_id is not None:
        return source_document.research_space_id
    msg = "Source-document graph writes require research_space_id."
    raise ValueError(msg)


__all__ = ["SourceDocumentGraphWriter"]
