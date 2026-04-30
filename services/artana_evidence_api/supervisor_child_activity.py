"""Supervisor child-run transparency helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_api.transparency import (
    active_skill_names_from_policy_content,
    append_skill_activity,
    sync_policy_decisions_artifact,
)

if TYPE_CHECKING:
    from uuid import UUID

    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.run_registry import HarnessRunRegistry

def _propagate_child_skill_activity(  # noqa: PLR0913
    *,
    space_id: UUID,
    parent_run_id: str,
    child_run_id: str,
    source_kind: str,
    artifact_store: HarnessArtifactStore,
    run_registry: HarnessRunRegistry,
    runtime: GraphHarnessKernelRuntime,
) -> None:
    policy_content = sync_policy_decisions_artifact(
        space_id=space_id,
        run_id=child_run_id,
        run_registry=run_registry,
        artifact_store=artifact_store,
        runtime=runtime,
    )
    if policy_content is None:
        return
    append_skill_activity(
        space_id=space_id,
        run_id=parent_run_id,
        skill_names=tuple(active_skill_names_from_policy_content(policy_content)),
        source_run_id=child_run_id,
        source_kind=source_kind,
        artifact_store=artifact_store,
        run_registry=run_registry,
        runtime=runtime,
    )




__all__ = ["_propagate_child_skill_activity"]
