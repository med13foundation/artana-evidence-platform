from __future__ import annotations

import pytest
from artana_evidence_db import kernel_runtime_factories
from artana_evidence_db.read_model_support import (
    ProjectorBackedGraphReadModelUpdateDispatcher,
)
from artana_evidence_db.relation_autopromotion_policy import AutoPromotionPolicy
from sqlalchemy.orm import Session


def test_build_relation_repository_uses_service_local_autopromotion_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_RELATION_AUTOPROMOTE_ENABLED", "0")
    monkeypatch.setenv("GRAPH_RELATION_AUTOPROMOTE_MIN_DISTINCT_SOURCES", "6")

    repository = kernel_runtime_factories.build_relation_repository(
        Session(),
    )
    policy = repository._auto_promotion_policy  # noqa: SLF001

    assert isinstance(policy, AutoPromotionPolicy)
    assert policy.enabled is False
    assert policy.min_distinct_sources == 6


def test_build_graph_read_model_update_dispatcher_uses_local_dispatcher() -> None:
    dispatcher = kernel_runtime_factories.build_graph_read_model_update_dispatcher(
        Session(),
    )

    assert isinstance(dispatcher, ProjectorBackedGraphReadModelUpdateDispatcher)
    assert dispatcher.projectors["entity_neighbors"].__class__.__module__ == (
        "artana_evidence_db.entity_neighbors_projector"
    )
    assert dispatcher.projectors["entity_relation_summary"].__class__.__module__ == (
        "artana_evidence_db.entity_relation_summary_projector"
    )
    assert dispatcher.projectors["entity_claim_summary"].__class__.__module__ == (
        "artana_evidence_db.entity_claim_summary_projector"
    )
    assert dispatcher.projectors["entity_embedding_status"].__class__.__module__ == (
        "artana_evidence_db.entity_embedding_status_projector"
    )
    assert dispatcher.projectors["entity_mechanism_paths"].__class__.__module__ == (
        "artana_evidence_db.entity_mechanism_paths_projector"
    )


def test_create_kernel_relation_suggestion_service_uses_local_embedding_repo() -> None:
    service = kernel_runtime_factories.create_kernel_relation_suggestion_service(
        Session(),
    )

    assert service._embeddings.__class__.__module__ == (  # noqa: SLF001
        "artana_evidence_db.entity_embedding_repository"
    )
