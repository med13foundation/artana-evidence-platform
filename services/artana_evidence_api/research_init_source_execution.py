"""Structured-source execution helpers for research-init runs."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from artana_evidence_api.alias_yield_reporting import (
    attach_alias_yield_rollup,
    source_results_with_alias_yield,
)
from artana_evidence_api.research_init_models import (
    ResearchInitStructuredEnrichmentReplaySource,
)
from artana_evidence_api.research_init_structured_replay import (
    replay_structured_enrichment_result,
)
from artana_evidence_api.types.common import JSONObject, json_string_list

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.document_store import (
        HarnessDocumentRecord,
        HarnessDocumentStore,
    )
    from artana_evidence_api.proposal_store import (
        HarnessProposalDraft,
        HarnessProposalStore,
    )
    from artana_evidence_api.research_init_source_enrichment import (
        SourceEnrichmentResult,
    )
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry

_MARRVEL_STRUCTURED_ENRICHMENT_TIMEOUT_SECONDS = 90.0


class ReviewedEnrichmentProposalWriter(Protocol):
    """Callable that persists reviewed source-enrichment proposals."""

    def __call__(
        self,
        *,
        proposal_store: HarnessProposalStore,
        proposals: list[HarnessProposalDraft],
        space_id: UUID,
        run_id: str,
        objective: str,
    ) -> int: ...


def structured_enrichment_source_timeout_seconds(
    *,
    source_key: str,
) -> float | None:
    """Return the bounded execution budget for one structured enrichment source."""
    if source_key != "marrvel":
        return None
    raw_value = os.getenv("ARTANA_MARRVEL_STRUCTURED_ENRICHMENT_TIMEOUT_SECONDS")
    if raw_value is None or raw_value.strip() == "":
        return _MARRVEL_STRUCTURED_ENRICHMENT_TIMEOUT_SECONDS
    try:
        parsed = float(raw_value.strip())
    except ValueError:
        logging.getLogger(__name__).warning(
            "Invalid MARRVEL structured enrichment timeout override %r; using %.1fs",
            raw_value,
            _MARRVEL_STRUCTURED_ENRICHMENT_TIMEOUT_SECONDS,
        )
        return _MARRVEL_STRUCTURED_ENRICHMENT_TIMEOUT_SECONDS
    if parsed <= 0:
        logging.getLogger(__name__).warning(
            "Non-positive MARRVEL structured enrichment timeout override %r; using %.1fs",
            raw_value,
            _MARRVEL_STRUCTURED_ENRICHMENT_TIMEOUT_SECONDS,
        )
        return _MARRVEL_STRUCTURED_ENRICHMENT_TIMEOUT_SECONDS
    return parsed


async def run_structured_enrichment_source(
    *,
    source_key: str,
    source_label: str,
    log_message: str,
    runner: Callable[..., Awaitable[SourceEnrichmentResult]],
    space_id: UUID,
    seed_terms: list[str],
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    parent_run: HarnessRunRecord,
    proposal_store: HarnessProposalStore,
    run_id: str,
    objective: str,
    source_results: dict[str, JSONObject],
    enrichment_documents: list[HarnessDocumentRecord],
    errors: list[str],
    proposal_writer: ReviewedEnrichmentProposalWriter,
    replay_source: ResearchInitStructuredEnrichmentReplaySource | None = None,
) -> int:
    """Run one structured enrichment source and normalize the shared outputs."""
    logging.getLogger(__name__).info(log_message, space_id)
    source_results.setdefault(source_key, {})
    timeout_seconds = structured_enrichment_source_timeout_seconds(
        source_key=source_key,
    )
    if replay_source is not None:
        result = replay_structured_enrichment_result(
            replay_source=replay_source,
            space_id=space_id,
            document_store=document_store,
            parent_run=parent_run,
        )
    else:
        try:
            runner_call = runner(
                space_id=space_id,
                seed_terms=seed_terms,
                document_store=document_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
                parent_run=parent_run,
            )
            if timeout_seconds is None:
                result = await runner_call
            else:
                result = await asyncio.wait_for(
                    runner_call,
                    timeout=timeout_seconds,
                )
        except TimeoutError:
            error_message = (
                f"{source_label} enrichment timed out after {timeout_seconds:.2f}s"
            )
            errors.append(error_message)
            source_results[source_key]["status"] = "failed"
            source_results[source_key]["failure_reason"] = "timeout"
            source_results[source_key]["timeout_seconds"] = timeout_seconds
            refresh_research_init_source_outputs(
                artifact_store=artifact_store,
                space_id=space_id,
                run_id=run_id,
                source_key=source_key,
                source_result=source_results[source_key],
                error_message=error_message,
            )
            return 0
        except Exception as exc:  # noqa: BLE001
            error_message = f"{source_label} enrichment failed: {exc}"
            errors.append(error_message)
            source_results[source_key]["status"] = "failed"
            source_results[source_key]["failure_reason"] = type(exc).__name__
            if timeout_seconds is not None:
                source_results[source_key]["timeout_seconds"] = timeout_seconds
            refresh_research_init_source_outputs(
                artifact_store=artifact_store,
                space_id=space_id,
                run_id=run_id,
                source_key=source_key,
                source_result=source_results[source_key],
                error_message=error_message,
            )
            return 0

    enrichment_documents.extend(result.documents_created)
    source_results[source_key]["records_processed"] = result.records_processed
    source_results[source_key]["status"] = "completed"
    source_results[source_key].pop("failure_reason", None)
    source_results[source_key].pop("timeout_seconds", None)
    errors.extend(result.errors)
    if not result.proposals_created:
        return 0
    return proposal_writer(
        proposal_store=proposal_store,
        proposals=result.proposals_created,
        space_id=space_id,
        run_id=run_id,
        objective=objective,
    )


def refresh_research_init_source_outputs(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
    source_key: str,
    source_result: JSONObject,
    error_message: str | None = None,
) -> None:
    """Patch workspace/result artifacts with one refreshed source summary."""
    workspace = artifact_store.get_workspace(space_id=space_id, run_id=run_id)
    if workspace is None:
        return

    source_results = _copy_workspace_source_results(
        workspace.snapshot.get("source_results")
    )
    source_results[source_key] = dict(source_result)
    attach_alias_yield_rollup(source_results)

    errors = json_string_list(workspace.snapshot.get("errors"))
    if error_message is not None and error_message not in errors:
        errors.append(error_message)

    patch: JSONObject = {
        "source_results": source_results,
        "errors": errors,
    }

    result_artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key="research_init_result",
    )
    if result_artifact is not None:
        updated_result = dict(result_artifact.content)
        updated_result["source_results"] = source_results_with_alias_yield(
            source_results
        )
        updated_result["errors"] = list(errors)
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run_id,
            artifact_key="research_init_result",
            media_type="application/json",
            content=updated_result,
        )
        patch["research_init_result"] = updated_result

    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run_id,
        patch=patch,
    )


def _copy_workspace_source_results(value: object) -> dict[str, JSONObject]:
    """Return a shallow copy of the workspace source-results payload."""
    if not isinstance(value, dict):
        return {}
    copied: dict[str, JSONObject] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, dict):
            continue
        copied[key] = dict(item)
    return copied


__all__ = [
    "refresh_research_init_source_outputs",
    "run_structured_enrichment_source",
    "structured_enrichment_source_timeout_seconds",
]
