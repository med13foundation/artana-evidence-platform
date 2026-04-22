"""Reasoning, readiness, and hypothesis service factory mixin."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_db.claim_participant_backfill_service import (
    KernelClaimParticipantBackfillService,
)
from artana_evidence_db.claim_projection_readiness_service import (
    KernelClaimProjectionReadinessService,
)
from artana_evidence_db.graph_domain_config import GRAPH_SERVICE_VIEW_CONFIG
from artana_evidence_db.graph_view_service import KernelGraphViewService
from artana_evidence_db.graph_view_support import KernelGraphViewServiceDependencies
from artana_evidence_db.kernel_runtime_factories import (
    build_graph_read_model_update_dispatcher,
)
from artana_evidence_db.reasoning_path_service import KernelReasoningPathService
from artana_evidence_db.runtime import create_graph_domain_pack

from src.application.agents.services import (
    HypothesisGenerationService,
    HypothesisGenerationServiceDependencies,
)
from src.domain.agents.models import ModelCapability
from src.infrastructure.llm.adapters import ArtanaGraphConnectionAdapter
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.graph_domain_ai_config import create_graph_domain_ai_config

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class KernelReasoningHypothesisServiceFactoryMixin:
    """Factory methods for reasoning paths, graph views, readiness, and hypotheses."""

    def _require_core_factory(self) -> object:
        from src.infrastructure.dependency_injection._kernel_core_service_factories import (
            KernelCoreServiceFactoryMixin,
        )

        if not isinstance(self, KernelCoreServiceFactoryMixin):
            msg = "KernelCoreServiceFactoryMixin is required"
            raise TypeError(msg)
        return self

    def _require_projection_factory(self) -> object:
        from src.infrastructure.dependency_injection._kernel_claim_projection_service_factories import (
            KernelClaimProjectionServiceFactoryMixin,
        )

        if not isinstance(self, KernelClaimProjectionServiceFactoryMixin):
            msg = "KernelClaimProjectionServiceFactoryMixin is required"
            raise TypeError(msg)
        return self

    def create_kernel_graph_view_service(
        self,
        session: Session,
    ) -> KernelGraphViewService:
        core_factory = self._require_core_factory()
        projection_factory = self._require_projection_factory()
        return KernelGraphViewService(
            KernelGraphViewServiceDependencies(
                entity_service=core_factory.create_kernel_entity_service(session),  # type: ignore[attr-defined]
                relation_service=core_factory.create_kernel_relation_service(session),  # type: ignore[attr-defined]
                relation_claim_service=projection_factory.create_kernel_relation_claim_service(session),  # type: ignore[attr-defined]
                claim_participant_service=projection_factory.create_kernel_claim_participant_service(session),  # type: ignore[attr-defined]
                claim_relation_service=projection_factory.create_kernel_claim_relation_service(session),  # type: ignore[attr-defined]
                claim_evidence_service=projection_factory.create_kernel_claim_evidence_service(session),  # type: ignore[attr-defined]
                source_document_lookup=core_factory._build_source_document_reference_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
                view_extension=GRAPH_SERVICE_VIEW_CONFIG,
            ),
        )

    def create_kernel_reasoning_path_service(
        self,
        session: Session,
    ) -> KernelReasoningPathService:
        core_factory = self._require_core_factory()
        projection_factory = self._require_projection_factory()
        return KernelReasoningPathService(
            reasoning_path_repo=core_factory._build_reasoning_path_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
            relation_claim_service=projection_factory.create_kernel_relation_claim_service(session),  # type: ignore[attr-defined]
            claim_participant_service=projection_factory.create_kernel_claim_participant_service(session),  # type: ignore[attr-defined]
            claim_evidence_service=projection_factory.create_kernel_claim_evidence_service(session),  # type: ignore[attr-defined]
            claim_relation_service=projection_factory.create_kernel_claim_relation_service(session),  # type: ignore[attr-defined]
            relation_service=core_factory.create_kernel_relation_service(session),  # type: ignore[attr-defined]
            read_model_update_dispatcher=build_graph_read_model_update_dispatcher(
                session,
            ),
            session=session,
            space_registry_port=core_factory._build_space_registry_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
        )

    def create_kernel_claim_projection_readiness_service(
        self,
        session: Session,
    ) -> KernelClaimProjectionReadinessService:
        projection_factory = self._require_projection_factory()
        return KernelClaimProjectionReadinessService(
            session=session,
            relation_projection_invariant_service=projection_factory.create_kernel_relation_projection_invariant_service(session),  # type: ignore[attr-defined]
            relation_projection_materialization_service=projection_factory.create_kernel_relation_projection_materialization_service(session),  # type: ignore[attr-defined]
            claim_participant_backfill_service=self.create_kernel_claim_participant_backfill_service(
                session,
            ),
        )

    def create_kernel_claim_participant_backfill_service(
        self,
        session: Session,
    ) -> KernelClaimParticipantBackfillService:
        core_factory = self._require_core_factory()
        projection_factory = self._require_projection_factory()
        return KernelClaimParticipantBackfillService(
            session=session,
            relation_claim_service=projection_factory.create_kernel_relation_claim_service(session),  # type: ignore[attr-defined]
            claim_participant_service=projection_factory.create_kernel_claim_participant_service(session),  # type: ignore[attr-defined]
            entity_repository=core_factory._build_entity_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
            concept_service=core_factory.create_concept_management_service(session),  # type: ignore[attr-defined]
            reasoning_path_service=self.create_kernel_reasoning_path_service(session),
        )

    def create_hypothesis_generation_service(
        self,
        session: Session,
    ) -> HypothesisGenerationService:
        core_factory = self._require_core_factory()
        projection_factory = self._require_projection_factory()
        dictionary_service = core_factory.create_dictionary_management_service(
            session,
        )  # type: ignore[attr-defined]
        graph_domain_pack = create_graph_domain_pack()
        graph_domain_ai_config = create_graph_domain_ai_config(graph_domain_pack.name)
        relation_repository = core_factory._build_relation_repository(session)  # type: ignore[attr-defined]  # noqa: SLF001
        graph_query_service = core_factory._build_graph_query_repository(session)  # type: ignore[attr-defined]  # noqa: SLF001
        model_spec = get_model_registry().get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
        )
        graph_connection_agent = ArtanaGraphConnectionAdapter(
            model=model_spec.model_id,
            prompt_config=graph_domain_ai_config.graph_connection_prompt,
            dictionary_service=dictionary_service,
            graph_query_service=graph_query_service,
            relation_repository=relation_repository,
        )
        return HypothesisGenerationService(
            dependencies=HypothesisGenerationServiceDependencies(
                graph_connection_agent=graph_connection_agent,
                relation_claim_service=projection_factory.create_kernel_relation_claim_service(session),  # type: ignore[attr-defined]
                claim_participant_service=projection_factory.create_kernel_claim_participant_service(session),  # type: ignore[attr-defined]
                claim_evidence_service=projection_factory.create_kernel_claim_evidence_service(session),  # type: ignore[attr-defined]
                entity_repository=core_factory._build_entity_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
                relation_repository=relation_repository,
                dictionary_service=dictionary_service,
                reasoning_path_service=self.create_kernel_reasoning_path_service(
                    session,
                ),
            ),
        )


__all__ = ["KernelReasoningHypothesisServiceFactoryMixin"]
