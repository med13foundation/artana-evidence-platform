"""Service-local protocols and value types for graph-domain adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.kernel_domain_models import (
    DictionarySearchResult,
    KernelRelation,
    KernelSourceDocumentReference,
)

ReasoningPathKind = Literal["MECHANISM"]
ReasoningPathStatus = Literal["ACTIVE", "STALE"]


class ClaimRelationConstraintError(Exception):
    """Raised when claim-relation writes violate storage constraints."""


@dataclass(frozen=True)
class ReasoningPathWrite:
    """Write payload for one reasoning path row."""

    research_space_id: str
    path_kind: ReasoningPathKind
    status: ReasoningPathStatus
    start_entity_id: str
    end_entity_id: str
    root_claim_id: str
    path_length: int
    confidence: float
    path_signature_hash: str
    generated_by: str | None
    metadata: JSONObject


@dataclass(frozen=True)
class ReasoningPathStepWrite:
    """Write payload for one reasoning path step row."""

    step_index: int
    source_claim_id: str
    target_claim_id: str
    claim_relation_id: str
    canonical_relation_id: str | None
    metadata: JSONObject


@dataclass(frozen=True)
class ReasoningPathWriteBundle:
    """Write bundle containing a path row and its ordered steps."""

    path: ReasoningPathWrite
    steps: tuple[ReasoningPathStepWrite, ...]


class DictionarySearchRepository(Protocol):
    """Minimal repository surface needed for deterministic dictionary search."""

    def search_dictionary(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None = None,
        domain_context: str | None = None,
        limit: int = 50,
        query_embeddings: dict[str, list[float]] | None = None,
        include_inactive: bool = False,
    ) -> list[DictionarySearchResult]: ...


class KernelRelationProjectionSourceRepository(Protocol):
    """Minimal projection-lineage surface needed by graph invariants."""

    def list_orphan_relations(
        self,
        *,
        research_space_id: str | None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]: ...

    def count_orphan_relations(
        self,
        *,
        research_space_id: str | None,
    ) -> int: ...

    def has_projection_for_relation(
        self,
        *,
        research_space_id: str,
        relation_id: str,
    ) -> bool: ...


class SourceDocumentReferencePort(Protocol):
    """Lookup contract for graph-local source-document references."""

    def get_by_id(
        self,
        document_id: UUID,
    ) -> KernelSourceDocumentReference | None: ...


__all__ = [
    "ClaimRelationConstraintError",
    "DictionarySearchRepository",
    "KernelRelationProjectionSourceRepository",
    "ReasoningPathKind",
    "ReasoningPathStepWrite",
    "ReasoningPathStatus",
    "ReasoningPathWrite",
    "ReasoningPathWriteBundle",
    "SourceDocumentReferencePort",
]
