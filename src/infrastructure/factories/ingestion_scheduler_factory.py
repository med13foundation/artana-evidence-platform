"""Factory helpers for ingestion scheduling service wiring."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from src.application.services import (
    ClinicalTrialsIngestionService,
    ClinVarIngestionService,
    ExtractionQueueService,
    ExtractionRunnerService,
    HGNCIngestionService,
    IngestionSchedulingOptions,
    IngestionSchedulingService,
    MarrvelIngestionService,
    MGIIngestionService,
    PubMedDiscoveryService,
    PubMedIngestionDependencies,
    PubMedIngestionService,
    PubMedQueryBuilder,
    StorageConfigurationService,
    StorageOperationCoordinator,
    ZFINIngestionService,
)
from src.database.session import SessionLocal, set_session_rls_context
from src.domain.entities.user_data_source import SourceType, UserDataSource
from src.infrastructure.data_sources import (
    ClinicalTrialsSourceGateway,
    ClinVarSourceGateway,
    HGNCSourceGateway,
    MarrvelSourceGateway,
    MGISourceGateway,
    PubMedSourceGateway,
    SimplePubMedPdfGateway,
    ZFINSourceGateway,
    create_pubmed_search_gateway,
)
from src.infrastructure.factories.ingestion_pipeline_factory import (
    create_ingestion_pipeline,
)
from src.infrastructure.factories.ingestion_processor_registry import (
    build_processor_registry,
)
from src.infrastructure.factories.ingestion_scheduler_config import (
    DEFAULT_INGESTION_JOB_HARD_TIMEOUT_SECONDS,
    DEFAULT_POST_INGESTION_GRAPH_SEED_TIMEOUT_SECONDS,
    DEFAULT_POST_INGESTION_HOOK_TIMEOUT_SECONDS,
    DEFAULT_SCHEDULER_HEARTBEAT_SECONDS,
    DEFAULT_SCHEDULER_LEASE_TTL_SECONDS,
    DEFAULT_SCHEDULER_STALE_RUNNING_TIMEOUT_SECONDS,
    ENV_ENABLE_POST_INGESTION_GRAPH_STAGE,
    ENV_ENABLE_POST_INGESTION_PIPELINE_HOOK,
    ENV_INGESTION_JOB_HARD_TIMEOUT_SECONDS,
    ENV_POST_INGESTION_GRAPH_SEED_TIMEOUT_SECONDS,
    ENV_POST_INGESTION_HOOK_TIMEOUT_SECONDS,
    ENV_SCHEDULER_HEARTBEAT_SECONDS,
    ENV_SCHEDULER_LEASE_TTL_SECONDS,
    ENV_SCHEDULER_STALE_RUNNING_TIMEOUT_SECONDS,
    read_bool_env,
    read_positive_int_env,
    resolve_scheduler_backend,
)
from src.infrastructure.factories.ingestion_scheduler_ontology import (
    run_ontology_ingestion,
)
from src.infrastructure.factories.ingestion_scheduler_post_ingestion import (
    build_post_ingestion_hook,
)
from src.infrastructure.llm.adapters.pubmed_relevance_agent_adapter import (
    ArtanaPubMedRelevanceAdapter,
)
from src.infrastructure.llm.adapters.query_agent_adapter import ArtanaQueryAgentAdapter
from src.infrastructure.repositories import (
    SQLAlchemyDiscoverySearchJobRepository,
    SqlAlchemyExtractionQueueRepository,
    SqlAlchemyIngestionJobRepository,
    SqlAlchemyIngestionSourceLockRepository,
    SqlAlchemyPublicationExtractionRepository,
    SqlAlchemyPublicationRepository,
    SqlAlchemyResearchSpaceRepository,
    SqlAlchemySourceDocumentRepository,
    SqlAlchemySourceRecordLedgerRepository,
    SqlAlchemySourceSyncStateRepository,
    SqlAlchemyStorageConfigurationRepository,
    SqlAlchemyStorageOperationRepository,
    SqlAlchemyUserDataSourceRepository,
)
from src.infrastructure.storage import initialize_storage_plugins

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator

    from sqlalchemy.orm import Session

    from src.application.services.ports.scheduler_port import SchedulerPort
    from src.application.services.structured_source_aliases import (
        StructuredSourceAliasWriter,
    )
    from src.domain.services.ingestion import (
        IngestionRunContext,
        IngestionRunSummary,
    )


def build_ingestion_scheduling_service(  # noqa: C901, PLR0915
    *,
    session: Session,
    scheduler: SchedulerPort | None = None,
) -> IngestionSchedulingService:
    """Create a fully wired ingestion scheduling service for the current session."""
    resolved_scheduler = scheduler or resolve_scheduler_backend()

    publication_repository = SqlAlchemyPublicationRepository(session)
    user_source_repository = SqlAlchemyUserDataSourceRepository(session)
    job_repository = SqlAlchemyIngestionJobRepository(session)
    research_space_repository = SqlAlchemyResearchSpaceRepository(session)

    storage_configuration_repository = SqlAlchemyStorageConfigurationRepository(
        session,
    )
    storage_operation_repository = SqlAlchemyStorageOperationRepository(session)
    source_sync_state_repository = SqlAlchemySourceSyncStateRepository(session)
    source_record_ledger_repository = SqlAlchemySourceRecordLedgerRepository(session)
    source_lock_repository = SqlAlchemyIngestionSourceLockRepository(session)
    source_document_repository = SqlAlchemySourceDocumentRepository(session)
    storage_service = StorageConfigurationService(
        configuration_repository=storage_configuration_repository,
        operation_repository=storage_operation_repository,
        plugin_registry=initialize_storage_plugins(),
    )
    storage_coordinator = StorageOperationCoordinator(storage_service)
    extraction_queue_repository = SqlAlchemyExtractionQueueRepository(session)
    extraction_queue_service = ExtractionQueueService(
        queue_repository=extraction_queue_repository,
    )
    extraction_repository = SqlAlchemyPublicationExtractionRepository(session)
    extraction_runner_service = ExtractionRunnerService(
        queue_repository=extraction_queue_repository,
        publication_repository=publication_repository,
        extraction_repository=extraction_repository,
        processor_registry=build_processor_registry(),
        storage_coordinator=storage_coordinator,
    )
    post_ingestion_hook = None
    if read_bool_env(ENV_ENABLE_POST_INGESTION_PIPELINE_HOOK, default=True):
        enable_post_ingestion_graph_stage = read_bool_env(
            ENV_ENABLE_POST_INGESTION_GRAPH_STAGE,
            default=True,
        )
        post_ingestion_graph_seed_timeout_seconds = read_positive_int_env(
            ENV_POST_INGESTION_GRAPH_SEED_TIMEOUT_SECONDS,
            default=DEFAULT_POST_INGESTION_GRAPH_SEED_TIMEOUT_SECONDS,
        )
        post_ingestion_hook = build_post_ingestion_hook(
            enable_post_ingestion_graph_stage=enable_post_ingestion_graph_stage,
            graph_seed_timeout_seconds=post_ingestion_graph_seed_timeout_seconds,
        )

    # Initialize Query Agent
    query_agent = ArtanaQueryAgentAdapter()
    pubmed_relevance_agent = ArtanaPubMedRelevanceAdapter()

    pipeline = create_ingestion_pipeline(session)
    structured_source_alias_writer = _build_structured_source_alias_writer(session)

    pubmed_service = PubMedIngestionService(
        gateway=PubMedSourceGateway(
            relevance_agent=pubmed_relevance_agent,
        ),
        pipeline=pipeline,
        dependencies=PubMedIngestionDependencies(
            publication_repository=publication_repository,
            storage_service=storage_service,
            query_agent=query_agent,
            research_space_repository=research_space_repository,
            source_document_repository=source_document_repository,
        ),
    )
    clinvar_service = ClinVarIngestionService(
        gateway=ClinVarSourceGateway(),
        pipeline=pipeline,
        storage_service=storage_service,
        source_document_repository=source_document_repository,
    )
    marrvel_service = MarrvelIngestionService(
        gateway=MarrvelSourceGateway(),
        pipeline=pipeline,
        storage_service=storage_service,
        source_document_repository=source_document_repository,
    )

    discovery_job_repository = SQLAlchemyDiscoverySearchJobRepository(session)
    query_builder = PubMedQueryBuilder()
    search_gateway = create_pubmed_search_gateway(query_builder)
    pdf_gateway = SimplePubMedPdfGateway()
    pubmed_discovery_service = PubMedDiscoveryService(
        job_repository=discovery_job_repository,
        query_builder=query_builder,
        search_gateway=search_gateway,
        pdf_gateway=pdf_gateway,
        storage_coordinator=storage_coordinator,
    )

    async def _run_pubmed_ingestion(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> IngestionRunSummary:
        return await pubmed_service.ingest(source, context=context)

    async def _run_clinvar_ingestion(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> IngestionRunSummary:
        return await clinvar_service.ingest(source, context=context)

    async def _run_marrvel_ingestion(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> IngestionRunSummary:
        return await marrvel_service.ingest(source, context=context)

    async def _run_ontology_ingestion(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
        gateway_factory: Callable[[], object] | None = None,
    ) -> IngestionRunSummary:
        return await run_ontology_ingestion(
            source,
            context=context,
            gateway_factory=gateway_factory,
        )

    async def _run_hpo_ingestion(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> IngestionRunSummary:
        from src.infrastructure.ingest.hpo_gateway import HPOGateway

        return await _run_ontology_ingestion(
            source,
            context=context,
            gateway_factory=HPOGateway,
        )

    async def _run_uberon_ingestion(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> IngestionRunSummary:
        from src.infrastructure.ingest.uberon_gateway import UberonGateway

        return await _run_ontology_ingestion(
            source,
            context=context,
            gateway_factory=UberonGateway,
        )

    async def _run_cell_ontology_ingestion(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> IngestionRunSummary:
        from src.infrastructure.ingest.cell_ontology_gateway import (
            CellOntologyGateway,
        )

        return await _run_ontology_ingestion(
            source,
            context=context,
            gateway_factory=CellOntologyGateway,
        )

    async def _run_gene_ontology_ingestion(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> IngestionRunSummary:
        from src.infrastructure.ingest.gene_ontology_gateway import (
            GeneOntologyGateway,
        )

        return await _run_ontology_ingestion(
            source,
            context=context,
            gateway_factory=GeneOntologyGateway,
        )

    async def _run_mondo_ingestion(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> IngestionRunSummary:
        from src.infrastructure.ingest.mondo_gateway import MondoGateway

        return await _run_ontology_ingestion(
            source,
            context=context,
            gateway_factory=MondoGateway,
        )

    async def _run_drugbank_ingestion(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> IngestionRunSummary:
        from src.application.services.drugbank_ingestion_service import (
            DrugBankIngestionService,
        )
        from src.infrastructure.data_sources.drugbank_gateway import (
            DrugBankSourceGateway,
        )

        service = DrugBankIngestionService(
            gateway=DrugBankSourceGateway(),
            pipeline=pipeline,
            alias_writer=structured_source_alias_writer,
        )
        return await service.ingest(source, context=context)  # type: ignore[return-value]

    async def _run_alphafold_ingestion(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> IngestionRunSummary:
        from src.application.services.alphafold_ingestion_service import (
            AlphaFoldIngestionService,
        )
        from src.infrastructure.data_sources.alphafold_gateway import (
            AlphaFoldSourceGateway,
        )

        service = AlphaFoldIngestionService(
            gateway=AlphaFoldSourceGateway(),
            pipeline=pipeline,
        )
        return await service.ingest(source, context=context)  # type: ignore[return-value]

    async def _run_uniprot_ingestion(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> IngestionRunSummary:
        from src.application.services.uniprot_ingestion_service import (
            UniProtIngestionService,
        )
        from src.infrastructure.data_sources.uniprot_gateway import (
            UniProtSourceGateway,
        )

        service = UniProtIngestionService(
            gateway=UniProtSourceGateway(),
            pipeline=pipeline,
            alias_writer=structured_source_alias_writer,
        )
        return await service.ingest(source, context=context)  # type: ignore[return-value]

    async def _run_hgnc_ingestion(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> IngestionRunSummary:
        service = HGNCIngestionService(
            gateway=HGNCSourceGateway(),
            alias_writer=structured_source_alias_writer,
        )
        return await service.ingest(source, context=context)

    async def _run_clinical_trials_ingestion(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> IngestionRunSummary:
        service = ClinicalTrialsIngestionService(
            gateway=ClinicalTrialsSourceGateway(),
            pipeline=pipeline,
            source_document_repository=source_document_repository,
        )
        return await service.ingest(source, context=context)

    async def _run_mgi_ingestion(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> IngestionRunSummary:
        service = MGIIngestionService(
            gateway=MGISourceGateway(),
            pipeline=pipeline,
            source_document_repository=source_document_repository,
        )
        return await service.ingest(source, context=context)

    async def _run_zfin_ingestion(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> IngestionRunSummary:
        service = ZFINIngestionService(
            gateway=ZFINSourceGateway(),
            pipeline=pipeline,
            source_document_repository=source_document_repository,
        )
        return await service.ingest(source, context=context)

    scheduler_heartbeat_seconds = read_positive_int_env(
        ENV_SCHEDULER_HEARTBEAT_SECONDS,
        default=DEFAULT_SCHEDULER_HEARTBEAT_SECONDS,
    )
    scheduler_lease_ttl_seconds = read_positive_int_env(
        ENV_SCHEDULER_LEASE_TTL_SECONDS,
        default=DEFAULT_SCHEDULER_LEASE_TTL_SECONDS,
    )
    scheduler_stale_running_timeout_seconds = read_positive_int_env(
        ENV_SCHEDULER_STALE_RUNNING_TIMEOUT_SECONDS,
        default=DEFAULT_SCHEDULER_STALE_RUNNING_TIMEOUT_SECONDS,
    )
    ingestion_job_hard_timeout_seconds = read_positive_int_env(
        ENV_INGESTION_JOB_HARD_TIMEOUT_SECONDS,
        default=DEFAULT_INGESTION_JOB_HARD_TIMEOUT_SECONDS,
    )
    post_ingestion_hook_timeout_seconds = read_positive_int_env(
        ENV_POST_INGESTION_HOOK_TIMEOUT_SECONDS,
        default=DEFAULT_POST_INGESTION_HOOK_TIMEOUT_SECONDS,
    )

    ingestion_services: dict[
        SourceType,
        Callable[..., Awaitable[IngestionRunSummary]],
    ] = {
        SourceType.PUBMED: _run_pubmed_ingestion,
        SourceType.CLINVAR: _run_clinvar_ingestion,
        SourceType.MARRVEL: _run_marrvel_ingestion,
        SourceType.HPO: _run_hpo_ingestion,
        SourceType.UBERON: _run_uberon_ingestion,
        SourceType.CELL_ONTOLOGY: _run_cell_ontology_ingestion,
        SourceType.GENE_ONTOLOGY: _run_gene_ontology_ingestion,
        SourceType.MONDO: _run_mondo_ingestion,
        SourceType.DRUGBANK: _run_drugbank_ingestion,
        SourceType.ALPHAFOLD: _run_alphafold_ingestion,
        SourceType.UNIPROT: _run_uniprot_ingestion,
        SourceType.HGNC: _run_hgnc_ingestion,
        SourceType.CLINICAL_TRIALS: _run_clinical_trials_ingestion,
        SourceType.MGI: _run_mgi_ingestion,
        SourceType.ZFIN: _run_zfin_ingestion,
    }

    return IngestionSchedulingService(
        scheduler=resolved_scheduler,
        source_repository=user_source_repository,
        job_repository=job_repository,
        ingestion_services=ingestion_services,
        options=IngestionSchedulingOptions(
            storage_operation_repository=storage_operation_repository,
            pubmed_discovery_service=pubmed_discovery_service,
            extraction_queue_service=extraction_queue_service,
            extraction_runner_service=extraction_runner_service,
            source_sync_state_repository=source_sync_state_repository,
            source_record_ledger_repository=source_record_ledger_repository,
            source_lock_repository=source_lock_repository,
            scheduler_heartbeat_seconds=scheduler_heartbeat_seconds,
            scheduler_lease_ttl_seconds=scheduler_lease_ttl_seconds,
            scheduler_stale_running_timeout_seconds=(
                scheduler_stale_running_timeout_seconds
            ),
            ingestion_job_hard_timeout_seconds=ingestion_job_hard_timeout_seconds,
            post_ingestion_hook_timeout_seconds=post_ingestion_hook_timeout_seconds,
            post_ingestion_hook=post_ingestion_hook,
        ),
    )


def _build_structured_source_alias_writer(
    session: Session,
) -> StructuredSourceAliasWriter:
    """Build the graph-backed alias writer for structured source ingestion."""
    from artana_evidence_db.composition import build_entity_repository
    from artana_evidence_db.entity_service import KernelEntityService
    from artana_evidence_db.governance import build_dictionary_repository
    from artana_evidence_db.graph_domain_config import (
        GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG,
    )

    from src.infrastructure.ingestion.structured_source_alias_writer import (
        KernelStructuredSourceAliasWriter,
    )

    entity_repository = build_entity_repository(session)
    dictionary_repository = build_dictionary_repository(
        session,
        dictionary_loading_extension=GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG,
    )
    entity_service = KernelEntityService(
        entity_repo=entity_repository,
        dictionary_repo=dictionary_repository,
    )
    return KernelStructuredSourceAliasWriter(
        entity_service=entity_service,
        entity_repository=entity_repository,
    )


@contextmanager
def ingestion_scheduling_service_context(
    *,
    session: Session | None = None,
    scheduler: SchedulerPort | None = None,
) -> Iterator[IngestionSchedulingService]:
    """Context manager that yields a scheduling service and closes the session."""
    local_session = session or SessionLocal()
    if session is None:
        set_session_rls_context(local_session, bypass_rls=True)
    try:
        service = build_ingestion_scheduling_service(
            session=local_session,
            scheduler=scheduler,
        )
        yield service
    finally:
        if session is None:
            local_session.close()
