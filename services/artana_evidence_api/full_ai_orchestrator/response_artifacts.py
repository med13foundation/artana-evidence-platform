"""Action-output artifact writers for the full-AI orchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.full_ai_orchestrator.response_summaries import (
    _collect_chase_round_summaries,
)
from artana_evidence_api.full_ai_orchestrator.runtime_constants import (
    _BOOTSTRAP_ARTIFACT_KEY,
    _BRIEF_METADATA_ARTIFACT_KEY,
    _CHASE_ROUNDS_ARTIFACT_KEY,
    _DRIVEN_TERMS_ARTIFACT_KEY,
    _PUBMED_ARTIFACT_KEY,
    _SOURCE_EXECUTION_ARTIFACT_KEY,
)
from artana_evidence_api.types.common import JSONObject, json_array_or_empty

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore


def _store_action_output_artifacts(  # noqa: PLR0913
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
    objective: str,
    seed_terms: list[str],
    workspace_snapshot: JSONObject,
    source_execution_summary: JSONObject,
    bootstrap_summary: JSONObject | None,
    brief_metadata: JSONObject,
) -> None:
    pubmed_results = workspace_snapshot.get("pubmed_results")
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_PUBMED_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "pubmed_results": json_array_or_empty(pubmed_results),
            "documents_ingested": workspace_snapshot.get("documents_ingested", 0),
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_DRIVEN_TERMS_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "objective": objective,
            "seed_terms": list(seed_terms),
            "driven_terms": (
                json_array_or_empty(workspace_snapshot.get("driven_terms"))
            ),
            "driven_genes_from_pubmed": (
                json_array_or_empty(workspace_snapshot.get("driven_genes_from_pubmed"))
            ),
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_SOURCE_EXECUTION_ARTIFACT_KEY,
        media_type="application/json",
        content=source_execution_summary,
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_BOOTSTRAP_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "bootstrap_run_id": workspace_snapshot.get("bootstrap_run_id"),
            "bootstrap_source_type": workspace_snapshot.get("bootstrap_source_type"),
            "summary": bootstrap_summary or {},
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_CHASE_ROUNDS_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "rounds": _collect_chase_round_summaries(
                workspace_snapshot=workspace_snapshot
            )
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_BRIEF_METADATA_ARTIFACT_KEY,
        media_type="application/json",
        content=brief_metadata,
    )


__all__ = ["_store_action_output_artifacts"]
