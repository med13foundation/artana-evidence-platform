"""
Entity resolver engine for the ingestion pipeline.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.domain.services.ingestion import IngestionProgressUpdate
from src.infrastructure.ingestion.resolution.strategies import (
    FuzzyStrategy,
    LookupStrategy,
    ResolutionStrategy,
    StrictMatchStrategy,
)
from src.infrastructure.ingestion.types import ResolvedEntity

if TYPE_CHECKING:
    from artana_evidence_db.kernel_domain_models import EntityResolutionPolicy
    from artana_evidence_db.kernel_repositories import KernelEntityRepository
    from artana_evidence_db.semantic_ports import DictionaryPort

    from src.domain.services.ingestion import IngestionProgressCallback
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)


class EntityResolver:
    """
    Resolves entity anchors to kernel entities using configured policies.
    """

    def __init__(
        self,
        dictionary_repository: DictionaryPort,
        entity_repository: KernelEntityRepository,
    ) -> None:
        self.dict_repo = dictionary_repository
        self.entity_repo = entity_repository

        # Initialize strategies
        self.strategies: dict[str, ResolutionStrategy] = {
            "STRICT_MATCH": StrictMatchStrategy(entity_repository),
            "LOOKUP": LookupStrategy(entity_repository),
            "FUZZY": FuzzyStrategy(entity_repository),
            "NONE": StrictMatchStrategy(entity_repository),  # Default/Fallback
        }

    @staticmethod
    def _normalize_entity_type(entity_type: str) -> str:
        normalized = entity_type.strip().upper()
        return normalized.replace("-", "_").replace("/", "_").replace(" ", "_")

    def _resolve_policy_for_entity_type(
        self,
        *,
        entity_type: str,
        anchor: JSONObject,
        source_record_id: str | None,
        progress_callback: IngestionProgressCallback | None,
    ) -> EntityResolutionPolicy | None:
        policy = self.dict_repo.get_resolution_policy(entity_type)
        if policy is not None:
            return policy
        self._emit_missing_policy_warning(
            entity_type=entity_type,
            anchor=anchor,
            source_record_id=source_record_id,
            progress_callback=progress_callback,
        )
        msg = (
            f"No resolution policy configured for entity_type={entity_type}. "
            "Configure the dictionary before ingestion."
        )
        raise ValueError(msg)

    def _require_active_entity_type(
        self,
        *,
        entity_type: str,
    ) -> str:
        normalized_entity_type = self._normalize_entity_type(entity_type)
        existing_entity_type = self.dict_repo.get_entity_type(
            normalized_entity_type,
            include_inactive=True,
        )
        if existing_entity_type is None:
            msg = (
                f"Unknown entity_type '{normalized_entity_type}'. "
                "Create or approve the dictionary entity type before ingestion."
            )
            raise ValueError(msg)
        if not (
            existing_entity_type.is_active
            and existing_entity_type.review_status == "ACTIVE"
        ):
            msg = (
                f"Entity type '{normalized_entity_type}' exists but is not active. "
                "Review or reactivate it before ingestion."
            )
            raise ValueError(msg)
        return existing_entity_type.id

    @staticmethod
    def _emit_entity_type_validation_warning(
        *,
        entity_type: str,
        source_record_id: str | None,
        progress_callback: IngestionProgressCallback | None,
        reason: str,
        message: str,
    ) -> None:
        logger.warning(message)
        if progress_callback is None:
            return
        payload: JSONObject = {
            "entity_type": entity_type,
            "reason": reason,
        }
        if isinstance(source_record_id, str) and source_record_id.strip():
            payload["source_record_id"] = source_record_id.strip()
        progress_callback(
            IngestionProgressUpdate(
                event_type="resolver_warning",
                message=message,
                payload=payload,
            ),
        )

    @staticmethod
    def _emit_missing_policy_warning(
        *,
        entity_type: str,
        anchor: JSONObject,
        source_record_id: str | None,
        progress_callback: IngestionProgressCallback | None,
    ) -> None:
        warning_message = (
            "No resolution policy configured for "
            f"entity_type={entity_type}; falling back to "
            "STRICT_MATCH with best-effort anchors."
        )
        logger.warning(warning_message)
        if progress_callback is None:
            return

        warning_payload: JSONObject = {
            "entity_type": entity_type,
            "fallback_strategy": "STRICT_MATCH",
            "reason": "missing_resolution_policy",
            "anchor_keys": sorted(anchor.keys()),
        }
        if isinstance(source_record_id, str) and source_record_id.strip():
            warning_payload["source_record_id"] = source_record_id.strip()
        progress_callback(
            IngestionProgressUpdate(
                event_type="resolver_warning",
                message=warning_message,
                payload=warning_payload,
            ),
        )

    def resolve(
        self,
        anchor: JSONObject,
        entity_type: str,
        research_space_id: str,
        *,
        source_record_id: str | None = None,
        progress_callback: IngestionProgressCallback | None = None,
    ) -> ResolvedEntity:
        """
        Resolve an entity anchor to a kernel entity.
        If resolution fails or no entity exists, creates a new one (if policy allows)
        or returns a provisional entity structure.

        NOTE: This implementation currently only TRYES to resolve.
        It does NOT create new entities yet. The creation logic might belong here
        or in the service layer using the resolver.
        For the pipeline, we need a ResolvedEntity ID to link observations.

        If not found, we effectively create a "new" entity ID to be persisted.
        """

        try:
            normalized_entity_type = self._require_active_entity_type(
                entity_type=entity_type,
            )
        except ValueError as exc:
            normalized_input = self._normalize_entity_type(entity_type)
            reason = (
                "unknown_entity_type"
                if "Unknown entity_type" in str(exc)
                else "inactive_entity_type"
            )
            self._emit_entity_type_validation_warning(
                entity_type=normalized_input,
                source_record_id=source_record_id,
                progress_callback=progress_callback,
                reason=reason,
                message=str(exc),
            )
            raise
        policy = self._resolve_policy_for_entity_type(
            entity_type=normalized_entity_type,
            anchor=anchor,
            source_record_id=source_record_id,
            progress_callback=progress_callback,
        )
        strategy_name = "STRICT_MATCH"
        if policy:
            strategy_name = policy.policy_strategy

        strategy = self.strategies.get(strategy_name, self.strategies["STRICT_MATCH"])

        required_anchors: list[str] = (
            policy.required_anchors
            if policy and isinstance(policy.required_anchors, list)
            else []
        )
        missing_required = []
        for anchor_key in required_anchors:
            if anchor_key not in anchor:
                missing_required.append(anchor_key)
                continue
            value = anchor[anchor_key]
            if value is None:
                missing_required.append(anchor_key)
                continue
            if isinstance(value, str) and not value.strip():
                missing_required.append(anchor_key)

        existing_entity = None
        if missing_required:
            logger.info(
                "Missing required anchors %s for %s; using create-new fallback.",
                missing_required,
                normalized_entity_type,
            )
        else:
            existing_entity = strategy.resolve(
                anchor,
                normalized_entity_type,
                research_space_id,
            )

        if existing_entity:
            return ResolvedEntity(
                id=str(existing_entity.id),
                entity_type=existing_entity.entity_type,
                display_label=existing_entity.display_label or "Unknown",
                created=False,
            )

        # If not found, we generate a new ID and basic info
        # The pipeline will likely need to persist this new entity.
        # For now, we return a ResolvedEntity with a special flag or just new UUID?
        # The ResolvedEntity dataclass expects an ID.
        # If we return a new UUID here, the caller needs to know it's new to save it.
        # This interaction implies the Resolver might need to CREATE the entity if strictly necessary
        # or we update ResolvedEntity to indicate "is_new".

        # Taking a pragmatic approach: The resolution engine ensures we have an ID.
        # If it doesn't exist, we create it in the database immediately?
        # Or we return a "Draft" entity.

        # Let's create it immediately for simplicity in this pipeline context,
        # or delegated to a service.
        # Given this is "Infrastructure", calling Repo.create is fine.

        # Construct display label from anchor if possible
        display_label = self._derive_label(anchor, normalized_entity_type)

        new_entity = self.entity_repo.create(
            research_space_id=research_space_id,
            entity_type=normalized_entity_type,
            display_label=display_label,
            metadata=anchor,
        )

        # We should also add the identifiers from the anchor so it can be resolved next time
        for k, v in anchor.items():
            # Heuristic: verify if key look likes a namespace
            # For now add all anchor keys as identifiers
            self.entity_repo.add_identifier(
                entity_id=str(new_entity.id),
                namespace=k,
                identifier_value=str(v),
            )

        return ResolvedEntity(
            id=str(new_entity.id),
            entity_type=new_entity.entity_type,
            display_label=new_entity.display_label or "New Entity",
            created=True,
        )

    def _derive_label(self, anchor: JSONObject, entity_type: str) -> str:
        # heuristics for label
        for key in [
            "display_label",
            "hgvs_notation",
            "mechanism_name",
            "name",
            "symbol",
            "title",
            "label",
            "id",
            "gene_symbol",
        ]:
            if key in anchor:
                return str(anchor[key])
        # Fallback
        return f"{entity_type} {list(anchor.values())[0] if anchor else 'Unknown'}"
