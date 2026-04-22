"""Shared helpers for Artana step execution and run identity."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Mapping

    from src.infrastructure.llm.config.runtime_policy import ReplayPolicy


class StepResultLike(Protocol):
    """Protocol for Artana step results."""

    output: object


@runtime_checkable
class StepClientLike(Protocol):
    """Runtime-checkable protocol for clients exposing ``step`` execution."""

    async def step(  # noqa: PLR0913 - explicit step contract mirrors kernel API
        self,
        *,
        run_id: str,
        tenant: object,
        model: str,
        prompt: str,
        output_schema: type[object],
        step_key: str,
        replay_policy: ReplayPolicy,
        context_version: object | None = None,
    ) -> StepResultLike: ...


_DEFAULT_EXTERNAL_ID_KEYS: tuple[str, ...] = ("external_id", "id")
_SOURCE_EXTERNAL_ID_KEYS: dict[str, tuple[str, ...]] = {
    "pubmed": ("pubmed_id", "pmid", "article_id", *_DEFAULT_EXTERNAL_ID_KEYS),
    "clinvar": (
        "clinvar_id",
        "variation_id",
        "allele_id",
        "accession",
        "rcv_accession",
        *_DEFAULT_EXTERNAL_ID_KEYS,
    ),
    "marrvel": ("gene_symbol", "record_type", *_DEFAULT_EXTERNAL_ID_KEYS),
}


def build_deterministic_run_id(
    *,
    prefix: str,
    research_space_id: str | None,
    source_type: str,
    external_id: str,
    extraction_config_version: str,
) -> str:
    """Create replay-safe run identifiers from stable business inputs."""
    normalized_prefix = prefix.strip().lower() or "run"
    normalized_space = (
        research_space_id.strip()
        if isinstance(research_space_id, str) and research_space_id.strip()
        else "global"
    )
    normalized_source_type = source_type.strip().lower() or "unknown"
    normalized_external_id = external_id.strip() or "unknown"
    normalized_config_version = extraction_config_version.strip() or "v1"
    payload = (
        f"{normalized_space}|{normalized_source_type}|{normalized_external_id}|"
        f"{normalized_config_version}"
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"{normalized_prefix}:{normalized_source_type}:{digest}"


def stable_sha256_digest(payload: str, *, length: int = 24) -> str:
    """Return a stable SHA-256 hex digest prefix for run identity."""
    normalized_length = max(length, 1)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:normalized_length]


def resolve_external_record_id(
    *,
    source_type: str,
    raw_record: Mapping[str, object],
    fallback_document_id: str,
) -> str:
    """Resolve a stable external ID for run identity construction."""
    keys = _SOURCE_EXTERNAL_ID_KEYS.get(
        source_type.strip().lower(),
        _DEFAULT_EXTERNAL_ID_KEYS,
    )
    for key in keys:
        value = raw_record.get(key)
        normalized_value = _normalize_identifier(value)
        if normalized_value is not None:
            return normalized_value
    fallback = fallback_document_id.strip()
    return fallback if fallback else "unknown"


def _normalize_identifier(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)
    if isinstance(value, list | tuple):
        for item in value:
            item_identifier = _normalize_identifier(item)
            if item_identifier is not None:
                return item_identifier
    return None


async def run_single_step_with_policy(  # noqa: PLR0913
    client: object,
    *,
    run_id: str,
    tenant: object,
    model: str,
    prompt: str,
    output_schema: type[object],
    step_key: str,
    replay_policy: ReplayPolicy,
    context_version: object | None = None,
) -> StepResultLike:
    """Execute ``SingleStepModelClient.step`` with replay policy."""
    if not isinstance(client, StepClientLike):
        msg = "Client does not expose a compatible callable 'step' method."
        raise TypeError(msg)
    if context_version is not None:
        return await client.step(
            run_id=run_id,
            tenant=tenant,
            model=model,
            prompt=prompt,
            output_schema=output_schema,
            step_key=step_key,
            replay_policy=replay_policy,
            context_version=context_version,
        )
    return await client.step(
        run_id=run_id,
        tenant=tenant,
        model=model,
        prompt=prompt,
        output_schema=output_schema,
        step_key=step_key,
        replay_policy=replay_policy,
    )


__all__ = [
    "build_deterministic_run_id",
    "resolve_external_record_id",
    "run_single_step_with_policy",
    "stable_sha256_digest",
]
