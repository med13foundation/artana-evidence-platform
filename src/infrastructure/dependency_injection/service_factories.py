# mypy: disable-error-code=no-untyped-def
"""
Factory mixin for building application services used by the dependency container.
"""

from __future__ import annotations

import logging
import os
from contextlib import suppress
from typing import TYPE_CHECKING

from artana_evidence_db.runtime import GraphDomainPack, create_graph_domain_pack

from src.application.agents.services import (
    ContentEnrichmentService,
    ContentEnrichmentServiceDependencies,
    EntityRecognitionService,
    EntityRecognitionServiceDependencies,
    ExtractionService,
    ExtractionServiceDependencies,
    GovernanceService,
)
from src.application.services.pipeline_run_trace_service import (
    PipelineRunTraceService,
)
from src.domain.agents.models import ModelCapability
from src.infrastructure.dependency_injection import (
    analysis_service_factories,
    curation_service_factories,
    discovery_service_factories,
    kernel_service_factories,
)
from src.infrastructure.dependency_injection._graph_runtime_builders import (
    build_graph_connection_service,
    build_graph_search_service,
)
from src.infrastructure.factories.ingestion_pipeline_factory import (
    create_ingestion_pipeline,
)
from src.infrastructure.llm.adapters import (
    ArtanaContentEnrichmentAdapter,
    ArtanaEntityRecognitionAdapter,
    ArtanaEvidenceSentenceHarnessAdapter,
    ArtanaExtractionAdapter,
    ArtanaExtractionPolicyAdapter,
    ArtanaMappingJudgeAdapter,
    ArtanaQueryAgentAdapter,
)
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.graph_domain_ai_config import create_graph_domain_ai_config
from src.infrastructure.repositories import (
    SqlAlchemyPipelineRunEventRepository,
    SqlAlchemyResearchSpaceRepository,
    SqlAlchemySourceDocumentRepository,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from artana.store import PostgresStore
    from artana_evidence_db.evidence_sentence_harness_port import (
        EvidenceSentenceHarnessPort,
    )
    from sqlalchemy.orm import Session

    from src.application.agents.services import (
        GraphConnectionService,
        GraphSearchService,
    )
    from src.application.services import SystemStatusService
    from src.domain.agents.graph_domain_ai_contracts import GraphDomainAiConfig
    from src.domain.agents.ports import (
        EntityRecognitionPort,
        ExtractionAgentPort,
        GraphConnectionPort,
        QueryAgentPort,
    )
    from src.domain.agents.ports.mapping_judge_port import MappingJudgePort
    from src.domain.repositories.pipeline_run_event_repository import (
        PipelineRunEventRepository,
    )
    from src.domain.repositories.source_document_repository import (
        SourceDocumentRepository,
    )
    from src.domain.services import storage_metrics, storage_providers


class ApplicationServiceFactoryMixin(
    analysis_service_factories.AnalysisServiceFactoryMixin,
    curation_service_factories.CurationServiceFactoryMixin,
    discovery_service_factories.DiscoveryServiceFactoryMixin,
    kernel_service_factories.KernelServiceFactoryMixin,
):
    """Provides helper factory methods shared by the dependency container."""

    if TYPE_CHECKING:
        _storage_plugin_registry: storage_providers.StoragePluginRegistry
        _storage_metrics_recorder: storage_metrics.StorageMetricsRecorder
        _entity_recognition_agent: EntityRecognitionPort | None
        _extraction_agent: ExtractionAgentPort | None
        _graph_domain_pack: GraphDomainPack | None
        _graph_domain_ai_config: GraphDomainAiConfig | None
        _mapping_judge_agent: MappingJudgePort | None
        _graph_connection_agent: GraphConnectionPort | None
        _query_agent: QueryAgentPort | None

    if TYPE_CHECKING:

        def get_system_status_service(self) -> SystemStatusService: ...

        def get_artana_store(self) -> PostgresStore: ...

    _logger = logging.getLogger(__name__)

    def get_query_agent(self) -> QueryAgentPort:
        if self._query_agent is None:
            registry = get_model_registry()
            model_spec = registry.get_default_model(ModelCapability.QUERY_GENERATION)
            self._query_agent = ArtanaQueryAgentAdapter(
                model=model_spec.model_id,
            )
        return self._query_agent

    @staticmethod
    def _build_review_queue_submitter(
        session: Session,
    ) -> Callable[[str, str, str | None, str], None]:
        from src.application.curation.repositories.review_repository import (
            SqlAlchemyReviewRepository,
        )
        from src.application.curation.services.review_service import ReviewService

        repository = SqlAlchemyReviewRepository()
        review_service = ReviewService(repository)

        def submit_review_item(
            entity_type: str,
            entity_id: str,
            research_space_id: str | None,
            priority: str,
        ) -> None:
            try:
                existing = repository.find_by_entity(
                    session,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    research_space_id=research_space_id,
                )
                if existing is not None:
                    existing_status = str(existing.get("status", "")).strip().lower()
                    if existing_status == "pending":
                        return
                review_service.submit(
                    session,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    priority=priority,
                    research_space_id=research_space_id,
                )
            except Exception as exc:  # noqa: BLE001
                with suppress(Exception):
                    session.rollback()
                ApplicationServiceFactoryMixin._logger.warning(
                    "Review queue submit skipped due to repository error: %s",
                    exc,
                )

        return submit_review_item

    @staticmethod
    def _is_stage_enabled(flag_name: str) -> bool:
        return os.getenv(flag_name, "1").strip() == "1"

    def _get_graph_domain_pack(self) -> GraphDomainPack:
        graph_domain_pack = getattr(self, "_graph_domain_pack", None)
        if graph_domain_pack is None:
            graph_domain_pack = create_graph_domain_pack()
            self._graph_domain_pack = graph_domain_pack
        return graph_domain_pack

    def _get_graph_domain_ai_config(self) -> GraphDomainAiConfig:
        graph_domain_pack = self._get_graph_domain_pack()
        graph_domain_ai_config = getattr(self, "_graph_domain_ai_config", None)
        if (
            graph_domain_ai_config is None
            or graph_domain_ai_config.pack_name != graph_domain_pack.name
        ):
            graph_domain_ai_config = create_graph_domain_ai_config(
                graph_domain_pack.name,
            )
            self._graph_domain_ai_config = graph_domain_ai_config
        return graph_domain_ai_config

    def get_entity_recognition_agent(self) -> EntityRecognitionPort:
        if self._entity_recognition_agent is None:
            registry = get_model_registry()
            model_spec = registry.get_default_model(
                ModelCapability.EVIDENCE_EXTRACTION,
            )
            graph_domain_ai_config = self._get_graph_domain_ai_config()
            self._entity_recognition_agent = ArtanaEntityRecognitionAdapter(
                model=model_spec.model_id,
                prompt_config=graph_domain_ai_config.entity_recognition_prompt,
                payload_config=graph_domain_ai_config.entity_recognition_payload,
            )
        return self._entity_recognition_agent

    def get_extraction_agent(self) -> ExtractionAgentPort:
        if self._extraction_agent is None:
            registry = get_model_registry()
            model_spec = registry.get_default_model(
                ModelCapability.EVIDENCE_EXTRACTION,
            )
            graph_domain_ai_config = self._get_graph_domain_ai_config()
            self._extraction_agent = ArtanaExtractionAdapter(
                model=model_spec.model_id,
                prompt_config=graph_domain_ai_config.extraction_prompt,
                payload_config=graph_domain_ai_config.extraction_payload,
            )
        return self._extraction_agent

    def get_mapping_judge_agent(self) -> MappingJudgePort | None:
        if not self._is_stage_enabled("ARTANA_ENABLE_ENDPOINT_SHAPE_AGENT"):
            return None
        if self._mapping_judge_agent is not None:
            return self._mapping_judge_agent
        registry = get_model_registry()
        model_spec = registry.get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
        )
        try:
            self._mapping_judge_agent = ArtanaMappingJudgeAdapter(
                model=model_spec.model_id,
            )
        except Exception as exc:  # noqa: BLE001 - fail-closed to deterministic guard
            self._logger.warning(
                "Endpoint-shape mapping judge unavailable, using deterministic guard only: %s",
                exc,
            )
            self._mapping_judge_agent = None
        return self._mapping_judge_agent

    def create_ingestion_pipeline(
        self,
        session: Session,
    ):
        """Build the ingestion pipeline through the legacy factory wrapper."""
        return create_ingestion_pipeline(session)

    def create_entity_recognition_service(
        self,
        session: Session,
        *,
        include_extraction_stage: bool = True,
        source_document_repository: SourceDocumentRepository | None = None,
        pipeline_run_event_repository: PipelineRunEventRepository | None = None,
    ) -> EntityRecognitionService:
        dictionary_service = self.create_dictionary_management_service(session)
        concept_service = self.create_concept_management_service(session)
        governance_service = GovernanceService()
        ingestion_pipeline = self.create_ingestion_pipeline(session)
        registry = get_model_registry()
        model_spec = registry.get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
        )
        graph_domain_ai_config = self._get_graph_domain_ai_config()
        entity_recognition_agent = ArtanaEntityRecognitionAdapter(
            model=model_spec.model_id,
            prompt_config=graph_domain_ai_config.entity_recognition_prompt,
            payload_config=graph_domain_ai_config.entity_recognition_payload,
            dictionary_service=dictionary_service,
        )
        extraction_agent = ArtanaExtractionAdapter(
            model=model_spec.model_id,
            prompt_config=graph_domain_ai_config.extraction_prompt,
            payload_config=graph_domain_ai_config.extraction_payload,
            dictionary_service=dictionary_service,
        )
        extraction_policy_agent = ArtanaExtractionPolicyAdapter(
            model=model_spec.model_id,
        )
        evidence_sentence_harness = self._create_evidence_sentence_harness(
            model_id=model_spec.model_id,
        )
        extraction_service = (
            ExtractionService(
                dependencies=ExtractionServiceDependencies(
                    extraction_agent=extraction_agent,
                    extraction_policy_agent=extraction_policy_agent,
                    ingestion_pipeline=ingestion_pipeline,
                    relation_repository=self._build_relation_repository(session),
                    relation_claim_repository=self._build_relation_claim_repository(
                        session,
                    ),
                    relation_projection_source_repository=(
                        self._build_relation_projection_source_repository(session)
                    ),
                    relation_projection_materialization_service=(
                        self.create_kernel_relation_projection_materialization_service(
                            session,
                        )
                    ),
                    claim_participant_repository=(
                        self._build_claim_participant_repository(session)
                    ),
                    claim_evidence_repository=self._build_claim_evidence_repository(
                        session,
                    ),
                    entity_repository=self._build_entity_repository(session),
                    dictionary_service=dictionary_service,
                    concept_service=concept_service,
                    evidence_sentence_harness=evidence_sentence_harness,
                    endpoint_shape_judge=self.get_mapping_judge_agent(),
                    concept_merge_judge=self.get_mapping_judge_agent(),
                    governance_service=governance_service,
                    review_queue_submitter=self._build_review_queue_submitter(session),
                    rollback_on_error=session.rollback,
                ),
            )
            if include_extraction_stage
            else None
        )

        return EntityRecognitionService(
            dependencies=EntityRecognitionServiceDependencies(
                entity_recognition_agent=entity_recognition_agent,
                source_document_repository=(
                    source_document_repository
                    or SqlAlchemySourceDocumentRepository(session)
                ),
                ingestion_pipeline=ingestion_pipeline,
                dictionary_service=dictionary_service,
                entity_recognition_bootstrap=(
                    graph_domain_ai_config.entity_recognition_bootstrap
                ),
                extraction_service=extraction_service,
                governance_service=governance_service,
                research_space_repository=SqlAlchemyResearchSpaceRepository(session),
                pipeline_trace_service=PipelineRunTraceService(
                    session,
                    event_repository=(
                        pipeline_run_event_repository
                        or SqlAlchemyPipelineRunEventRepository(session)
                    ),
                ),
            ),
            default_shadow_mode=False,
        )

    def create_extraction_service(self, session: Session) -> ExtractionService:
        dictionary_service = self.create_dictionary_management_service(session)
        concept_service = self.create_concept_management_service(session)
        registry = get_model_registry()
        model_spec = registry.get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
        )
        graph_domain_ai_config = self._get_graph_domain_ai_config()
        extraction_agent = ArtanaExtractionAdapter(
            model=model_spec.model_id,
            prompt_config=graph_domain_ai_config.extraction_prompt,
            payload_config=graph_domain_ai_config.extraction_payload,
            dictionary_service=dictionary_service,
        )
        extraction_policy_agent = ArtanaExtractionPolicyAdapter(
            model=model_spec.model_id,
        )
        evidence_sentence_harness = self._create_evidence_sentence_harness(
            model_id=model_spec.model_id,
        )
        return ExtractionService(
            dependencies=ExtractionServiceDependencies(
                extraction_agent=extraction_agent,
                extraction_policy_agent=extraction_policy_agent,
                ingestion_pipeline=self.create_ingestion_pipeline(session),
                relation_repository=self._build_relation_repository(session),
                relation_claim_repository=self._build_relation_claim_repository(
                    session,
                ),
                relation_projection_source_repository=(
                    self._build_relation_projection_source_repository(session)
                ),
                claim_participant_repository=(
                    self._build_claim_participant_repository(session)
                ),
                claim_evidence_repository=self._build_claim_evidence_repository(
                    session,
                ),
                entity_repository=self._build_entity_repository(session),
                dictionary_service=dictionary_service,
                concept_service=concept_service,
                evidence_sentence_harness=evidence_sentence_harness,
                endpoint_shape_judge=self.get_mapping_judge_agent(),
                concept_merge_judge=self.get_mapping_judge_agent(),
                governance_service=GovernanceService(),
                review_queue_submitter=self._build_review_queue_submitter(session),
                rollback_on_error=session.rollback,
            ),
        )

    def _create_evidence_sentence_harness(
        self,
        *,
        model_id: str | None,
    ) -> EvidenceSentenceHarnessPort | None:
        try:
            return ArtanaEvidenceSentenceHarnessAdapter(
                model=model_id,
            )
        except Exception as exc:  # noqa: BLE001 - fail-open for optional path
            self._logger.warning(
                "Evidence sentence harness unavailable; optional relation sentence fallback disabled: %s",
                exc,
            )
            return None

    def create_graph_connection_service(
        self,
        session: Session,
    ) -> GraphConnectionService:
        return build_graph_connection_service(session)

    def create_graph_search_service(self, session: Session) -> GraphSearchService:
        return build_graph_search_service(session)

    def create_content_enrichment_service(
        self,
        session: Session,
    ) -> ContentEnrichmentService:
        content_enrichment_agent = None
        if self._is_stage_enabled("ARTANA_ENABLE_CONTENT_ENRICHMENT_AGENT"):
            registry = get_model_registry()
            model_spec = registry.get_default_model(
                ModelCapability.EVIDENCE_EXTRACTION,
            )
            content_enrichment_agent = ArtanaContentEnrichmentAdapter(
                model=model_spec.model_id,
            )
        return ContentEnrichmentService(
            dependencies=ContentEnrichmentServiceDependencies(
                source_document_repository=SqlAlchemySourceDocumentRepository(session),
                content_enrichment_agent=content_enrichment_agent,
                storage_coordinator=self.create_storage_operation_coordinator(session),
                pipeline_trace_service=PipelineRunTraceService(
                    session,
                    event_repository=SqlAlchemyPipelineRunEventRepository(session),
                ),
            ),
        )
