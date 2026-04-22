"""Factory helpers for building data source AI test services."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from src.application.services import (
    DataSourceAiTestDependencies,
    DataSourceAiTestService,
    DataSourceAiTestSettings,
)
from src.database.session import SessionLocal, set_session_rls_context
from src.domain.agents.models import ModelCapability
from src.infrastructure.data_sources import ClinVarSourceGateway, PubMedSourceGateway
from src.infrastructure.llm.adapters.query_agent_adapter import ArtanaQueryAgentAdapter
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.state.agent_run_state_repository import (
    SqlAlchemyAgentRunStateRepository,
)
from src.infrastructure.repositories import (
    SqlAlchemyResearchSpaceRepository,
    SqlAlchemyUserDataSourceRepository,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

DEFAULT_AI_TEST_SAMPLE_SIZE = 5


def build_data_source_ai_test_service(
    *,
    session: Session,
) -> DataSourceAiTestService:
    """Create a fully wired AI test service for the current session."""
    source_repository = SqlAlchemyUserDataSourceRepository(session)
    research_space_repository = SqlAlchemyResearchSpaceRepository(session)
    agent_run_state_repository = SqlAlchemyAgentRunStateRepository(session)

    # Get model from registry (respects env var overrides)
    registry = get_model_registry()
    model_spec = registry.get_default_model(ModelCapability.QUERY_GENERATION)
    model_name = model_spec.model_id

    query_agent = ArtanaQueryAgentAdapter(model=model_name)

    dependencies = DataSourceAiTestDependencies(
        source_repository=source_repository,
        pubmed_gateway=PubMedSourceGateway(),
        clinvar_gateway=ClinVarSourceGateway(),
        query_agent=query_agent,
        run_id_provider=query_agent,
        research_space_repository=research_space_repository,
        agent_run_state=agent_run_state_repository,
    )
    return DataSourceAiTestService(
        dependencies,
        settings=DataSourceAiTestSettings(
            sample_size=DEFAULT_AI_TEST_SAMPLE_SIZE,
            ai_model_name=model_name,
        ),
    )


@contextmanager
def data_source_ai_test_service_context(
    *,
    session: Session | None = None,
) -> Iterator[DataSourceAiTestService]:
    """Context manager that yields a test service and closes the session."""
    local_session = session or SessionLocal()
    if session is None:
        set_session_rls_context(local_session, bypass_rls=True)
    try:
        service = build_data_source_ai_test_service(session=local_session)
        yield service
    finally:
        if session is None:
            local_session.close()


__all__ = [
    "DEFAULT_AI_TEST_SAMPLE_SIZE",
    "build_data_source_ai_test_service",
    "data_source_ai_test_service_context",
]
