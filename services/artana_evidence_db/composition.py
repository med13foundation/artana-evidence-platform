"""Service-local composition helpers for the standalone graph API."""

from __future__ import annotations

from artana_evidence_db.kernel_repositories import (
    SqlAlchemyKernelEntityRepository,
    SqlAlchemyKernelObservationRepository,
)
from artana_evidence_db.kernel_runtime_factories import (
    build_relation_repository,
)
from artana_evidence_db.kernel_services import KernelObservationService
from artana_evidence_db.phi_encryption_support import (
    build_phi_encryption_service_from_env,
    is_phi_encryption_enabled,
)
from sqlalchemy.orm import Session

from .governance import (
    build_concept_service,
    build_dictionary_repository,
    build_dictionary_service,
)
from .runtime.pack_registry import create_graph_domain_pack


def build_entity_repository(session: Session) -> SqlAlchemyKernelEntityRepository:
    """Build the graph-service entity repository with local security wiring."""
    enable_phi_encryption = is_phi_encryption_enabled()
    phi_encryption_service = (
        build_phi_encryption_service_from_env() if enable_phi_encryption else None
    )
    return SqlAlchemyKernelEntityRepository(
        session,
        phi_encryption_service=phi_encryption_service,
        enable_phi_encryption=enable_phi_encryption,
    )


def build_observation_service(
    session: Session,
) -> KernelObservationService:
    """Build the graph-service observation service."""
    return KernelObservationService(
        observation_repo=SqlAlchemyKernelObservationRepository(
            session,
        ),
        entity_repo=build_entity_repository(session),
        dictionary_repo=build_dictionary_service(
            session,
            dictionary_loading_extension=(
                create_graph_domain_pack().dictionary_loading_extension
            ),
        ),
    )


__all__ = [
    "build_concept_service",
    "build_dictionary_repository",
    "build_dictionary_service",
    "build_entity_repository",
    "build_observation_service",
    "build_relation_repository",
]
