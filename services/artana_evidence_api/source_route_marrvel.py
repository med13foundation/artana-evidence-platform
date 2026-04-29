"""MARRVEL public direct-source route plugin."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from artana_evidence_api.auth import HarnessUser, get_current_harness_user
from artana_evidence_api.dependencies import (
    get_direct_source_search_store,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.direct_source_search import (
    DirectSourceSearchStore,
)
from artana_evidence_api.direct_source_search import (
    MarrvelSourceSearchResponse as DurableMarrvelSourceSearchResponse,
)
from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    SourceResultCapture,
    compact_provenance,
    source_result_capture_metadata,
)
from artana_evidence_api.source_route_contracts import (
    DirectSourceRouteDependencies,
    DirectSourceRoutePlugin,
    DirectSourceTypedRoute,
)
from artana_evidence_api.source_route_helpers import parse_source_search_payload
from artana_evidence_api.types.common import JSONObject, json_object_or_empty
from fastapi import Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder

from .routers import marrvel

_CURRENT_USER_DEPENDENCY = Depends(get_current_harness_user)
_MARRVEL_DISCOVERY_SERVICE_DEPENDENCY = Depends(
    marrvel.get_marrvel_discovery_service,
)
_DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY = Depends(get_direct_source_search_store)


# Empty subclass preserves the public v2 OpenAPI schema name.
class MarrvelSourceSearchResponse(DurableMarrvelSourceSearchResponse):
    """Typed v2 MARRVEL source-search response with durable capture metadata."""


def get_marrvel_route_discovery_service(
    marrvel_discovery_service: marrvel.MarrvelDiscoveryService = (
        _MARRVEL_DISCOVERY_SERVICE_DEPENDENCY
    ),
) -> marrvel.MarrvelDiscoveryService:
    """Return the MARRVEL discovery dependency for source-route composition."""

    return marrvel_discovery_service


def marrvel_typed_route_plugin() -> DirectSourceRoutePlugin:
    """Return the typed public MARRVEL route plugin."""

    return DirectSourceRoutePlugin(
        source_key="marrvel",
        routes=(
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/marrvel/searches",
                method="POST",
                endpoint=create_marrvel_source_search,
                response_model=MarrvelSourceSearchResponse,
                status_code=status.HTTP_201_CREATED,
                summary="Search MARRVEL evidence source",
                dependencies=(Depends(require_harness_space_write_access),),
            ),
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/marrvel/searches/{result_id}",
                method="GET",
                endpoint=get_marrvel_source_search,
                response_model=MarrvelSourceSearchResponse,
                summary="Get MARRVEL evidence source search",
                dependencies=(Depends(require_harness_space_read_access),),
            ),
        ),
        create_payload=create_marrvel_route_payload,
        get_payload=get_marrvel_route_payload,
    )


async def create_marrvel_source_search(
    space_id: UUID,
    request: marrvel.MarrvelSearchRequest,
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    marrvel_discovery_service: marrvel.MarrvelDiscoveryService = (
        _MARRVEL_DISCOVERY_SERVICE_DEPENDENCY
    ),
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 compatibility route for MARRVEL source search."""

    return await create_marrvel_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=current_user,
        marrvel_discovery_service=marrvel_discovery_service,
        direct_source_search_store=direct_source_search_store,
    )


def get_marrvel_source_search(
    space_id: UUID,
    result_id: UUID,
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    marrvel_discovery_service: marrvel.MarrvelDiscoveryService = (
        _MARRVEL_DISCOVERY_SERVICE_DEPENDENCY
    ),
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 compatibility route for MARRVEL source-search lookup."""

    return get_marrvel_source_search_payload(
        space_id=space_id,
        search_id=result_id,
        current_user=current_user,
        marrvel_discovery_service=marrvel_discovery_service,
        direct_source_search_store=direct_source_search_store,
    )


def _marrvel_result_payload(
    result: object,
    *,
    source_capture: JSONObject | None = None,
) -> JSONObject:
    payload = json_object_or_empty(jsonable_encoder(result))
    if source_capture is not None:
        payload["source_capture"] = source_capture
    return payload


def _marrvel_source_capture(result: marrvel.MarrvelSearchResponse) -> JSONObject:
    result_count = sum(result.panel_counts.values()) if result.panel_counts else 0
    return source_result_capture_metadata(
        source_key="marrvel",
        capture_stage=SourceCaptureStage.SEARCH_RESULT,
        capture_method="direct_source_search",
        locator=f"marrvel:search:{result.id}",
        search_id=str(result.id),
        query=result.query_value,
        query_payload={
            "query_mode": result.query_mode,
            "query_value": result.query_value,
            "gene_symbol": result.gene_symbol,
            "taxon_id": result.taxon_id,
            "available_panels": list(result.available_panels),
        },
        result_count=result_count,
        provenance=compact_provenance(
            status=result.status,
            gene_found=result.gene_found,
            resolved_gene_symbol=result.resolved_gene_symbol,
            resolved_variant=result.resolved_variant,
            panel_counts=result.panel_counts,
        ),
    )


_MARRVEL_VARIANT_PANEL_KEYS = frozenset(
    {
        "clinvar",
        "mutalyzer",
        "transvar",
        "gnomad_variant",
        "geno2mp_variant",
        "dgv_variant",
        "decipher_variant",
    },
)


def _marrvel_panel_records(result: marrvel.MarrvelSearchResponse) -> list[JSONObject]:
    records: list[JSONObject] = []
    for panel_name, payload in result.panels.items():
        panel_items = payload if isinstance(payload, list) else [payload]
        if not panel_items:
            continue
        for item_index, item in enumerate(panel_items):
            panel_payload = json_object_or_empty(item)
            variant_panel = panel_name in _MARRVEL_VARIANT_PANEL_KEYS
            record: JSONObject = {
                **panel_payload,
                "marrvel_record_id": f"{result.id}:{panel_name}:{item_index}",
                "panel_name": panel_name,
                "panel_family": "variant" if variant_panel else "context",
                "variant_aware_recommended": variant_panel,
                "query_mode": result.query_mode,
                "query_value": result.query_value,
                "gene_symbol": result.resolved_gene_symbol or result.gene_symbol,
                "resolved_gene_symbol": result.resolved_gene_symbol,
                "resolved_variant": result.resolved_variant,
                "taxon_id": result.taxon_id,
                "panel_payload": panel_payload,
            }
            hgvs_notation = _marrvel_hgvs_notation(result=result, record=panel_payload)
            if hgvs_notation is not None:
                record["hgvs_notation"] = hgvs_notation
            records.append(record)
    return records


def _marrvel_hgvs_notation(
    *,
    result: marrvel.MarrvelSearchResponse,
    record: JSONObject,
) -> str | None:
    for value in (
        record.get("hgvs_notation"),
        record.get("hgvs"),
        record.get("variant"),
        record.get("cdna_change"),
        record.get("protein_change"),
        result.resolved_variant,
        result.query_value if result.query_mode != "gene" else None,
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _durable_marrvel_source_search_response(
    *,
    result: marrvel.MarrvelSearchResponse,
    source_capture: SourceResultCapture,
    created_at: datetime,
    completed_at: datetime,
) -> DurableMarrvelSourceSearchResponse:
    records = _marrvel_panel_records(result)
    return DurableMarrvelSourceSearchResponse(
        id=result.id,
        space_id=result.space_id,
        query=result.query_value,
        query_mode=result.query_mode,
        query_value=result.query_value,
        gene_symbol=result.gene_symbol,
        resolved_gene_symbol=result.resolved_gene_symbol,
        resolved_variant=result.resolved_variant,
        taxon_id=result.taxon_id,
        gene_found=result.gene_found,
        gene_info=result.gene_info,
        omim_count=result.omim_count,
        variant_count=result.variant_count,
        panel_counts=result.panel_counts,
        panels=result.panels,
        available_panels=result.available_panels,
        record_count=len(records),
        records=records,
        created_at=created_at,
        completed_at=completed_at,
        source_capture=source_capture,
    )


async def create_marrvel_source_search_payload(
    *,
    space_id: UUID,
    request: marrvel.MarrvelSearchRequest,
    current_user: HarnessUser,
    marrvel_discovery_service: marrvel.MarrvelDiscoveryService,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    created_at = datetime.now(UTC)
    marrvel_result = await marrvel.create_marrvel_search(
        space_id=space_id,
        request=request,
        current_user=current_user,
        marrvel_discovery_service=marrvel_discovery_service,
    )
    completed_at = datetime.now(UTC)
    source_capture = SourceResultCapture.model_validate(
        _marrvel_source_capture(marrvel_result),
    )
    durable_result = _durable_marrvel_source_search_response(
        result=marrvel_result,
        source_capture=source_capture,
        created_at=created_at,
        completed_at=completed_at,
    )
    saved_result = direct_source_search_store.save(
        durable_result,
        created_by=current_user.id,
    )
    return _marrvel_result_payload(
        saved_result,
        source_capture=saved_result.source_capture.to_metadata(),
    )


def get_marrvel_source_search_payload(
    *,
    space_id: UUID,
    search_id: UUID,
    current_user: HarnessUser,
    marrvel_discovery_service: marrvel.MarrvelDiscoveryService | None,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    stored_result = direct_source_search_store.get(
        space_id=space_id,
        source_key="marrvel",
        search_id=search_id,
    )
    if isinstance(stored_result, DurableMarrvelSourceSearchResponse):
        return _marrvel_result_payload(
            stored_result,
            source_capture=stored_result.source_capture.to_metadata(),
        )
    if marrvel_discovery_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MARRVEL discovery service is not available.",
        )

    marrvel_result = marrvel.get_marrvel_search(
        space_id=space_id,
        result_id=search_id,
        current_user=current_user,
        marrvel_discovery_service=marrvel_discovery_service,
    )
    completed_at = datetime.now(UTC)
    source_capture = SourceResultCapture.model_validate(
        _marrvel_source_capture(marrvel_result),
    )
    durable_result = _durable_marrvel_source_search_response(
        result=marrvel_result,
        source_capture=source_capture,
        created_at=completed_at,
        completed_at=completed_at,
    )
    saved_result = direct_source_search_store.save(
        durable_result,
        created_by=current_user.id,
    )
    return _marrvel_result_payload(
        saved_result,
        source_capture=saved_result.source_capture.to_metadata(),
    )


async def create_marrvel_route_payload(
    space_id: UUID,
    request_payload: JSONObject,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Create a MARRVEL search from the generic route payload."""

    request = parse_source_search_payload(request_payload, marrvel.MarrvelSearchRequest)
    marrvel_discovery_service = cast(
        "marrvel.MarrvelDiscoveryService | None",
        dependencies.source_dependency("marrvel"),
    )
    if marrvel_discovery_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MARRVEL discovery service is not available.",
        )
    return await create_marrvel_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=dependencies.current_user,
        marrvel_discovery_service=marrvel_discovery_service,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


def get_marrvel_route_payload(
    space_id: UUID,
    search_id: UUID,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Return a MARRVEL search from the generic route lookup."""

    marrvel_discovery_service = cast(
        "marrvel.MarrvelDiscoveryService | None",
        dependencies.source_dependency("marrvel"),
    )
    return get_marrvel_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        current_user=dependencies.current_user,
        marrvel_discovery_service=marrvel_discovery_service,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


__all__ = [
    "MarrvelSourceSearchResponse",
    "create_marrvel_source_search",
    "create_marrvel_route_payload",
    "create_marrvel_source_search_payload",
    "get_marrvel_route_discovery_service",
    "get_marrvel_source_search",
    "get_marrvel_route_payload",
    "get_marrvel_source_search_payload",
    "marrvel_typed_route_plugin",
]
