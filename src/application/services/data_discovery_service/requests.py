"""Typed request models for data discovery services."""

from __future__ import annotations

from uuid import UUID  # noqa: TCH003

from pydantic import BaseModel, ConfigDict, Field

from src.domain.entities.data_discovery_parameters import AdvancedQueryParameters
from src.type_definitions.common import JSONObject  # noqa: TCH001


class CreateDataDiscoverySessionRequest(BaseModel):
    """Request model for creating a new data discovery session."""

    owner_id: UUID
    name: str = "Untitled Session"
    research_space_id: UUID | None = None
    initial_parameters: AdvancedQueryParameters = Field(
        default_factory=lambda: AdvancedQueryParameters(
            gene_symbol=None,
            search_term=None,
        ),
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)


class UpdateSessionParametersRequest(BaseModel):
    """Request model for updating session parameters."""

    session_id: UUID
    parameters: AdvancedQueryParameters

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ExecuteQueryTestRequest(BaseModel):
    """Request model for executing a query test."""

    session_id: UUID
    catalog_entry_id: str
    timeout_seconds: int = 30
    parameters: AdvancedQueryParameters | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class AddSourceToSpaceRequest(BaseModel):
    """Request model for adding a tested source to a research space."""

    session_id: UUID
    catalog_entry_id: str
    research_space_id: UUID
    source_config: JSONObject = Field(default_factory=dict)
    requested_by: UUID | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)
