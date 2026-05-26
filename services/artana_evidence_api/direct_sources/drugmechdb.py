"""DrugMechDB curated mechanism-path direct source connector."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID, uuid4

import httpx
import yaml
from artana_evidence_api.direct_sources.capture import (
    build_direct_search_capture,
    json_records,
    single_record_external_id,
)
from artana_evidence_api.source_result_capture import SourceResultCapture
from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DRUGMECHDB_REPOSITORY_URL = "https://github.com/SuLab/DrugMechDB"
DRUGMECHDB_COMMIT_SHA = "41fea1332cdc56abab1c12761edd2e63a01ef9ca"
DRUGMECHDB_INDICATION_PATHS_URL = (
    "https://raw.githubusercontent.com/SuLab/DrugMechDB/"
    f"{DRUGMECHDB_COMMIT_SHA}/indication_paths.yaml"
)
DRUGMECHDB_LICENSE_URL = (
    "https://raw.githubusercontent.com/SuLab/DrugMechDB/"
    f"{DRUGMECHDB_COMMIT_SHA}/LICENSE"
)
DRUGMECHDB_LICENSE = "CC0-1.0"
_DEFAULT_TIMEOUT_SECONDS = 30.0
_USER_AGENT = "artana-evidence-platform/drugmechdb-gateway"


class DrugMechDBSourceSearchRequest(BaseModel):
    """Request payload for bounded DrugMechDB mechanism-path search."""

    model_config = ConfigDict(strict=True)

    query: str | None = Field(default=None, min_length=1, max_length=512)
    drug_name: str | None = Field(default=None, min_length=1, max_length=256)
    drugbank_id: str | None = Field(default=None, min_length=1, max_length=64)
    disease: str | None = Field(default=None, min_length=1, max_length=256)
    disease_mesh: str | None = Field(default=None, min_length=1, max_length=64)
    node_id: str | None = Field(default=None, min_length=1, max_length=128)
    path_id: str | None = Field(default=None, min_length=1, max_length=128)
    max_results: int = Field(default=20, ge=1, le=100)

    @field_validator(
        "query",
        "drug_name",
        "drugbank_id",
        "disease",
        "disease_mesh",
        "node_id",
        "path_id",
    )
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @field_validator("drugbank_id")
    @classmethod
    def _normalize_drugbank_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.upper()
        if normalized.startswith("DB:"):
            return normalized.split(":", 1)[1]
        return normalized

    @field_validator("disease_mesh")
    @classmethod
    def _normalize_disease_mesh(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    @model_validator(mode="after")
    def _validate_filter_input(self) -> DrugMechDBSourceSearchRequest:
        if (
            self.query
            or self.drug_name
            or self.drugbank_id
            or self.disease
            or self.disease_mesh
            or self.node_id
            or self.path_id
        ):
            return self
        msg = (
            "Provide at least one of query, drug_name, drugbank_id, disease, "
            "disease_mesh, node_id, or path_id"
        )
        raise ValueError(msg)

    def query_text(self) -> str:
        """Return the public query string for capture metadata."""

        parts: list[str] = []
        for field_name in (
            "path_id",
            "query",
            "drug_name",
            "drugbank_id",
            "disease",
            "disease_mesh",
            "node_id",
        ):
            value = getattr(self, field_name)
            if value:
                parts.append(f"{field_name}:{value}")
        return " ".join(parts)


class DrugMechDBSourceSearchResponse(BaseModel):
    """Response payload for one captured DrugMechDB direct search."""

    id: UUID
    space_id: UUID
    source_key: Literal["drugmechdb"] = "drugmechdb"
    status: Literal["completed"] = "completed"
    query: str
    drug_name: str | None = None
    drugbank_id: str | None = None
    disease: str | None = None
    disease_mesh: str | None = None
    node_id: str | None = None
    path_id: str | None = None
    max_results: int
    fetched_records: int
    record_count: int
    corpus_size: int
    commit_sha: str
    source_url: str
    repository_url: str
    records: list[JSONObject] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime
    source_capture: SourceResultCapture


@dataclass(frozen=True, slots=True)
class DrugMechDBGatewayFetchResult:
    """Normalized DrugMechDB catalog fetch result."""

    records: list[dict[str, object]]
    fetched_records: int
    corpus_size: int
    commit_sha: str = DRUGMECHDB_COMMIT_SHA
    source_url: str = DRUGMECHDB_INDICATION_PATHS_URL
    repository_url: str = DRUGMECHDB_REPOSITORY_URL
    license_url: str = DRUGMECHDB_LICENSE_URL
    license: str = DRUGMECHDB_LICENSE


class DrugMechDBGatewayError(RuntimeError):
    """Raised when DrugMechDB data cannot be fetched or parsed."""


class DrugMechDBGatewayProtocol(Protocol):
    """Gateway contract for query-time DrugMechDB mechanism-path search."""

    async def fetch_records_async(
        self,
        *,
        query: str | None = None,
        drug_name: str | None = None,
        drugbank_id: str | None = None,
        disease: str | None = None,
        disease_mesh: str | None = None,
        node_id: str | None = None,
        path_id: str | None = None,
        max_results: int = 20,
    ) -> DrugMechDBGatewayFetchResult:
        """Fetch matching DrugMechDB mechanism-path records."""
        ...


class DrugMechDBDirectSourceSearchStore(Protocol):
    """Storage boundary needed by the DrugMechDB direct-search runner."""

    def save(
        self,
        record: DrugMechDBSourceSearchResponse,
        *,
        created_by: UUID | str,
    ) -> DrugMechDBSourceSearchResponse:
        """Store one DrugMechDB source-search response."""
        ...


class DrugMechDBSourceGateway:
    """Fetch the pinned DrugMechDB YAML artifact and render mechanism paths."""

    def __init__(
        self,
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._transport = transport
        self._cached_records: list[dict[str, object]] | None = None

    async def fetch_records_async(
        self,
        *,
        query: str | None = None,
        drug_name: str | None = None,
        drugbank_id: str | None = None,
        disease: str | None = None,
        disease_mesh: str | None = None,
        node_id: str | None = None,
        path_id: str | None = None,
        max_results: int = 20,
    ) -> DrugMechDBGatewayFetchResult:
        """Fetch and filter curated DrugMechDB mechanism paths."""

        records = await self._records()
        filtered = [
            record
            for record in records
            if _matches_request(
                record,
                query=query,
                drug_name=drug_name,
                drugbank_id=drugbank_id,
                disease=disease,
                disease_mesh=disease_mesh,
                node_id=node_id,
                path_id=path_id,
            )
        ]
        return DrugMechDBGatewayFetchResult(
            records=filtered[:max_results],
            fetched_records=len(filtered),
            corpus_size=len(records),
        )

    async def _records(self) -> list[dict[str, object]]:
        if self._cached_records is not None:
            return self._cached_records
        async with self._build_client() as client:
            text = await self._read_url(client, DRUGMECHDB_INDICATION_PATHS_URL)
        self._cached_records = _parse_indication_paths(text)
        if not self._cached_records:
            msg = "DrugMechDB indication_paths.yaml did not contain mechanism paths."
            raise DrugMechDBGatewayError(msg)
        return self._cached_records

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={"User-Agent": _USER_AGENT},
            timeout=self._timeout_seconds,
            transport=self._transport,
            follow_redirects=True,
        )

    @staticmethod
    async def _read_url(client: httpx.AsyncClient, url: str) -> str:
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"DrugMechDB request failed for {url}: {exc}"
            raise DrugMechDBGatewayError(msg) from exc
        return response.text


def build_drugmechdb_gateway() -> DrugMechDBGatewayProtocol:
    """Return the pinned public DrugMechDB mechanism-path gateway."""

    return DrugMechDBSourceGateway()


async def run_drugmechdb_direct_search(
    *,
    space_id: UUID,
    created_by: UUID | str,
    request: DrugMechDBSourceSearchRequest,
    gateway: DrugMechDBGatewayProtocol,
    store: DrugMechDBDirectSourceSearchStore,
) -> DrugMechDBSourceSearchResponse:
    """Fetch DrugMechDB paths and capture them as a direct source search."""

    created_at = datetime.now(UTC)
    fetch_result = await gateway.fetch_records_async(
        query=request.query,
        drug_name=request.drug_name,
        drugbank_id=request.drugbank_id,
        disease=request.disease,
        disease_mesh=request.disease_mesh,
        node_id=request.node_id,
        path_id=request.path_id,
        max_results=request.max_results,
    )
    records = json_records(fetch_result.records)
    completed_at = datetime.now(UTC)
    search_id = uuid4()
    query = request.query_text()
    capture = build_direct_search_capture(
        source_key="drugmechdb",
        search_id=search_id,
        completed_at=completed_at,
        query=query,
        query_payload=request.model_dump(mode="json", exclude_none=True),
        result_count=len(records),
        provider="DrugMechDB",
        external_id=single_record_external_id(records, keys=("path_id",)),
        provenance={
            "fetched_records": fetch_result.fetched_records,
            "corpus_size": fetch_result.corpus_size,
            "commit_sha": fetch_result.commit_sha,
            "source_url": fetch_result.source_url,
            "repository_url": fetch_result.repository_url,
            "license": fetch_result.license,
            "license_url": fetch_result.license_url,
            "content_scope": "curated_drug_mechanism_paths",
            "extraction_policy": "selective_batched_no_auto_bulk_extraction",
        },
    )
    result = DrugMechDBSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        query=query,
        drug_name=request.drug_name,
        drugbank_id=request.drugbank_id,
        disease=request.disease,
        disease_mesh=request.disease_mesh,
        node_id=request.node_id,
        path_id=request.path_id,
        max_results=request.max_results,
        fetched_records=fetch_result.fetched_records,
        record_count=len(records),
        corpus_size=fetch_result.corpus_size,
        commit_sha=fetch_result.commit_sha,
        source_url=fetch_result.source_url,
        repository_url=fetch_result.repository_url,
        records=records,
        created_at=created_at,
        completed_at=completed_at,
        source_capture=SourceResultCapture.model_validate(capture),
    )
    return store.save(result, created_by=created_by)


def _parse_indication_paths(text: str) -> list[dict[str, object]]:
    loaded: object = yaml.safe_load(text)
    if not isinstance(loaded, list):
        msg = "DrugMechDB indication_paths.yaml must be a YAML list."
        raise DrugMechDBGatewayError(msg)
    records: list[dict[str, object]] = []
    for item in loaded:
        path = _string_mapping(item)
        if path is None:
            continue
        record = _path_record(path)
        if record is not None:
            records.append(record)
    return records


def _path_record(path: Mapping[str, object]) -> dict[str, object] | None:
    graph = _string_mapping(path.get("graph"))
    if graph is None:
        return None
    path_id = _text(graph.get("_id"))
    if path_id is None:
        return None
    nodes = _node_records(path.get("nodes"))
    edges = _edge_records(path.get("links"), nodes_by_id=_nodes_by_id(nodes))
    drugbank_curie = _text(graph.get("drugbank"))
    return {
        "source": "drugmechdb",
        "path_id": path_id,
        "drug_name": _text(graph.get("drug")),
        "drugbank_id": _drugbank_id(drugbank_curie),
        "drugbank_curie": drugbank_curie,
        "drug_mesh": _text(graph.get("drug_mesh")),
        "disease_name": _text(graph.get("disease")),
        "disease_mesh": _text(graph.get("disease_mesh")),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
        "node_ids": [node["id"] for node in nodes],
        "references": _string_list(path.get("reference")),
        "license": DRUGMECHDB_LICENSE,
        "source_url": DRUGMECHDB_INDICATION_PATHS_URL,
        "repository_url": DRUGMECHDB_REPOSITORY_URL,
        "license_url": DRUGMECHDB_LICENSE_URL,
        "commit_sha": DRUGMECHDB_COMMIT_SHA,
        "narrative": _path_narrative(path_id=path_id, edges=edges),
    }


def _node_records(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    records: list[dict[str, str]] = []
    for item in value:
        node = _string_mapping(item)
        if node is None:
            continue
        node_id = _text(node.get("id"))
        name = _text(node.get("name"))
        label = _text(node.get("label"))
        if node_id is None or name is None:
            continue
        records.append(
            {
                "id": node_id,
                "name": name,
                "label": label or "Entity",
            },
        )
    return records


def _edge_records(
    value: object,
    *,
    nodes_by_id: Mapping[str, Mapping[str, str]],
) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    records: list[dict[str, str]] = []
    for item in value:
        edge = _string_mapping(item)
        if edge is None:
            continue
        source_id = _text(edge.get("source"))
        target_id = _text(edge.get("target"))
        predicate = _text(edge.get("key"))
        if source_id is None or target_id is None or predicate is None:
            continue
        source_node = nodes_by_id.get(source_id, {})
        target_node = nodes_by_id.get(target_id, {})
        records.append(
            {
                "source_id": source_id,
                "source_name": source_node.get("name", source_id),
                "source_label": source_node.get("label", "Entity"),
                "predicate": predicate,
                "target_id": target_id,
                "target_name": target_node.get("name", target_id),
                "target_label": target_node.get("label", "Entity"),
            },
        )
    return records


def _nodes_by_id(nodes: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {node["id"]: node for node in nodes}


def _matches_request(
    record: Mapping[str, object],
    *,
    query: str | None,
    drug_name: str | None,
    drugbank_id: str | None,
    disease: str | None,
    disease_mesh: str | None,
    node_id: str | None,
    path_id: str | None,
) -> bool:
    filter_matches = (
        not path_id or _matches_text(record.get("path_id"), path_id),
        not drugbank_id
        or _matches_text(record.get("drugbank_id"), drugbank_id)
        or _matches_text(record.get("drugbank_curie"), _drugbank_curie(drugbank_id)),
        not disease_mesh or _matches_text(record.get("disease_mesh"), disease_mesh),
        not node_id or _matches_sequence(record.get("node_ids"), node_id),
        not drug_name or _contains_text(record.get("drug_name"), drug_name),
        not disease
        or _matches_any(
            record,
            disease,
            ("disease_name", "disease_mesh", "path_id", "narrative"),
        ),
    )
    if not all(filter_matches):
        return False
    if not query:
        return True
    return _matches_any(
        record,
        query,
        (
            "path_id",
            "drug_name",
            "drugbank_id",
            "drugbank_curie",
            "disease_name",
            "disease_mesh",
            "node_ids",
            "narrative",
        ),
    )


def _matches_any(
    record: Mapping[str, object],
    needle: str,
    fields: tuple[str, ...],
) -> bool:
    return any(_contains_text(record.get(field), needle) for field in fields)


def _matches_text(value: object, expected: str) -> bool:
    return str(value or "").casefold() == expected.casefold()


def _contains_text(value: object, needle: str) -> bool:
    if isinstance(value, list):
        return _matches_sequence(value, needle)
    return needle.casefold() in str(value or "").casefold()


def _matches_sequence(value: object, needle: str) -> bool:
    if not isinstance(value, list):
        return False
    normalized_needle = needle.casefold()
    return any(normalized_needle in str(item).casefold() for item in value)


def _path_narrative(*, path_id: str, edges: list[dict[str, str]]) -> str:
    if not edges:
        return f"DrugMechDB path {path_id} has no rendered mechanism edges."
    sentences = [
        (
            f"{_entity_label(edge, prefix='source')} {edge['predicate']} "
            f"{_entity_label(edge, prefix='target')}."
        )
        for edge in edges
    ]
    return f"DrugMechDB path {path_id}: {' '.join(sentences)}"


def _entity_label(
    edge: Mapping[str, str], *, prefix: Literal["source", "target"]
) -> str:
    return (
        f"{edge[f'{prefix}_name']} ({edge[f'{prefix}_label']}; {edge[f'{prefix}_id']})"
    )


def _drugbank_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.upper()
    if normalized.startswith("DB:"):
        return normalized.split(":", 1)[1]
    return normalized


def _drugbank_curie(value: str) -> str:
    normalized = value.upper()
    if normalized.startswith("DB:"):
        return normalized
    return f"DB:{normalized}"


def _string_mapping(value: object) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    return {str(key): item for key, item in value.items() if isinstance(key, str)}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, int | float) and not isinstance(value, bool):
        return str(value)
    return None


__all__ = [
    "DRUGMECHDB_COMMIT_SHA",
    "DRUGMECHDB_INDICATION_PATHS_URL",
    "DRUGMECHDB_LICENSE",
    "DRUGMECHDB_LICENSE_URL",
    "DRUGMECHDB_REPOSITORY_URL",
    "DrugMechDBGatewayError",
    "DrugMechDBGatewayFetchResult",
    "DrugMechDBGatewayProtocol",
    "DrugMechDBSourceGateway",
    "DrugMechDBSourceSearchRequest",
    "DrugMechDBSourceSearchResponse",
    "build_drugmechdb_gateway",
    "run_drugmechdb_direct_search",
]
