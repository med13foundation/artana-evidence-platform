"""Auto-resolve, retry gating, and persistence error helpers for extraction relations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

if TYPE_CHECKING:
    from collections.abc import Callable

    from artana_evidence_db.kernel_domain_models import (
        KernelRelationClaim,
        RelationClaimStatus,
    )
    from artana_evidence_db.kernel_repositories import (
        KernelRelationClaimRepository,
    )
    from artana_evidence_db.semantic_ports import DictionaryPort

    from src.application.agents.services._extraction_relation_policy_helpers import (
        RelationGovernanceMode,
        _ResolvedRelationCandidate,
    )

_LOW_CONFIDENCE_REVIEW_THRESHOLD = 0.6
_FULL_AUTO_CONFIDENCE_THRESHOLD = 0.0
logger = logging.getLogger(__name__)


class _AutoResolveSelf(Protocol):
    _relation_claims: KernelRelationClaimRepository | None
    _dictionary: DictionaryPort | None
    _rollback_on_error: Callable[[], None] | None

    @staticmethod
    def _extract_auto_resolve_retry_key(claim: KernelRelationClaim) -> str | None: ...

    @staticmethod
    def _claim_signature(
        claim: KernelRelationClaim,
    ) -> tuple[str, str, str, str, str]: ...

    @staticmethod
    def _map_relation_write_error_code(exc: Exception) -> str: ...

    def _rollback_after_persistence_error(self, *, context: str) -> None: ...


class _ExtractionRelationAutoResolveHelpers:
    """Shared helper methods for claim auto-resolve and retry gating."""

    def _load_full_auto_retry_index(
        self: _AutoResolveSelf,
        *,
        research_space_id: str,
        source_document_id: str,
        relation_governance_mode: RelationGovernanceMode,
    ) -> dict[tuple[str, str, str, str, str], str]:
        if (
            relation_governance_mode != "FULL_AUTO"
            or self._relation_claims is None
            or not research_space_id
        ):
            return {}
        try:
            existing_claims = self._relation_claims.find_by_research_space(
                research_space_id,
                source_document_id=source_document_id,
                limit=5000,
            )
        except (TypeError, ValueError, SQLAlchemyError):
            return {}

        retry_index: dict[tuple[str, str, str, str, str], str] = {}
        for claim in existing_claims:
            if claim.linked_relation_id is not None:
                continue
            if claim.claim_status not in {"OPEN", "NEEDS_MAPPING"}:
                continue
            retry_key = self._extract_auto_resolve_retry_key(claim)
            if retry_key is None:
                continue
            signature = self._claim_signature(claim)
            if signature in retry_index:
                continue
            retry_index[signature] = retry_key
        return retry_index

    def _resolve_dictionary_fingerprint(self: _AutoResolveSelf) -> str:
        if self._dictionary is None:
            return "dictionary_unavailable"
        try:
            changelog_entries = self._dictionary.list_changelog_entries(limit=1)
        except ValueError:
            return "dictionary_changelog_error"
        if not changelog_entries:
            return "0"
        return str(changelog_entries[0].id)

    @staticmethod
    def _candidate_signature(
        candidate: _ResolvedRelationCandidate,
    ) -> tuple[str, str, str, str, str]:
        return (
            candidate.source_type.strip().upper(),
            candidate.relation_type.strip().upper(),
            candidate.target_type.strip().upper(),
            _ExtractionRelationAutoResolveHelpers._normalize_signature_label(
                candidate.source_label,
            ),
            _ExtractionRelationAutoResolveHelpers._normalize_signature_label(
                candidate.target_label,
            ),
        )

    @staticmethod
    def _claim_signature(
        claim: KernelRelationClaim,
    ) -> tuple[str, str, str, str, str]:
        return (
            claim.source_type.strip().upper(),
            claim.relation_type.strip().upper(),
            claim.target_type.strip().upper(),
            _ExtractionRelationAutoResolveHelpers._normalize_signature_label(
                claim.source_label,
            ),
            _ExtractionRelationAutoResolveHelpers._normalize_signature_label(
                claim.target_label,
            ),
        )

    @staticmethod
    def _normalize_signature_label(label: str | None) -> str:
        if label is None:
            return ""
        return label.strip().upper()

    @staticmethod
    def _extract_auto_resolve_retry_key(
        claim: KernelRelationClaim,
    ) -> str | None:
        raw_retry_key = claim.metadata_payload.get(
            "auto_resolve_dictionary_fingerprint",
        )
        if not isinstance(raw_retry_key, str):
            return None
        normalized = raw_retry_key.strip()
        return normalized or None

    @staticmethod
    def _resolve_full_auto_terminal_status(
        *,
        candidate: _ResolvedRelationCandidate,
    ) -> RelationClaimStatus:
        if candidate.validation_state in {
            "FORBIDDEN",
            "INVALID_COMPONENTS",
            "SELF_LOOP",
        }:
            return "REJECTED"
        return "NEEDS_MAPPING"

    def _set_claim_system_status(
        self: _AutoResolveSelf,
        *,
        claim_id: str,
        claim_status: RelationClaimStatus,
    ) -> list[str]:
        if self._relation_claims is None:
            return []
        try:
            self._relation_claims.set_system_status(
                claim_id,
                claim_status=claim_status,
            )
        except (TypeError, ValueError, SQLAlchemyError) as exc:
            self._rollback_after_persistence_error(
                context="relation_claim_set_system_status",
            )
            error_code = self._map_relation_write_error_code(exc)
            return [f"relation_claim_status_update_failed:{error_code}:{claim_id}"]
        return []

    def _link_claim_to_relation(
        self: _AutoResolveSelf,
        *,
        claim_id: str,
        relation_id: str,
    ) -> list[str]:
        if self._relation_claims is None:
            return []
        try:
            self._relation_claims.link_relation(
                claim_id,
                linked_relation_id=relation_id,
            )
        except (TypeError, ValueError, SQLAlchemyError) as exc:
            self._rollback_after_persistence_error(
                context="relation_claim_link",
            )
            error_code = self._map_relation_write_error_code(exc)
            return [f"relation_claim_link_failed:{error_code}:{claim_id}:{relation_id}"]
        return []

    @staticmethod
    def _map_relation_write_error_code(  # noqa: C901, PLR0911
        exc: Exception,
    ) -> str:
        message = str(exc)
        if isinstance(exc, IntegrityError) and exc.orig is not None:
            message = str(exc.orig)
        normalized = message.strip().lower()

        if "requires evidence but none exists at commit" in normalized:
            return "relation_requires_evidence"
        if "not allowed by active relation constraints" in normalized:
            return "relation_triple_not_allowed"
        if (
            "fk_relations_source_space_entities" in normalized
            or "source_id" in normalized
            and "does not belong to research_space_id" in normalized
        ):
            return "relation_source_cross_space"
        if (
            "fk_relations_target_space_entities" in normalized
            or "target_id" in normalized
            and "does not belong to research_space_id" in normalized
        ):
            return "relation_target_cross_space"
        if (
            "fk_relations_relation_type_dictionary" in normalized
            or "active dictionary_relation_type" in normalized
        ):
            return "relation_type_invalid_or_inactive"
        if (
            "fk_entities_entity_type_dictionary" in normalized
            or "active dictionary_entity_type" in normalized
        ):
            return "entity_type_invalid_or_inactive"
        if "uq_relations_canonical_edge" in normalized:
            return "relation_edge_duplicate"
        if "foreign key" in normalized:
            return "relation_foreign_key_violation"
        if isinstance(exc, ValueError | TypeError):
            return "relation_payload_invalid"
        if isinstance(exc, IntegrityError):
            return "relation_integrity_violation"
        if isinstance(exc, SQLAlchemyError):
            return "relation_sqlalchemy_error"
        return "relation_write_failed"

    def _rollback_after_persistence_error(
        self: _AutoResolveSelf,
        *,
        context: str,
    ) -> None:
        rollback = self._rollback_on_error
        if rollback is None:
            return
        try:
            rollback()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed rollback after extraction relation persistence error "
                "(context=%s): %s",
                context,
                exc,
            )

    @staticmethod
    def _review_priority_for_candidate(
        *,
        candidate: _ResolvedRelationCandidate,
    ) -> str:
        if candidate.validation_state in {"FORBIDDEN", "SELF_LOOP"}:
            return "high"
        if candidate.validation_state == "UNDEFINED":
            return "medium"
        if candidate.confidence < _LOW_CONFIDENCE_REVIEW_THRESHOLD:
            return "medium"
        return "low"


__all__ = [
    "_FULL_AUTO_CONFIDENCE_THRESHOLD",
    "_ExtractionRelationAutoResolveHelpers",
]
