"""Configuration helpers for data discovery source creation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from artana_evidence_db.runtime import (
    create_graph_domain_context_policy,
    default_graph_domain_context_for_source_type,
)

from src.domain.entities import (
    data_discovery_parameters,
    data_discovery_session,
    data_source_configs,
    user_data_source,
)
from src.domain.services.domain_context_resolver import DomainContextResolver
from src.type_definitions.json_utils import to_json_value

from .session_methods import SessionManagementMixin

if TYPE_CHECKING:
    from datetime import date

    from src.application.services.pubmed_query_builder import PubMedQueryBuilder
    from src.domain.repositories.data_discovery_repository import (
        SourceCatalogRepository,
    )
    from src.type_definitions.common import JSONObject, SourceMetadata

logger = logging.getLogger(__name__)


class QuerySourceConfigurationMixin(SessionManagementMixin):
    """Helpers for preparing source metadata and ingestion defaults."""

    _catalog_repo: SourceCatalogRepository
    _pubmed_query_builder: PubMedQueryBuilder

    @staticmethod
    def _to_json_object(payload: JSONObject) -> JSONObject:
        return {key: to_json_value(value) for key, value in payload.items()}

    @staticmethod
    def _format_pubmed_date(value: date | None) -> str | None:
        if value is None:
            return None
        return value.strftime("%Y/%m/%d")

    def _build_pubmed_metadata(
        self,
        parameters: data_discovery_parameters.AdvancedQueryParameters,
    ) -> SourceMetadata:
        self._pubmed_query_builder.validate(parameters)
        query = self._pubmed_query_builder.build_query(parameters)
        if query == "ALL[All Fields]":
            query = "MED13"
        domain_context_policy = create_graph_domain_context_policy()
        config = data_source_configs.pubmed.PubMedQueryConfig(
            query=query,
            domain_context=(
                default_graph_domain_context_for_source_type(
                    "pubmed",
                    domain_context_policy=domain_context_policy,
                )
                or DomainContextResolver.GENERAL_DEFAULT_DOMAIN
            ),
            date_from=self._format_pubmed_date(parameters.date_from),
            date_to=self._format_pubmed_date(parameters.date_to),
            publication_types=(parameters.publication_types or None),
            max_results=parameters.max_results,
        )
        return self._to_json_object(config.model_dump(mode="json"))

    @staticmethod
    def _coerce_json_object(payload: object | None) -> JSONObject:
        """Normalize payload dictionaries into JSON-safe objects."""
        if not isinstance(payload, dict):
            return {}

        metadata: JSONObject = {}
        for key, value in payload.items():
            metadata[str(key)] = to_json_value(value)
        return metadata

    def _apply_discovery_defaults(
        self,
        source_config: JSONObject,
        catalog_entry: data_discovery_session.SourceCatalogEntry,
    ) -> JSONObject:
        """Apply catalog-level defaults for metadata, including AI settings."""
        config_payload: JSONObject = dict(source_config)
        raw_metadata = config_payload.get("metadata")
        metadata = self._coerce_json_object(raw_metadata)

        defaults = catalog_entry.capabilities.discovery_defaults
        ai_profile = defaults.ai_profile

        if ai_profile.default_query and not metadata.get("query"):
            metadata["query"] = ai_profile.default_query

        existing_agent_config = metadata.get("agent_config")
        agent_config = (
            dict(existing_agent_config)
            if isinstance(existing_agent_config, dict)
            else {}
        )

        if ai_profile.is_ai_managed:
            agent_config.setdefault("is_ai_managed", True)
        if ai_profile.agent_prompt:
            agent_config.setdefault("agent_prompt", ai_profile.agent_prompt)
        if ai_profile.use_research_space_context is not None:
            agent_config.setdefault(
                "use_research_space_context",
                ai_profile.use_research_space_context,
            )
        if ai_profile.model_id is not None:
            agent_config.setdefault("model_id", ai_profile.model_id)
        if ai_profile.source_type:
            agent_config.setdefault("query_agent_source_type", ai_profile.source_type)

        if ai_profile.is_ai_managed:
            metadata.setdefault("agent_config", agent_config)
        elif existing_agent_config:
            metadata["agent_config"] = agent_config

        config_payload["metadata"] = self._to_json_object(metadata)
        return config_payload

    @staticmethod
    def _build_ingestion_schedule(
        catalog_entry: data_discovery_session.SourceCatalogEntry,
    ) -> user_data_source.IngestionSchedule:
        defaults = catalog_entry.capabilities.discovery_defaults
        if not defaults.schedule_enabled:
            return user_data_source.IngestionSchedule(
                enabled=False,
                frequency=user_data_source.ScheduleFrequency.MANUAL,
                start_time=None,
                timezone="UTC",
                cron_expression=None,
            )

        return user_data_source.IngestionSchedule(
            enabled=True,
            frequency=user_data_source.ScheduleFrequency(defaults.schedule_frequency),
            start_time=None,
            timezone=defaults.schedule_timezone,
            cron_expression=None,
        )

    def _apply_pubmed_defaults(
        self,
        source_config: JSONObject,
        parameters: data_discovery_parameters.AdvancedQueryParameters,
    ) -> JSONObject:
        config_payload: JSONObject = dict(source_config)
        raw_metadata = config_payload.get("metadata")
        metadata = self._coerce_json_object(raw_metadata)
        metadata.setdefault(
            "domain_context",
            DomainContextResolver.PUBMED_DEFAULT_DOMAIN,
        )
        if not isinstance(metadata.get("query"), str) or not metadata.get("query"):
            derived = self._build_pubmed_metadata(parameters)
            for key, value in derived.items():
                metadata.setdefault(key, value)
        validated_config = data_source_configs.pubmed.PubMedQueryConfig.model_validate(
            metadata,
        )
        config_payload["metadata"] = self._to_json_object(
            validated_config.model_dump(mode="json"),
        )
        return config_payload

    def _apply_api_defaults(
        self,
        source_config: JSONObject,
        catalog_entry: data_discovery_session.SourceCatalogEntry,
    ) -> JSONObject:
        """Ensure API-backed sources have the minimum required configuration."""
        config_payload: JSONObject = dict(source_config)

        raw_url = config_payload.get("url")
        current_url = raw_url.strip() if isinstance(raw_url, str) else None
        fallback_url = catalog_entry.api_endpoint or catalog_entry.url_template
        if not current_url and isinstance(fallback_url, str) and fallback_url.strip():
            config_payload["url"] = fallback_url

        raw_rpm = config_payload.get("requests_per_minute")
        if not isinstance(raw_rpm, int) or raw_rpm < 1:
            config_payload["requests_per_minute"] = 10

        raw_metadata = config_payload.get("metadata")
        metadata_payload = self._coerce_json_object(raw_metadata)
        metadata_payload.setdefault("catalog_entry_id", catalog_entry.id)
        config_payload["metadata"] = self._to_json_object(metadata_payload)
        return config_payload

    @staticmethod
    def _derive_default_clinvar_query(
        parameters: data_discovery_parameters.AdvancedQueryParameters,
    ) -> str:
        gene = (
            parameters.gene_symbol.strip().upper()
            if isinstance(parameters.gene_symbol, str)
            and parameters.gene_symbol.strip()
            else "MED13"
        )
        term = (
            parameters.search_term.strip()
            if isinstance(parameters.search_term, str)
            and parameters.search_term.strip()
            else "pathogenic variant"
        )
        return f"{gene} {term}".strip()

    def _apply_clinvar_defaults(
        self,
        source_config: JSONObject,
        parameters: data_discovery_parameters.AdvancedQueryParameters,
    ) -> JSONObject:
        """Apply ClinVar-specific defaults and normalize metadata."""
        config_payload: JSONObject = dict(source_config)
        raw_metadata = config_payload.get("metadata")
        metadata = self._coerce_json_object(raw_metadata)

        if not isinstance(metadata.get("query"), str) or not metadata.get("query"):
            metadata.setdefault(
                "query",
                self._derive_default_clinvar_query(parameters),
            )

        if not isinstance(metadata.get("gene_symbol"), str) or not metadata.get(
            "gene_symbol",
        ):
            default_gene = (
                parameters.gene_symbol.strip().upper()
                if isinstance(parameters.gene_symbol, str)
                and parameters.gene_symbol.strip()
                else "MED13"
            )
            metadata.setdefault("gene_symbol", default_gene)

        validated_config = data_source_configs.ClinVarQueryConfig.model_validate(
            metadata,
        )
        config_payload["metadata"] = self._to_json_object(
            validated_config.model_dump(mode="json"),
        )

        raw_rpm = config_payload.get("requests_per_minute")
        if not isinstance(raw_rpm, int) or raw_rpm < 1:
            config_payload["requests_per_minute"] = 10
        return config_payload

    def _prepare_source_configuration(
        self,
        source_type: user_data_source.SourceType,
        source_config: JSONObject,
        catalog_entry: data_discovery_session.SourceCatalogEntry,
        parameters: data_discovery_parameters.AdvancedQueryParameters,
    ) -> JSONObject:
        """Apply source-type-specific defaults before configuration validation."""
        config_payload = self._apply_discovery_defaults(
            source_config=source_config,
            catalog_entry=catalog_entry,
        )
        if source_type == user_data_source.SourceType.PUBMED:
            return self._apply_pubmed_defaults(config_payload, parameters)
        if source_type == user_data_source.SourceType.CLINVAR:
            return self._apply_clinvar_defaults(config_payload, parameters)
        if source_type == user_data_source.SourceType.API:
            return self._apply_api_defaults(config_payload, catalog_entry)
        return config_payload
