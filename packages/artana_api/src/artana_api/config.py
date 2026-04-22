"""Configuration helpers for the public Artana SDK."""

from __future__ import annotations

import os
from collections.abc import Mapping
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .exceptions import ArtanaConfigurationError


class ArtanaConfig(BaseModel):
    """Static configuration for one Artana API client."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_url: str = Field(min_length=1)
    api_key: str | None = None
    access_token: str | None = None
    openai_api_key: str | None = None
    timeout_seconds: float = Field(default=30.0, gt=0.0)
    default_space_id: str | None = None
    default_headers: dict[str, str] = Field(default_factory=dict)
    artana_api_key_header: str = Field(default="X-Artana-Key", min_length=1)
    openai_api_key_header: str = Field(default="X-OpenAI-API-Key", min_length=1)

    @field_validator("base_url")
    @classmethod
    def _normalize_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized:
            raise ValueError("base_url is required")
        return normalized

    @field_validator("api_key", "access_token", "openai_api_key")
    @classmethod
    def _normalize_optional_secret(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("default_space_id")
    @classmethod
    def _normalize_default_space_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return str(UUID(normalized))

    @field_validator("default_headers")
    @classmethod
    def _normalize_default_headers(cls, value: dict[str, str]) -> dict[str, str]:
        normalized_headers: dict[str, str] = {}
        for key, header_value in value.items():
            normalized_key = key.strip()
            normalized_value = header_value.strip()
            if normalized_key and normalized_value:
                normalized_headers[normalized_key] = normalized_value
        return normalized_headers

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> ArtanaConfig:
        """Build one config object from environment variables."""
        env = os.environ if environ is None else environ
        base_url = env.get("ARTANA_API_BASE_URL") or env.get("ARTANA_BASE_URL")
        if base_url is None or base_url.strip() == "":
            raise ArtanaConfigurationError(
                "ARTANA_API_BASE_URL is required to build ArtanaConfig from env.",
            )

        timeout_raw = env.get("ARTANA_TIMEOUT_SECONDS", "30")
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise ArtanaConfigurationError(
                "ARTANA_TIMEOUT_SECONDS must be a valid number.",
            ) from exc

        return cls(
            base_url=base_url,
            api_key=env.get("ARTANA_API_KEY"),
            access_token=env.get("ARTANA_ACCESS_TOKEN")
            or env.get("ARTANA_BEARER_TOKEN"),
            openai_api_key=env.get("ARTANA_OPENAI_API_KEY")
            or env.get("OPENAI_API_KEY"),
            timeout_seconds=timeout_seconds,
            default_space_id=env.get("ARTANA_DEFAULT_SPACE_ID"),
        )


__all__ = ["ArtanaConfig"]
