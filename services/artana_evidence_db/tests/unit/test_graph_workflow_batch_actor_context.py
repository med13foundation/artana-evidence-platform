"""Actor-lineage coverage for official batch mutation dispatch."""

from __future__ import annotations

from typing import cast

import pytest
from artana_evidence_db.graph_workflow.actor_context import WorkflowActorContext
from artana_evidence_db.graph_workflow_batch import GraphWorkflowBatchMixin
from artana_evidence_db.workflow_persistence_models import GraphWorkflowModel


@pytest.mark.parametrize(
    ("resource_type", "action", "method_name"),
    [
        ("concept_proposal", "approve", "_apply_batch_concept_proposal"),
        ("dictionary_proposal", "approve", "_apply_batch_dictionary_proposal"),
        ("graph_change_proposal", "apply", "_apply_batch_graph_change_proposal"),
        ("connector_proposal", "approve", "_apply_batch_connector_proposal"),
    ],
)
def test_official_batch_mutations_receive_canonical_ai_actor(
    monkeypatch: pytest.MonkeyPatch,
    resource_type: str,
    action: str,
    method_name: str,
) -> None:
    service = GraphWorkflowBatchMixin()
    observed: dict[str, object] = {}

    def capture_actor(**kwargs: object) -> dict[str, object]:
        observed.update(kwargs)
        return {"status": "applied"}

    monkeypatch.setattr(service, method_name, capture_actor)
    principal = "agent:official-batch-reviewer"

    service._apply_batch_review_item(
        research_space_id="space-1",
        workflow=cast("GraphWorkflowModel", object()),
        item={
            "resource_type": resource_type,
            "resource_id": "resource-1",
            "action": action,
        },
        actor_context=WorkflowActorContext(
            authenticated_user_actor="manual:user-1",
            authenticated_ai_principal=principal,
        ),
        confidence_assessment=None,
        ai_decision_payload=None,
        index=0,
    )

    assert observed["actor"] == principal
