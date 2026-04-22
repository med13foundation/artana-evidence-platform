"""
Data mappers for Data Discovery entities.

These functions convert between domain entities and database models,
following the Clean Architecture pattern of separating domain logic
from infrastructure concerns.
"""

import json
from uuid import UUID

from pydantic import BaseModel

from src.domain.entities.data_discovery_parameters import (
    AdvancedQueryParameters,
    QueryParameterCapabilities,
    QueryParameterType,
    TestResultStatus,
)
from src.domain.entities.data_discovery_session import (
    DataDiscoverySession,
    QueryTestResult,
    SourceCatalogEntry,
)
from src.domain.entities.discovery_preset import (
    DiscoveryPreset,
    DiscoveryProvider,
    PresetScope,
)
from src.domain.entities.discovery_search_job import (
    DiscoverySearchJob,
    DiscoverySearchStatus,
)
from src.domain.entities.user_data_source import SourceType
from src.models.database.data_discovery import (
    DataDiscoverySessionModel,
    DiscoveryPresetModel,
    DiscoverySearchJobModel,
    PresetScopeEnum,
    QueryTestResultModel,
    SourceCatalogEntryModel,
)
from src.type_definitions.common import JSONObject

UUIDInput = str | int | UUID


def _is_json_value(value: object) -> bool:
    """Return whether the supplied value conforms to ``JSONValue``."""
    if value is None or isinstance(value, str | int | float | bool):
        return True
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_json_value(item) for key, item in value.items()
        )
    return False


def _model_to_json_object(model: BaseModel) -> JSONObject:
    """Serialize a Pydantic model into a JSON-safe object for JSON columns."""
    payload = json.loads(model.model_dump_json())
    if not isinstance(payload, dict):
        msg = "Expected model to serialize to a JSON object"
        raise TypeError(msg)
    if not _is_json_value(payload):
        msg = "Expected model to serialize to a JSON-safe object"
        raise TypeError(msg)
    return payload


def _coerce_uuid(value: UUIDInput) -> UUID:
    """Convert legacy string/int identifiers into UUIDs."""
    if isinstance(value, UUID):
        return value
    if isinstance(value, int):
        return UUID(f"{value:032x}")
    normalized = value.strip()
    try:
        return UUID(normalized)
    except ValueError as exc:
        if normalized.isdigit():
            return UUID(f"{int(normalized):032x}")
        msg = f"Invalid UUID value: {value}"
        raise ValueError(msg) from exc


def _coerce_uuid_or_none(value: UUIDInput | None) -> UUID | None:
    return None if value is None else _coerce_uuid(value)


def session_to_model(entity: DataDiscoverySession) -> DataDiscoverySessionModel:
    """
    Convert a DataDiscoverySession entity to a database model.

    Args:
        entity: The domain entity to convert

    Returns:
        The corresponding database model
    """
    # Convert UUID objects to strings for database storage
    return DataDiscoverySessionModel(
        id=str(entity.id) if isinstance(entity.id, UUID) else entity.id,
        owner_id=(
            str(entity.owner_id)
            if isinstance(entity.owner_id, UUID)
            else entity.owner_id
        ),
        research_space_id=(
            str(entity.research_space_id)
            if entity.research_space_id and isinstance(entity.research_space_id, UUID)
            else entity.research_space_id
        ),
        name=entity.name,
        gene_symbol=entity.current_parameters.gene_symbol,
        search_term=entity.current_parameters.search_term,
        selected_sources=entity.selected_sources,
        tested_sources=entity.tested_sources,
        total_tests_run=entity.total_tests_run,
        successful_tests=entity.successful_tests,
        is_active=entity.is_active,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        last_activity_at=entity.last_activity_at,
        pubmed_search_config=_model_to_json_object(entity.current_parameters),
    )


def session_to_entity(model: DataDiscoverySessionModel) -> DataDiscoverySession:
    """
    Convert a DataDiscoverySessionModel to a domain entity.

    Args:
        model: The database model to convert

    Returns:
        The corresponding domain entity
    """
    session_id = _coerce_uuid(model.id)
    owner_id = _coerce_uuid(model.owner_id)
    research_space_id = _coerce_uuid_or_none(model.research_space_id)

    parameters_payload = model.pubmed_search_config or {}
    derived_parameters: dict[str, object | None] = {
        "gene_symbol": model.gene_symbol,
        "search_term": model.search_term,
    }
    if isinstance(parameters_payload, dict):
        derived_parameters.update(parameters_payload)

    parameters = AdvancedQueryParameters.model_validate(derived_parameters)

    return DataDiscoverySession(
        id=session_id,
        owner_id=owner_id,
        research_space_id=research_space_id,
        name=model.name,
        current_parameters=parameters,
        selected_sources=model.selected_sources or [],
        tested_sources=model.tested_sources or [],
        total_tests_run=model.total_tests_run,
        successful_tests=model.successful_tests,
        is_active=model.is_active,
        created_at=model.created_at,
        updated_at=model.updated_at,
        last_activity_at=model.last_activity_at,
    )


def source_catalog_to_model(entity: SourceCatalogEntry) -> SourceCatalogEntryModel:
    """
    Convert a SourceCatalogEntry entity to a database model.

    Args:
        entity: The domain entity to convert

    Returns:
        The corresponding database model
    """
    return SourceCatalogEntryModel(
        id=entity.id,
        name=entity.name,
        description=entity.description,
        category=entity.category,
        subcategory=entity.subcategory,
        tags=entity.tags,
        source_type=entity.source_type.value,
        param_type=entity.param_type.value,  # Convert enum to string
        url_template=entity.url_template,
        data_format=entity.data_format,
        api_endpoint=entity.api_endpoint,
        is_active=entity.is_active,
        requires_auth=entity.requires_auth,
        usage_count=entity.usage_count,
        success_rate=entity.success_rate,
        source_template_id=entity.source_template_id,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        query_capabilities=_model_to_json_object(entity.capabilities),
    )


def source_catalog_to_entity(model: SourceCatalogEntryModel) -> SourceCatalogEntry:
    """
    Convert a SourceCatalogEntryModel to a domain entity.

    Args:
        model: The database model to convert

    Returns:
        The corresponding domain entity
    """
    return SourceCatalogEntry(
        id=model.id,
        name=model.name,
        description=model.description,
        category=model.category,
        subcategory=model.subcategory,
        tags=model.tags or [],
        source_type=SourceType(model.source_type),
        param_type=QueryParameterType(model.param_type),
        url_template=model.url_template,
        data_format=model.data_format,
        api_endpoint=model.api_endpoint,
        is_active=model.is_active,
        requires_auth=model.requires_auth,
        usage_count=model.usage_count,
        success_rate=model.success_rate,
        source_template_id=model.source_template_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        capabilities=QueryParameterCapabilities.model_validate(
            model.query_capabilities or {},
        ),
    )


def query_result_to_model(entity: QueryTestResult) -> QueryTestResultModel:
    """
    Convert a QueryTestResult entity to a database model.

    Args:
        entity: The domain entity to convert

    Returns:
        The corresponding database model
    """
    # Convert UUID objects to strings for database storage
    return QueryTestResultModel(
        id=str(entity.id) if isinstance(entity.id, UUID) else entity.id,
        session_id=(
            str(entity.session_id)
            if isinstance(entity.session_id, UUID)
            else entity.session_id
        ),
        catalog_entry_id=entity.catalog_entry_id,
        status=entity.status.value,  # Convert enum to string
        gene_symbol=entity.parameters.gene_symbol,
        search_term=entity.parameters.search_term,
        response_data=entity.response_data,
        response_url=entity.response_url,
        error_message=entity.error_message,
        execution_time_ms=entity.execution_time_ms,
        data_quality_score=entity.data_quality_score,
        started_at=entity.started_at,
        completed_at=entity.completed_at,
        parameters_payload=_model_to_json_object(entity.parameters),
    )


def query_result_to_entity(model: QueryTestResultModel) -> QueryTestResult:
    """
    Convert a QueryTestResultModel to a domain entity.

    Args:
        model: The database model to convert

    Returns:
        The corresponding domain entity
    """
    # Convert string UUIDs from database to UUID objects for domain entities
    # Handle various input types (string, UUID, int for legacy data)
    result_id = _coerce_uuid(model.id)
    session_id = _coerce_uuid(model.session_id)

    parameters_payload = model.parameters_payload or {}
    derived_parameters: dict[str, object | None] = {
        "gene_symbol": model.gene_symbol,
        "search_term": model.search_term,
    }
    if isinstance(parameters_payload, dict):
        derived_parameters.update(parameters_payload)

    parameters = AdvancedQueryParameters.model_validate(derived_parameters)

    return QueryTestResult(
        id=result_id,
        session_id=session_id,
        catalog_entry_id=model.catalog_entry_id,
        parameters=parameters,
        status=TestResultStatus(model.status),
        response_data=model.response_data,
        response_url=model.response_url,
        error_message=model.error_message,
        execution_time_ms=model.execution_time_ms,
        data_quality_score=model.data_quality_score,
        started_at=model.started_at,
        completed_at=model.completed_at,
    )


def preset_to_model(entity: DiscoveryPreset) -> DiscoveryPresetModel:
    """Convert a DiscoveryPreset entity to a database model."""
    return DiscoveryPresetModel(
        id=str(entity.id),
        owner_id=str(entity.owner_id),
        scope=PresetScopeEnum(entity.scope.value),
        provider=entity.provider.value,
        name=entity.name,
        description=entity.description,
        parameters=_model_to_json_object(entity.parameters),
        metadata_payload=entity.metadata,
        research_space_id=(
            str(entity.research_space_id)
            if entity.research_space_id is not None
            else None
        ),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def preset_to_entity(model: DiscoveryPresetModel) -> DiscoveryPreset:
    """Convert a DiscoveryPresetModel to a domain entity."""
    parameters_payload = model.parameters or {}
    advanced_parameters = AdvancedQueryParameters.model_validate(parameters_payload)
    return DiscoveryPreset(
        id=_coerce_uuid(model.id),
        owner_id=_coerce_uuid(model.owner_id),
        provider=DiscoveryProvider(model.provider),
        scope=PresetScope(PresetScopeEnum(model.scope).value),
        name=model.name,
        description=model.description,
        parameters=advanced_parameters,
        metadata=model.metadata_payload or {},
        research_space_id=_coerce_uuid_or_none(model.research_space_id),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def search_job_to_model(entity: DiscoverySearchJob) -> DiscoverySearchJobModel:
    """Convert a DiscoverySearchJob entity into a persistence model."""
    return DiscoverySearchJobModel(
        id=str(entity.id),
        owner_id=str(entity.owner_id),
        session_id=str(entity.session_id) if entity.session_id else None,
        provider=entity.provider.value,
        status=entity.status.value,
        query_preview=entity.query_preview,
        parameters=_model_to_json_object(entity.parameters),
        total_results=entity.total_results,
        result_payload=entity.result_metadata,
        error_message=entity.error_message,
        storage_key=entity.storage_key,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        completed_at=entity.completed_at,
    )


def search_job_to_entity(model: DiscoverySearchJobModel) -> DiscoverySearchJob:
    """Convert a DiscoverySearchJobModel to a domain entity."""
    return DiscoverySearchJob(
        id=_coerce_uuid(model.id),
        owner_id=_coerce_uuid(model.owner_id),
        session_id=_coerce_uuid_or_none(model.session_id),
        provider=DiscoveryProvider(model.provider),
        status=DiscoverySearchStatus(model.status),
        query_preview=model.query_preview,
        parameters=AdvancedQueryParameters.model_validate(model.parameters or {}),
        total_results=model.total_results,
        result_metadata=model.result_payload or {},
        error_message=model.error_message,
        storage_key=model.storage_key,
        created_at=model.created_at,
        updated_at=model.updated_at,
        completed_at=model.completed_at,
    )
