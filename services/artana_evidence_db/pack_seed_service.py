"""Explicit, versioned graph domain-pack seeding."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from artana_evidence_db.biomedical_concept_bootstrap import (
    seed_biomedical_starter_concepts,
)
from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.governance import seed_builtin_dictionary_entries
from artana_evidence_db.pack_seed_models import (
    GraphPackSeedOperationEnum,
    GraphPackSeedStatusEnum,
    GraphPackSeedStatusModel,
)
from artana_evidence_db.runtime.contracts import GraphDomainPack
from sqlalchemy import select
from sqlalchemy.orm import Session

GraphPackSeedOperation = Literal["seed", "repair"]


@dataclass(frozen=True, slots=True)
class GraphPackSeedOperationResult:
    """Result of one explicit pack seed or repair operation."""

    status: GraphPackSeedStatusModel
    applied: bool
    operation: GraphPackSeedOperation


class GraphPackSeedService:
    """Owns idempotent pack seeding and seed-status persistence."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_status(
        self,
        *,
        research_space_id: UUID,
        pack: GraphDomainPack,
    ) -> GraphPackSeedStatusModel | None:
        return self._session.scalar(
            select(GraphPackSeedStatusModel).where(
                GraphPackSeedStatusModel.research_space_id == research_space_id,
                GraphPackSeedStatusModel.pack_name == pack.name,
                GraphPackSeedStatusModel.pack_version == pack.version,
            ),
        )

    def seed_space(
        self,
        *,
        research_space_id: UUID,
        pack: GraphDomainPack,
    ) -> GraphPackSeedOperationResult:
        existing = self.get_status(research_space_id=research_space_id, pack=pack)
        if existing is not None:
            return GraphPackSeedOperationResult(
                status=existing,
                applied=False,
                operation="seed",
            )
        self._apply_pack_seed(research_space_id=research_space_id, pack=pack)
        now = datetime.now(UTC)
        status = GraphPackSeedStatusModel(
            id=uuid4(),
            research_space_id=research_space_id,
            pack_name=pack.name,
            pack_version=pack.version,
            status=GraphPackSeedStatusEnum.SEEDED,
            last_operation=GraphPackSeedOperationEnum.SEED,
            seed_count=1,
            repair_count=0,
            metadata_payload=self._pack_metadata(pack=pack),
            seeded_at=now,
            repaired_at=None,
            created_at=now,
            updated_at=now,
        )
        self._session.add(status)
        self._session.flush()
        return GraphPackSeedOperationResult(
            status=status,
            applied=True,
            operation="seed",
        )

    def repair_space(
        self,
        *,
        research_space_id: UUID,
        pack: GraphDomainPack,
    ) -> GraphPackSeedOperationResult:
        self._apply_pack_seed(research_space_id=research_space_id, pack=pack)
        now = datetime.now(UTC)
        existing = self.get_status(research_space_id=research_space_id, pack=pack)
        if existing is None:
            existing = GraphPackSeedStatusModel(
                id=uuid4(),
                research_space_id=research_space_id,
                pack_name=pack.name,
                pack_version=pack.version,
                status=GraphPackSeedStatusEnum.SEEDED,
                last_operation=GraphPackSeedOperationEnum.REPAIR,
                seed_count=0,
                repair_count=1,
                metadata_payload=self._pack_metadata(pack=pack),
                seeded_at=now,
                repaired_at=now,
                created_at=now,
                updated_at=now,
            )
            self._session.add(existing)
        else:
            existing.last_operation = GraphPackSeedOperationEnum.REPAIR
            existing.repair_count = int(existing.repair_count or 0) + 1
            existing.repaired_at = now
            existing.updated_at = now
            existing.metadata_payload = self._pack_metadata(pack=pack)
        self._session.flush()
        return GraphPackSeedOperationResult(
            status=existing,
            applied=True,
            operation="repair",
        )

    def _apply_pack_seed(
        self,
        *,
        research_space_id: UUID,
        pack: GraphDomainPack,
    ) -> None:
        seed_builtin_dictionary_entries(
            self._session,
            dictionary_loading_extension=pack.dictionary_loading_extension,
        )
        if pack.name == "biomedical":
            seed_biomedical_starter_concepts(
                self._session,
                research_space_id=research_space_id,
            )

    @staticmethod
    def _pack_metadata(*, pack: GraphDomainPack) -> JSONObject:
        return {
            "domain_contexts": [
                context.id
                for context in pack.dictionary_loading_extension.builtin_domain_contexts
            ],
            "entity_types": [
                entity.entity_type
                for entity in pack.dictionary_loading_extension.builtin_entity_types
            ],
            "relation_types": [
                relation.relation_type
                for relation in pack.dictionary_loading_extension.builtin_relation_types
            ],
            "space_seed": "biomedical_starter_concepts"
            if pack.name == "biomedical"
            else "none",
        }


__all__ = [
    "GraphPackSeedOperation",
    "GraphPackSeedOperationResult",
    "GraphPackSeedService",
]
