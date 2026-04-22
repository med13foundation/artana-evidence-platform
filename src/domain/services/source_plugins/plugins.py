from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ValidationError

from src.domain.entities.data_source_configs import (
    ClinVarQueryConfig,
    PubMedQueryConfig,
)
from src.domain.entities.user_data_source import (
    SourceConfiguration,
    SourceType,
)

if TYPE_CHECKING:
    from src.type_definitions.common import SourceMetadata
else:
    SourceMetadata = dict[str, object]  # Runtime type stub

from .base import SourcePlugin


class FileUploadSourcePlugin(SourcePlugin):
    """Plugin for validating file upload sources."""

    source_type = SourceType.FILE_UPLOAD

    def validate_configuration(
        self,
        configuration: SourceConfiguration,
    ) -> SourceConfiguration:
        metadata: SourceMetadata = dict(configuration.metadata or {})
        if not configuration.file_path:
            msg = "file_path is required for file upload sources"
            raise ValueError(msg)
        if not configuration.format:
            msg = "format is required for file upload sources"
            raise ValueError(msg)
        metadata.setdefault("ingest_mode", "batch")
        return configuration.model_copy(update={"metadata": metadata})


class APISourcePlugin(SourcePlugin):
    """Plugin for validating API-backed sources."""

    source_type = SourceType.API

    def validate_configuration(
        self,
        configuration: SourceConfiguration,
    ) -> SourceConfiguration:
        metadata: SourceMetadata = dict(configuration.metadata or {})
        if not configuration.url:
            msg = "url is required for API sources"
            raise ValueError(msg)
        if configuration.requests_per_minute is None:
            msg = "requests_per_minute is required for API sources"
            raise ValueError(msg)
        metadata.setdefault("auth_type", configuration.auth_type or "none")
        return configuration.model_copy(update={"metadata": metadata})


class DatabaseSourcePlugin(SourcePlugin):
    """Plugin for validating database replication sources."""

    source_type = SourceType.DATABASE

    def validate_configuration(
        self,
        configuration: SourceConfiguration,
    ) -> SourceConfiguration:
        metadata: SourceMetadata = dict(configuration.metadata or {})
        connection = metadata.get("connection_string")
        if not connection:
            msg = "metadata.connection_string is required for database sources"
            raise ValueError(msg)
        metadata.setdefault("driver", "postgresql")
        return configuration.model_copy(update={"metadata": metadata})


class PubMedSourcePlugin(SourcePlugin):
    """Plugin for validating PubMed data sources."""

    source_type = SourceType.PUBMED
    DEFAULT_REQUESTS_PER_MINUTE = 10

    def validate_configuration(
        self,
        configuration: SourceConfiguration,
    ) -> SourceConfiguration:
        metadata: SourceMetadata = dict(configuration.metadata or {})
        try:
            pubmed_config = PubMedQueryConfig.model_validate(metadata)
        except ValidationError as exc:
            messages = ", ".join(error["msg"] for error in exc.errors())
            raise ValueError(messages) from exc

        # Type: model_dump(mode="json") returns dict[str, object] which is SourceMetadata
        sanitized_metadata: SourceMetadata = dict(pubmed_config.model_dump(mode="json"))
        requests_per_minute = (
            configuration.requests_per_minute or self.DEFAULT_REQUESTS_PER_MINUTE
        )

        return configuration.model_copy(
            update={
                "metadata": sanitized_metadata,
                "requests_per_minute": requests_per_minute,
            },
        )


class ClinVarSourcePlugin(SourcePlugin):
    """Plugin for validating ClinVar data sources."""

    source_type = SourceType.CLINVAR
    DEFAULT_REQUESTS_PER_MINUTE = 10

    def validate_configuration(
        self,
        configuration: SourceConfiguration,
    ) -> SourceConfiguration:
        metadata: SourceMetadata = dict(configuration.metadata or {})
        try:
            clinvar_config = ClinVarQueryConfig.model_validate(metadata)
        except ValidationError as exc:
            messages = ", ".join(error["msg"] for error in exc.errors())
            raise ValueError(messages) from exc

        sanitized_metadata: SourceMetadata = dict(
            clinvar_config.model_dump(mode="json"),
        )
        requests_per_minute = (
            configuration.requests_per_minute or self.DEFAULT_REQUESTS_PER_MINUTE
        )

        return configuration.model_copy(
            update={
                "metadata": sanitized_metadata,
                "requests_per_minute": requests_per_minute,
            },
        )


__all__ = [
    "APISourcePlugin",
    "ClinVarSourcePlugin",
    "DatabaseSourcePlugin",
    "PubMedSourcePlugin",
    "FileUploadSourcePlugin",
]
