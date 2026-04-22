"""Domain contracts for ontology loader ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from uuid import UUID

    from src.type_definitions.common import JSONObject


class OntologyNamespace(StrEnum):
    """Well-known ontology namespaces."""

    HPO = "HP"
    UBERON = "UBERON"
    CELL_ONTOLOGY = "CL"
    GENE_ONTOLOGY = "GO"


@dataclass(frozen=True, slots=True)
class OntologyTerm:
    """One parsed ontology term from an OBO/OWL release."""

    id: str
    name: str
    definition: str = ""
    synonyms: tuple[str, ...] = ()
    parents: tuple[str, ...] = ()
    xrefs: tuple[str, ...] = ()
    is_obsolete: bool = False
    namespace: str = ""
    comment: str = ""


@dataclass(frozen=True, slots=True)
class OntologyRelease:
    """Metadata about one ontology release."""

    version: str
    download_url: str
    format: str = "obo"
    release_date: str | None = None


@dataclass(frozen=True, slots=True)
class OntologyFetchResult:
    """Result of fetching and parsing one ontology release."""

    terms: list[OntologyTerm]
    release: OntologyRelease
    fetched_term_count: int = 0
    checkpoint_after: JSONObject | None = None


@dataclass(frozen=True, slots=True)
class OntologyIngestionSummary:
    """Summary of one ontology loader run."""

    source_id: UUID
    ingestion_job_id: UUID | None = None
    release_version: str = ""
    terms_fetched: int = 0
    terms_imported: int = 0
    entities_created: int = 0
    entities_updated: int = 0
    alias_candidates_count: int = 0
    aliases_registered: int = 0
    aliases_persisted: int = 0
    aliases_skipped: int = 0
    alias_entities_touched: int = 0
    alias_errors: tuple[str, ...] = ()
    aliases_persisted_by_namespace_entity_type: dict[str, int] = field(
        default_factory=dict,
    )
    hierarchy_edges: int = 0
    hierarchy_edges_created: int = 0
    xref_edges_created: int = 0
    skipped_obsolete: int = 0
    checkpoint_before: JSONObject | None = None
    checkpoint_after: JSONObject | None = None


@runtime_checkable
class OntologyGateway(Protocol):
    """Fetch and parse one ontology release."""

    async def fetch_release(
        self,
        *,
        version: str | None = None,
        format_preference: str = "obo",
        namespace_filter: str | None = None,
        max_terms: int | None = None,
    ) -> OntologyFetchResult:
        """Fetch terms from the ontology source."""
        ...

    async def get_latest_version(self) -> str | None:
        """Return the latest available release version, or None."""
        ...


__all__ = [
    "OntologyFetchResult",
    "OntologyGateway",
    "OntologyIngestionSummary",
    "OntologyNamespace",
    "OntologyRelease",
    "OntologyTerm",
]
