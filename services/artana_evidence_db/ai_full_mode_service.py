"""Application service for DB-owned AI Full Mode governance."""

from __future__ import annotations

from artana_evidence_db.ai_full_mode_concept_service import AIFullModeConceptMixin
from artana_evidence_db.ai_full_mode_decision_connector_service import (
    AIFullModeDecisionConnectorMixin,
)
from artana_evidence_db.ai_full_mode_graph_change_service import (
    AIFullModeGraphChangeMixin,
)
from artana_evidence_db.ai_full_mode_repository_mixin import AIFullModeRepositoryMixin
from artana_evidence_db.ai_full_mode_support import resolve_ai_full_source_ref
from artana_evidence_db.concept_repository import GraphConceptRepository
from artana_evidence_db.kernel_services import KernelRelationClaimService
from artana_evidence_db.semantic_ports import DictionaryPort
from sqlalchemy.orm import Session


class AIFullModeService(
    AIFullModeConceptMixin,
    AIFullModeGraphChangeMixin,
    AIFullModeDecisionConnectorMixin,
    AIFullModeRepositoryMixin,
):
    """Owns AI Full Mode proposal, duplicate, and decision workflows."""

    def __init__(
        self,
        *,
        session: Session,
        dictionary_service: DictionaryPort,
        relation_claim_service: KernelRelationClaimService | None = None,
    ) -> None:
        self._session = session
        self._dictionary = dictionary_service
        self._concepts = GraphConceptRepository(session)
        self._relation_claim_service = relation_claim_service


__all__ = ["AIFullModeService", "resolve_ai_full_source_ref"]
