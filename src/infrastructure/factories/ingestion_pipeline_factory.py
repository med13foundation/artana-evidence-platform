"""
Factory for creating the ingestion pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.infrastructure.embeddings import HybridTextEmbeddingProvider
from src.infrastructure.ingestion.mapping import (
    ExactMapper,
    HybridMapper,
    LLMJudgeMapper,
    VectorMapper,
)
from src.infrastructure.ingestion.normalization.composite_normalizer import (
    CompositeNormalizer,
)
from src.infrastructure.ingestion.normalization.unit_converter import UnitConverter
from src.infrastructure.ingestion.normalization.value_caster import ValueCaster
from src.infrastructure.ingestion.pipeline import IngestionPipeline
from src.infrastructure.ingestion.provenance.tracker import ProvenanceTracker
from src.infrastructure.ingestion.resolution.entity_resolver import EntityResolver
from src.infrastructure.ingestion.validation.observation_validator import (
    ObservationValidator,
)

if TYPE_CHECKING:
    from artana_evidence_db.governance_ports import (
        DictionarySearchHarnessPort,
    )
    from sqlalchemy.orm import Session

    from src.domain.agents.ports.mapping_judge_port import MappingJudgePort
    from src.infrastructure.ingestion.interfaces import Mapper


def create_ingestion_pipeline(
    session: Session,
    *,
    mapping_judge_agent: MappingJudgePort | None = None,
    dictionary_search_harness: DictionarySearchHarnessPort | None = None,
) -> IngestionPipeline:
    """
    Create a fully wired ingestion pipeline.
    """
    from src.infrastructure.dependency_injection.dependencies import (
        get_legacy_dependency_container,
    )

    legacy_container = get_legacy_dependency_container()
    active_mapping_judge_agent = mapping_judge_agent
    if active_mapping_judge_agent is None:
        from src.infrastructure.llm.adapters.mapping_judge_agent_adapter import (
            ArtanaMappingJudgeAdapter,
        )
        from src.infrastructure.llm.config import resolve_artana_state_uri

        # Validate state backend eagerly so factory fails fast when Artana cannot run.
        resolve_artana_state_uri()
        active_mapping_judge_agent = ArtanaMappingJudgeAdapter()

    dictionary_repo = legacy_container.build_dictionary_repository(session)
    embedding_provider = HybridTextEmbeddingProvider()
    active_dictionary_search_harness = dictionary_search_harness
    if active_dictionary_search_harness is None:
        from src.infrastructure.llm.adapters.dictionary_search_harness_adapter import (
            ArtanaDictionarySearchHarnessAdapter,
        )

        active_dictionary_search_harness = ArtanaDictionarySearchHarnessAdapter(
            dictionary_repo=dictionary_repo,
            embedding_provider=embedding_provider,
            mapping_judge_agent=active_mapping_judge_agent,
        )
    dictionary_service = legacy_container.build_dictionary_service(
        session,
        dictionary_search_harness=active_dictionary_search_harness,
        embedding_provider=embedding_provider,
    )
    entity_repo = legacy_container.build_entity_repository(session)
    provenance_repo = legacy_container.build_provenance_repository(session)

    # Mapper
    exact_mapper = ExactMapper(dictionary_service)
    vector_mapper = VectorMapper(dictionary_service)
    mappers: list[Mapper] = [
        exact_mapper,
        vector_mapper,
        LLMJudgeMapper(
            dictionary_service,
            mapping_judge_agent=active_mapping_judge_agent,
        ),
    ]
    mapper = HybridMapper(mappers)

    # Normalizer
    unit_converter = UnitConverter(dictionary_service)
    value_caster = ValueCaster(dictionary_service)
    normalizer = CompositeNormalizer(unit_converter, value_caster)

    # Resolver
    resolver = EntityResolver(dictionary_service, entity_repo)

    # Validator
    # NOTE: Triple validation is enforced in KernelRelationService when
    # relation edges are created. This ingestion pipeline currently persists
    # observations only.
    validator = ObservationValidator(dictionary_service)

    # Services
    observation_service = legacy_container.create_kernel_observation_service(
        session,
        dictionary_service=dictionary_service,
        entity_repository=entity_repo,
    )
    provenance_tracker = ProvenanceTracker(provenance_repo)

    return IngestionPipeline(
        mapper=mapper,
        normalizer=normalizer,
        resolver=resolver,
        validator=validator,
        observation_service=observation_service,
        provenance_tracker=provenance_tracker,
        rollback_on_error=session.rollback,
    )
