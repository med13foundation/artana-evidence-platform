"""
Application service for testing AI-managed data source configurations.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pydantic

from src.application.services.data_source_ai_test_helpers import (
    LOW_CONFIDENCE_THRESHOLD,
    apply_clinvar_defaults,
    build_clinvar_findings,
    build_findings,
    extract_search_terms,
    should_use_clinvar_gateway,
    should_use_pubmed_gateway,
)
from src.domain.entities import data_source_configs, user_data_source
from src.type_definitions import data_sources as data_source_types

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.services.ports.agent_run_state_port import AgentRunStatePort
    from src.domain.agents.ports.query_agent_port import (
        QueryAgentPort,
        QueryAgentRunMetadataProvider,
    )
    from src.domain.repositories import (
        ResearchSpaceRepository,
        UserDataSourceRepository,
    )
    from src.domain.services.clinvar_ingestion import ClinVarGateway
    from src.domain.services.pubmed_ingestion import PubMedGateway
    from src.type_definitions.common import RawRecord, SourceMetadata


class DataSourceAiTestSettings(pydantic.BaseModel):
    """Settings for AI data source test execution."""

    model_config = pydantic.ConfigDict(extra="forbid")

    sample_size: int = pydantic.Field(default=5, ge=1)
    ai_model_name: str | None = None


@dataclass(frozen=True)
class DataSourceAiTestDependencies:
    """Bundle dependencies required for AI test execution."""

    source_repository: UserDataSourceRepository
    pubmed_gateway: PubMedGateway
    clinvar_gateway: ClinVarGateway
    query_agent: QueryAgentPort | None
    research_space_repository: ResearchSpaceRepository | None
    agent_run_state: AgentRunStatePort | None = None
    run_id_provider: QueryAgentRunMetadataProvider | None = None


class DataSourceAiTestService:
    """Coordinate AI configuration testing for supported data sources."""

    def __init__(
        self,
        dependencies: DataSourceAiTestDependencies,
        settings: DataSourceAiTestSettings | None = None,
    ) -> None:
        self._source_repository = dependencies.source_repository
        self._pubmed_gateway = dependencies.pubmed_gateway
        self._clinvar_gateway = dependencies.clinvar_gateway
        self._query_agent = dependencies.query_agent
        self._run_id_provider = dependencies.run_id_provider
        self._research_space_repository = dependencies.research_space_repository
        self._agent_run_state = dependencies.agent_run_state
        resolved_settings = settings or DataSourceAiTestSettings()
        self._sample_size = max(resolved_settings.sample_size, 1)
        self._ai_model_name = resolved_settings.ai_model_name

    async def test_ai_configuration(
        self,
        source_id: UUID,
    ) -> data_source_types.DataSourceAiTestResult:
        """Run a lightweight AI-driven test against a data source configuration."""
        source = self._require_source(source_id)
        checked_at = dt.datetime.now(dt.UTC)
        config = self._build_source_config(source)
        error_message = self._validate_preconditions(source=source, config=config)
        executed_query: str | None = None
        fetched_records = 0
        findings: list[data_source_types.DataSourceAiTestFinding] = []
        agent_run_id: str | None = None
        agent_run_tables: list[data_source_types.AgentRunTableSummary] = []
        ai_executed = False
        fetch_attempted = False

        # Track the actual model used (configured or default)
        actual_model_id: str | None = None

        if error_message is None and config is not None:
            research_space_description = self._resolve_research_space_description(
                source,
                config,
            )
            agent_source_type = config.agent_config.query_agent_source_type
            ai_executed = True
            # Use configured model_id or fall back to default
            actual_model_id = config.agent_config.model_id or self._ai_model_name
            intelligent_query = await self._generate_intelligent_query(
                research_space_description,
                config.agent_config.agent_prompt,
                source_type=agent_source_type,
                model_id=config.agent_config.model_id,
            )

            if not intelligent_query:
                error_message = "AI agent did not return a query. Refine the AI instructions and try again."
            else:
                executed_query = intelligent_query
                (
                    fetch_attempted,
                    fetched_records,
                    findings,
                    fetch_error,
                ) = await self._fetch_test_records(
                    source=source,
                    config=config,
                    executed_query=intelligent_query,
                )
                if fetch_error is not None:
                    error_message = fetch_error

        if ai_executed:
            agent_run_id, agent_run_tables = self._resolve_agent_run_state(checked_at)

        success = error_message is None
        if error_message is None:
            if fetch_attempted:
                message = (
                    f"AI test succeeded with {fetched_records} record(s) returned."
                )
            else:
                message = (
                    f"AI query generated successfully; no connector fetch step for "
                    f"{agent_source_type}."
                )
        else:
            message = error_message

        search_terms = extract_search_terms(executed_query)
        model_name = self._resolve_model_name(
            has_query_agent=self._query_agent is not None,
            configured_model_id=actual_model_id,
        )

        return data_source_types.DataSourceAiTestResult(
            source_id=source.id,
            model=model_name,
            success=success,
            message=message,
            executed_query=executed_query,
            search_terms=search_terms,
            fetched_records=fetched_records,
            sample_size=self._sample_size,
            findings=findings,
            checked_at=checked_at,
            agent_run_id=agent_run_id,
            agent_run_tables=agent_run_tables,
        )

    def _require_source(self, source_id: UUID) -> user_data_source.UserDataSource:
        source = self._source_repository.find_by_id(source_id)
        if source is None:
            msg = f"Data source {source_id} not found"
            raise ValueError(msg)
        return source

    @staticmethod
    def _build_source_config(
        source: user_data_source.UserDataSource,
    ) -> data_source_configs.PubMedQueryConfig | None:
        metadata: SourceMetadata = dict(source.configuration.metadata or {})
        metadata_with_defaults = apply_clinvar_defaults(
            metadata,
        )
        try:
            return data_source_configs.PubMedQueryConfig.model_validate(
                metadata_with_defaults,
            )
        except pydantic.ValidationError as exc:
            logger.warning("Invalid PubMed config for source %s: %s", source.id, exc)
            return None

    @staticmethod
    def _build_clinvar_test_config(
        *,
        source: user_data_source.UserDataSource,
        executed_query: str,
    ) -> data_source_configs.ClinVarQueryConfig | None:
        metadata: SourceMetadata = dict(source.configuration.metadata or {})
        metadata_with_defaults = apply_clinvar_defaults(
            metadata,
        )
        metadata_with_defaults["query"] = executed_query
        metadata_with_defaults["max_results"] = 5
        try:
            return data_source_configs.ClinVarQueryConfig.model_validate(
                metadata_with_defaults,
            )
        except pydantic.ValidationError as exc:
            logger.warning("Invalid ClinVar config for source %s: %s", source.id, exc)
            return None

    async def _fetch_test_records(
        self,
        *,
        source: user_data_source.UserDataSource,
        config: data_source_configs.PubMedQueryConfig,
        executed_query: str,
    ) -> tuple[
        bool,
        int,
        list[data_source_types.DataSourceAiTestFinding],
        str | None,
    ]:
        if should_use_pubmed_gateway(source, config):
            test_config = config.model_copy(
                update={
                    "query": executed_query,
                    "max_results": self._sample_size,
                    "relevance_threshold": 0,
                },
            )
            try:
                raw_records = await self._pubmed_gateway.fetch_records(test_config)
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("AI test failed for source %s", source.id)
                return True, 0, [], f"PubMed request failed: {exc!s}"

            findings = self._build_findings(raw_records)
            fetched_records = len(raw_records)
            error_message = (
                "PubMed returned no results for the AI-generated query. "
                "Adjust the prompt or filters and try again."
                if fetched_records == 0
                else None
            )
            return True, fetched_records, findings, error_message

        if should_use_clinvar_gateway(source, config):
            clinvar_test_config = self._build_clinvar_test_config(
                source=source,
                executed_query=executed_query,
            )
            if clinvar_test_config is None:
                return (
                    True,
                    0,
                    [],
                    "ClinVar source configuration is invalid. "
                    "Review source settings and try again.",
                )
            try:
                raw_records = await self._clinvar_gateway.fetch_records(
                    clinvar_test_config,
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("AI test failed for source %s", source.id)
                return True, 0, [], f"ClinVar request failed: {exc!s}"

            findings = self._build_clinvar_findings(raw_records)
            fetched_records = len(raw_records)
            error_message = (
                "ClinVar returned no results for the AI-generated query. "
                "Adjust the prompt or filters and try again."
                if fetched_records == 0
                else None
            )
            return True, fetched_records, findings, error_message

        # Non-PubMed/ClinVar sources currently support query generation validation only.
        logger.info(
            "Skipping connector fetch for unsupported AI test source %s",
            source.id,
        )
        return False, 0, [], None

    def _validate_preconditions(
        self,
        *,
        source: user_data_source.UserDataSource,
        config: data_source_configs.PubMedQueryConfig | None,
    ) -> str | None:
        if source.source_type not in (
            user_data_source.SourceType.PUBMED,
            user_data_source.SourceType.API,
            user_data_source.SourceType.CLINVAR,
        ):
            return "AI testing is only supported for PubMed, ClinVar, or API sources."
        if config is None:
            return "Source configuration is invalid. Review the source settings."
        if not config.agent_config.is_ai_managed:
            return "AI-managed queries are disabled for this source."
        if self._query_agent is None:
            return "AI agent is not configured for testing."
        if self._research_space_repository is None:
            return "Research space context is unavailable for AI testing."
        return None

    def _resolve_research_space_description(
        self,
        source: user_data_source.UserDataSource,
        config: data_source_configs.PubMedQueryConfig,
    ) -> str:
        if not config.agent_config.use_research_space_context:
            return ""
        if source.research_space_id is None:
            return ""
        repository = self._research_space_repository
        if repository is None:
            return ""
        space = repository.find_by_id(source.research_space_id)
        return space.description if space else ""

    async def _generate_intelligent_query(
        self,
        research_space_description: str,
        agent_prompt: str,
        source_type: str,
        model_id: str | None = None,
    ) -> str:
        if self._query_agent is None:
            return ""
        try:
            contract = await self._query_agent.generate_query(
                research_space_description=research_space_description,
                user_instructions=agent_prompt,
                source_type=source_type,
                model_id=model_id,
            )

            # Log decision and confidence for observability
            if contract.decision == "escalate":
                logger.warning(
                    "AI query escalated: %s (confidence=%.2f)",
                    contract.rationale,
                    contract.confidence_score,
                )
                return ""
            if contract.confidence_score < LOW_CONFIDENCE_THRESHOLD:
                logger.warning(
                    "Low confidence AI query (%.2f): %s",
                    contract.confidence_score,
                    contract.rationale,
                )

            return contract.query.strip()
        except Exception:  # pragma: no cover - defensive
            logger.exception("AI query generation failed")
            return ""

    def _resolve_model_name(
        self,
        *,
        has_query_agent: bool,
        configured_model_id: str | None = None,
    ) -> str | None:
        if not has_query_agent:
            return None
        # Use configured model if provided, otherwise fall back to default
        model = configured_model_id or self._ai_model_name
        return model.strip() if isinstance(model, str) and model.strip() else None

    def _build_findings(
        self,
        records: list[RawRecord],
    ) -> list[data_source_types.DataSourceAiTestFinding]:
        return build_findings(records, self._sample_size)

    def _build_clinvar_findings(
        self,
        records: list[RawRecord],
    ) -> list[data_source_types.DataSourceAiTestFinding]:
        return build_clinvar_findings(records, self._sample_size)

    def _resolve_agent_run_state(
        self,
        checked_at: dt.datetime,
    ) -> tuple[str | None, list[data_source_types.AgentRunTableSummary]]:
        if self._agent_run_state is None:
            return None, []

        if self._run_id_provider is None:
            return None, []

        run_id = self._run_id_provider.get_last_run_id()
        if run_id is None:
            window_start = checked_at - dt.timedelta(minutes=2)
            run_id = self._agent_run_state.find_latest_run_id(since=window_start)

        if run_id is None:
            return None, []

        return run_id, self._agent_run_state.get_run_table_summaries(run_id)


__all__ = [
    "DataSourceAiTestDependencies",
    "DataSourceAiTestService",
    "DataSourceAiTestSettings",
]
