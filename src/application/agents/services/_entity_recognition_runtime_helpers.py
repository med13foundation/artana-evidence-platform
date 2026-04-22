"""Runtime utility helpers for entity-recognition orchestration."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from artana_evidence_db.runtime import (
    create_graph_domain_context_policy,
    default_graph_domain_context_for_source_type,
)

from src.domain.entities.source_document import DocumentExtractionStatus
from src.domain.services.domain_context_resolver import DomainContextResolver
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from src.domain.agents.contracts.entity_recognition import EntityRecognitionContract
    from src.domain.entities.source_document import SourceDocument
    from src.domain.repositories.source_document_repository import (
        SourceDocumentRepository,
    )
    from src.type_definitions.common import JSONObject, JSONValue

_ID_CLEANUP_PATTERN = re.compile(r"[^A-Za-z0-9_]+")
_SEPARATOR_PATTERN = re.compile(r"[_\s]+")
_ISO_DATE_ONLY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
logger = logging.getLogger(__name__)


class _EntityRecognitionRuntimeHelpers:
    """Shared runtime helpers for the entity-recognition service."""

    _source_documents: SourceDocumentRepository

    def _persist_extracted_document(
        self,
        *,
        document: SourceDocument,
        run_id: str | None,
        metadata_patch: JSONObject,
    ) -> SourceDocument:
        extracted = document.mark_extracted(
            extraction_agent_run_id=run_id,
            extracted_at=datetime.now(UTC),
        )
        updated = extracted.model_copy(
            update={
                "metadata": self._merge_metadata(
                    extracted.metadata,
                    metadata_patch,
                ),
            },
        )
        return self._source_documents.upsert(updated)

    def _persist_failed_document(
        self,
        *,
        document: SourceDocument,
        run_id: str | None,
        metadata_patch: JSONObject,
    ) -> SourceDocument:
        failed = document.model_copy(
            update={
                "extraction_status": DocumentExtractionStatus.FAILED,
                "extraction_agent_run_id": run_id,
                "updated_at": datetime.now(UTC),
                "metadata": self._merge_metadata(document.metadata, metadata_patch),
            },
        )
        try:
            return self._source_documents.upsert(failed)
        except Exception as exc:  # noqa: BLE001
            rolled_back = self._rollback_source_document_session(
                context="persist_failed_document",
            )
            if not rolled_back:
                raise
            logger.warning(
                "Retrying failed document persistence after rollback "
                "(document_id=%s): %s",
                document.id,
                exc,
            )
            return self._source_documents.upsert(failed)

    def _rollback_source_document_session(self, *, context: str) -> bool:
        repository = self._source_documents
        try:
            session = getattr(repository, "session", None)
        except AttributeError:
            return False
        if session is None:
            return False
        rollback = getattr(session, "rollback", None)
        if rollback is None or not callable(rollback):
            return False
        try:
            rollback()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Source document session rollback failed (context=%s): %s",
                context,
                exc,
            )
            return False
        return True

    @staticmethod
    def _merge_metadata(
        existing: JSONObject,
        patch: JSONObject,
    ) -> JSONObject:
        merged: JSONObject = {
            str(key): to_json_value(value) for key, value in existing.items()
        }
        for key, value in patch.items():
            merged[str(key)] = to_json_value(value)
        return merged

    @staticmethod
    def _resolve_run_id(contract: EntityRecognitionContract) -> str | None:
        run_id = contract.agent_run_id
        if not isinstance(run_id, str):
            return None
        normalized = run_id.strip()
        return normalized or None

    @staticmethod
    def _resolve_governance_decision(
        contract: EntityRecognitionContract,
    ) -> Literal["generated", "fallback", "escalate"]:
        if contract.decision != "escalate":
            return contract.decision

        has_structured_output = bool(
            contract.recognized_entities
            or contract.recognized_observations
            or contract.pipeline_payloads
            or contract.created_definitions
            or contract.created_synonyms
            or contract.created_entity_types
            or contract.created_relation_types
            or contract.created_relation_constraints,
        )
        return "generated" if has_structured_output else contract.decision

    @staticmethod
    def _try_parse_uuid(raw_value: str | None) -> UUID | None:
        if raw_value is None:
            return None
        try:
            return UUID(raw_value)
        except ValueError:
            return None

    @staticmethod
    def _normalize_identifier(
        value: str,
        *,
        prefix: str,
        max_length: int,
    ) -> str:
        stripped = value.strip()
        cleaned = _ID_CLEANUP_PATTERN.sub("_", stripped.upper())
        normalized = cleaned.strip("_")
        normalized = re.sub(r"_+", "_", normalized)
        if not normalized:
            normalized = prefix
        return normalized[:max_length]

    @classmethod
    def _to_canonical_name(cls, field_name: str) -> str:
        base = cls._normalize_identifier(
            field_name,
            prefix="field",
            max_length=128,
        )
        return base.lower()

    @staticmethod
    def _to_display_name(field_name: str) -> str:
        tokens = _SEPARATOR_PATTERN.split(field_name.strip())
        words = [token.capitalize() for token in tokens if token]
        display = " ".join(words)
        return display[:255] if display else "Unnamed Field"

    @classmethod
    def _resolve_variable_id(
        cls,
        *,
        explicit_variable_id: str | None,
        field_name: str,
    ) -> str:
        if isinstance(explicit_variable_id, str) and explicit_variable_id.strip():
            return cls._normalize_identifier(
                explicit_variable_id,
                prefix="VAR_AUTO",
                max_length=64,
            )
        normalized_field = cls._normalize_identifier(
            field_name,
            prefix="FIELD",
            max_length=56,
        )
        return f"VAR_{normalized_field}"[:64]

    @staticmethod
    def _infer_data_type(value: JSONValue) -> str:  # noqa: PLR0911
        if isinstance(value, bool):
            return "BOOLEAN"
        if isinstance(value, int):
            return "INTEGER"
        if isinstance(value, float):
            return "FLOAT"
        if isinstance(value, dict | list):
            return "JSON"
        if isinstance(value, str):
            normalized = value.strip()
            if _ISO_DATE_ONLY_PATTERN.match(normalized):
                return "DATE"
            try:
                datetime.fromisoformat(normalized)
            except ValueError:
                return "STRING"
            return "DATE"
        return "STRING"

    @staticmethod
    def _infer_domain_context(source_type: str) -> str:
        resolved = default_graph_domain_context_for_source_type(
            source_type,
            domain_context_policy=create_graph_domain_context_policy(),
        )
        if resolved is None:
            return DomainContextResolver.GENERAL_DEFAULT_DOMAIN
        return resolved

    @staticmethod
    def _normalize_seed_entity_ids(seed_entity_ids: list[str]) -> tuple[str, ...]:
        normalized_ids: list[str] = []
        for seed_entity_id in seed_entity_ids:
            normalized = seed_entity_id.strip()
            if not normalized or normalized in normalized_ids:
                continue
            normalized_ids.append(normalized)
        return tuple(normalized_ids)


__all__ = ["_EntityRecognitionRuntimeHelpers"]
