"""Claim projection service factory mixin."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_db.claim_evidence_service import KernelClaimEvidenceService
from artana_evidence_db.claim_participant_service import KernelClaimParticipantService
from artana_evidence_db.claim_relation_service import KernelClaimRelationService
from artana_evidence_db.kernel_runtime_factories import (
    build_graph_read_model_update_dispatcher,
)
from artana_evidence_db.relation_claim_service import KernelRelationClaimService
from artana_evidence_db.relation_projection_invariant_service import (
    KernelRelationProjectionInvariantService,
)
from artana_evidence_db.relation_projection_materialization_service import (
    KernelRelationProjectionMaterializationService,
)
from artana_evidence_db.relation_projection_source_service import (
    KernelRelationProjectionSourceService,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class KernelClaimProjectionServiceFactoryMixin:
    """Factory methods for claim ledger, evidence, and projection services."""

    def _require_core_factory(self) -> object:
        from src.infrastructure.dependency_injection._kernel_core_service_factories import (
            KernelCoreServiceFactoryMixin,
        )

        if not isinstance(self, KernelCoreServiceFactoryMixin):
            msg = "KernelCoreServiceFactoryMixin is required"
            raise TypeError(msg)
        return self

    def create_kernel_relation_claim_service(
        self,
        session: Session,
    ) -> KernelRelationClaimService:
        core_factory = self._require_core_factory()
        return KernelRelationClaimService(
            relation_claim_repo=core_factory._build_relation_claim_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
            read_model_update_dispatcher=build_graph_read_model_update_dispatcher(
                session,
            ),
        )

    def create_kernel_relation_projection_source_service(
        self,
        session: Session,
    ) -> KernelRelationProjectionSourceService:
        core_factory = self._require_core_factory()
        return KernelRelationProjectionSourceService(
            relation_projection_repo=core_factory._build_relation_projection_source_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
        )

    def create_kernel_relation_projection_invariant_service(
        self,
        session: Session,
    ) -> KernelRelationProjectionInvariantService:
        core_factory = self._require_core_factory()
        return KernelRelationProjectionInvariantService(
            relation_projection_repo=core_factory._build_relation_projection_source_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
        )

    def create_kernel_relation_projection_materialization_service(
        self,
        session: Session,
    ) -> KernelRelationProjectionMaterializationService:
        core_factory = self._require_core_factory()
        return KernelRelationProjectionMaterializationService(
            relation_repo=core_factory._build_relation_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
            relation_claim_repo=core_factory._build_relation_claim_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
            claim_participant_repo=core_factory._build_claim_participant_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
            claim_evidence_repo=core_factory._build_claim_evidence_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
            entity_repo=core_factory._build_entity_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
            dictionary_repo=core_factory._build_dictionary_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
            relation_projection_repo=core_factory._build_relation_projection_source_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
            read_model_update_dispatcher=build_graph_read_model_update_dispatcher(
                session,
            ),
        )

    def create_kernel_claim_participant_service(
        self,
        session: Session,
    ) -> KernelClaimParticipantService:
        core_factory = self._require_core_factory()
        return KernelClaimParticipantService(
            claim_participant_repo=core_factory._build_claim_participant_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
        )

    def create_kernel_claim_relation_service(
        self,
        session: Session,
    ) -> KernelClaimRelationService:
        core_factory = self._require_core_factory()
        return KernelClaimRelationService(
            claim_relation_repo=core_factory._build_claim_relation_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
        )

    def create_kernel_claim_evidence_service(
        self,
        session: Session,
    ) -> KernelClaimEvidenceService:
        core_factory = self._require_core_factory()
        return KernelClaimEvidenceService(
            claim_evidence_repo=core_factory._build_claim_evidence_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
        )


__all__ = ["KernelClaimProjectionServiceFactoryMixin"]
