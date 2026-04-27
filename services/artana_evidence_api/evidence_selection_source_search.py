"""Tool-backed source-search runner for evidence-selection harness runs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from artana_evidence_api.direct_source_search import (
    AlphaFoldSourceSearchRequest,
    ClinicalTrialsSourceSearchRequest,
    ClinVarSourceSearchRequest,
    DirectSourceSearchRecord,
    DirectSourceSearchStore,
    DrugBankSourceSearchRequest,
    MarrvelSourceSearchResponse,
    MGISourceSearchRequest,
    PubMedSourceSearchResponse,
    UniProtSourceSearchRequest,
    ZFINSourceSearchRequest,
    run_alphafold_direct_search,
    run_clinicaltrials_direct_search,
    run_clinvar_direct_search,
    run_drugbank_direct_search,
    run_mgi_direct_search,
    run_uniprot_direct_search,
    run_zfin_direct_search,
)
from artana_evidence_api.marrvel_discovery import (
    SUPPORTED_MARRVEL_PANELS,
    MarrvelDiscoveryResult,
)
from artana_evidence_api.pubmed_discovery import (
    AdvancedQueryParameters,
    DiscoverySearchJob,
    DiscoverySearchStatus,
    PubMedDiscoveryService,
    RunPubmedSearchRequest,
)
from artana_evidence_api.source_enrichment_bridges import (
    MarrvelDiscoveryServiceProtocol,
    build_alphafold_gateway,
    build_clinicaltrials_gateway,
    build_clinvar_gateway,
    build_drugbank_gateway,
    build_marrvel_discovery_service,
    build_mgi_gateway,
    build_uniprot_gateway,
    build_zfin_gateway,
)
from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    SourceResultCapture,
    compact_provenance,
    source_result_capture_metadata,
)
from artana_evidence_api.types.common import (
    JSONObject,
    json_array_or_empty,
    json_object_or_empty,
)

_SearchHandler = Callable[
    [UUID, UUID | str, "EvidenceSelectionLiveSourceSearch", DirectSourceSearchStore],
    Awaitable[DirectSourceSearchRecord],
]


class EvidenceSelectionSourceSearchError(RuntimeError):
    """Raised when the harness cannot create a requested source search."""


@dataclass(frozen=True, slots=True)
class EvidenceSelectionLiveSourceSearch:
    """One source search the harness should create before screening records."""

    source_key: str
    query_payload: JSONObject
    max_records: int | None = None
    timeout_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class _MarrvelSearchParameters:
    """Validated MARRVEL query parameters for source-search creation."""

    gene_symbol: str | None
    variant_hgvs: str | None
    protein_variant: str | None
    taxon_id: int
    panels: list[str] | None


class EvidenceSelectionSourceSearchRunner:
    """Create durable direct-source searches for the evidence-selection harness."""

    def __init__(
        self,
        *,
        pubmed_discovery_service_factory: (
            Callable[[], AbstractContextManager[PubMedDiscoveryService]] | None
        ) = None,
        marrvel_discovery_service_factory: (
            Callable[[], MarrvelDiscoveryServiceProtocol | None]
        ) = build_marrvel_discovery_service,
    ) -> None:
        self._pubmed_discovery_service_factory = pubmed_discovery_service_factory
        self._marrvel_discovery_service_factory = marrvel_discovery_service_factory

    async def run_search(
        self,
        *,
        space_id: UUID,
        created_by: UUID | str,
        source_search: EvidenceSelectionLiveSourceSearch,
        store: DirectSourceSearchStore,
    ) -> DirectSourceSearchRecord:
        """Run and store one source-specific search."""

        handlers: dict[str, _SearchHandler] = {
            "pubmed": self._run_pubmed,
            "marrvel": self._run_marrvel,
            "clinvar": self._run_clinvar,
            "clinical_trials": self._run_clinicaltrials,
            "uniprot": self._run_uniprot,
            "alphafold": self._run_alphafold,
            "drugbank": self._run_drugbank,
            "mgi": self._run_mgi,
            "zfin": self._run_zfin,
        }
        handler = handlers.get(source_search.source_key)
        if handler is not None:
            return await handler(space_id, created_by, source_search, store)
        raise EvidenceSelectionSourceSearchError(
            "Evidence-selection live source search does not support "
            f"'{source_search.source_key}'.",
        )

    async def _run_pubmed(
        self,
        space_id: UUID,
        created_by: UUID | str,
        source_search: EvidenceSelectionLiveSourceSearch,
        store: DirectSourceSearchStore,
    ) -> DirectSourceSearchRecord:
        if self._pubmed_discovery_service_factory is None:
            raise EvidenceSelectionSourceSearchError(
                "PubMed discovery service is unavailable.",
            )
        parameters = AdvancedQueryParameters.model_validate(
            _pubmed_payload_with_limit(source_search)["parameters"],
        )
        with self._pubmed_discovery_service_factory() as service:
            result = await service.run_pubmed_search(
                owner_id=UUID(str(created_by)),
                request=RunPubmedSearchRequest(
                    session_id=space_id,
                    parameters=parameters,
                ),
            )
        if result.status != DiscoverySearchStatus.COMPLETED:
            raise EvidenceSelectionSourceSearchError(
                "PubMed search did not complete successfully.",
            )
        durable_result = _pubmed_direct_source_record(
            space_id=space_id,
            result=result,
        )
        return store.save(durable_result, created_by=created_by)

    async def _run_marrvel(
        self,
        space_id: UUID,
        created_by: UUID | str,
        source_search: EvidenceSelectionLiveSourceSearch,
        store: DirectSourceSearchStore,
    ) -> DirectSourceSearchRecord:
        request = _marrvel_search_parameters(source_search.query_payload)
        service = self._marrvel_discovery_service_factory()
        if service is None:
            raise EvidenceSelectionSourceSearchError(
                "MARRVEL discovery service is unavailable.",
            )
        created_at = datetime.now(UTC)
        try:
            result = await service.search(
                owner_id=UUID(str(created_by)),
                space_id=space_id,
                gene_symbol=request.gene_symbol,
                variant_hgvs=request.variant_hgvs,
                protein_variant=request.protein_variant,
                taxon_id=request.taxon_id,
                panels=request.panels,
            )
        finally:
            service.close()
        completed_at = datetime.now(UTC)
        durable_result = _marrvel_direct_source_record(
            result=result,
            created_at=created_at,
            completed_at=completed_at,
        )
        return store.save(durable_result, created_by=created_by)

    async def _run_clinvar(
        self,
        space_id: UUID,
        created_by: UUID | str,
        source_search: EvidenceSelectionLiveSourceSearch,
        store: DirectSourceSearchStore,
    ) -> DirectSourceSearchRecord:
        gateway = build_clinvar_gateway()
        if gateway is None:
            raise EvidenceSelectionSourceSearchError("ClinVar gateway is unavailable.")
        return await run_clinvar_direct_search(
            space_id=space_id,
            created_by=created_by,
            request=ClinVarSourceSearchRequest.model_validate(
                _payload_with_limit(source_search),
            ),
            gateway=gateway,
            store=store,
        )

    async def _run_clinicaltrials(
        self,
        space_id: UUID,
        created_by: UUID | str,
        source_search: EvidenceSelectionLiveSourceSearch,
        store: DirectSourceSearchStore,
    ) -> DirectSourceSearchRecord:
        gateway = build_clinicaltrials_gateway()
        if gateway is None:
            raise EvidenceSelectionSourceSearchError(
                "ClinicalTrials.gov gateway is unavailable.",
            )
        return await run_clinicaltrials_direct_search(
            space_id=space_id,
            created_by=created_by,
            request=ClinicalTrialsSourceSearchRequest.model_validate(
                _payload_with_limit(source_search),
            ),
            gateway=gateway,
            store=store,
        )

    async def _run_uniprot(
        self,
        space_id: UUID,
        created_by: UUID | str,
        source_search: EvidenceSelectionLiveSourceSearch,
        store: DirectSourceSearchStore,
    ) -> DirectSourceSearchRecord:
        gateway = build_uniprot_gateway()
        if gateway is None:
            raise EvidenceSelectionSourceSearchError("UniProt gateway is unavailable.")
        return await run_uniprot_direct_search(
            space_id=space_id,
            created_by=created_by,
            request=UniProtSourceSearchRequest.model_validate(
                _payload_with_limit(source_search),
            ),
            gateway=gateway,
            store=store,
        )

    async def _run_alphafold(
        self,
        space_id: UUID,
        created_by: UUID | str,
        source_search: EvidenceSelectionLiveSourceSearch,
        store: DirectSourceSearchStore,
    ) -> DirectSourceSearchRecord:
        gateway = build_alphafold_gateway()
        if gateway is None:
            raise EvidenceSelectionSourceSearchError("AlphaFold gateway is unavailable.")
        return await run_alphafold_direct_search(
            space_id=space_id,
            created_by=created_by,
            request=AlphaFoldSourceSearchRequest.model_validate(
                _payload_with_limit(source_search),
            ),
            gateway=gateway,
            store=store,
        )

    async def _run_drugbank(
        self,
        space_id: UUID,
        created_by: UUID | str,
        source_search: EvidenceSelectionLiveSourceSearch,
        store: DirectSourceSearchStore,
    ) -> DirectSourceSearchRecord:
        gateway = build_drugbank_gateway()
        if gateway is None:
            raise EvidenceSelectionSourceSearchError("DrugBank gateway is unavailable.")
        return await run_drugbank_direct_search(
            space_id=space_id,
            created_by=created_by,
            request=DrugBankSourceSearchRequest.model_validate(
                _payload_with_limit(source_search),
            ),
            gateway=gateway,
            store=store,
        )

    async def _run_mgi(
        self,
        space_id: UUID,
        created_by: UUID | str,
        source_search: EvidenceSelectionLiveSourceSearch,
        store: DirectSourceSearchStore,
    ) -> DirectSourceSearchRecord:
        gateway = build_mgi_gateway()
        if gateway is None:
            raise EvidenceSelectionSourceSearchError("MGI gateway is unavailable.")
        return await run_mgi_direct_search(
            space_id=space_id,
            created_by=created_by,
            request=MGISourceSearchRequest.model_validate(
                _payload_with_limit(source_search),
            ),
            gateway=gateway,
            store=store,
        )

    async def _run_zfin(
        self,
        space_id: UUID,
        created_by: UUID | str,
        source_search: EvidenceSelectionLiveSourceSearch,
        store: DirectSourceSearchStore,
    ) -> DirectSourceSearchRecord:
        gateway = build_zfin_gateway()
        if gateway is None:
            raise EvidenceSelectionSourceSearchError("ZFIN gateway is unavailable.")
        return await run_zfin_direct_search(
            space_id=space_id,
            created_by=created_by,
            request=ZFINSourceSearchRequest.model_validate(
                _payload_with_limit(source_search),
            ),
            gateway=gateway,
            store=store,
        )


def _payload_with_limit(source_search: EvidenceSelectionLiveSourceSearch) -> JSONObject:
    payload: JSONObject = dict(source_search.query_payload)
    if source_search.max_records is not None and "max_results" not in payload:
        payload["max_results"] = source_search.max_records
    return payload


def validate_live_source_search(source_search: EvidenceSelectionLiveSourceSearch) -> None:
    """Validate a live source-search payload before external source side effects."""

    validator = _LIVE_SOURCE_SEARCH_VALIDATORS.get(source_search.source_key)
    if validator is not None:
        validator(source_search)
        return
    raise EvidenceSelectionSourceSearchError(
        "Evidence-selection live source search does not support "
        f"'{source_search.source_key}'.",
    )


def _validate_pubmed_source_search(
    source_search: EvidenceSelectionLiveSourceSearch,
) -> None:
    AdvancedQueryParameters.model_validate(
        _pubmed_payload_with_limit(source_search)["parameters"],
    )


def _validate_marrvel_source_search(
    source_search: EvidenceSelectionLiveSourceSearch,
) -> None:
    _marrvel_search_parameters(source_search.query_payload)


def _validate_clinvar_source_search(
    source_search: EvidenceSelectionLiveSourceSearch,
) -> None:
    ClinVarSourceSearchRequest.model_validate(_payload_with_limit(source_search))


def _validate_clinicaltrials_source_search(
    source_search: EvidenceSelectionLiveSourceSearch,
) -> None:
    ClinicalTrialsSourceSearchRequest.model_validate(_payload_with_limit(source_search))


def _validate_uniprot_source_search(
    source_search: EvidenceSelectionLiveSourceSearch,
) -> None:
    UniProtSourceSearchRequest.model_validate(_payload_with_limit(source_search))


def _validate_alphafold_source_search(
    source_search: EvidenceSelectionLiveSourceSearch,
) -> None:
    AlphaFoldSourceSearchRequest.model_validate(_payload_with_limit(source_search))


def _validate_drugbank_source_search(
    source_search: EvidenceSelectionLiveSourceSearch,
) -> None:
    DrugBankSourceSearchRequest.model_validate(_payload_with_limit(source_search))


def _validate_mgi_source_search(
    source_search: EvidenceSelectionLiveSourceSearch,
) -> None:
    MGISourceSearchRequest.model_validate(_payload_with_limit(source_search))


def _validate_zfin_source_search(
    source_search: EvidenceSelectionLiveSourceSearch,
) -> None:
    ZFINSourceSearchRequest.model_validate(_payload_with_limit(source_search))


_LIVE_SOURCE_SEARCH_VALIDATORS: dict[
    str,
    Callable[[EvidenceSelectionLiveSourceSearch], None],
] = {
    "pubmed": _validate_pubmed_source_search,
    "marrvel": _validate_marrvel_source_search,
    "clinvar": _validate_clinvar_source_search,
    "clinical_trials": _validate_clinicaltrials_source_search,
    "uniprot": _validate_uniprot_source_search,
    "alphafold": _validate_alphafold_source_search,
    "drugbank": _validate_drugbank_source_search,
    "mgi": _validate_mgi_source_search,
    "zfin": _validate_zfin_source_search,
}


def _pubmed_payload_with_limit(
    source_search: EvidenceSelectionLiveSourceSearch,
) -> JSONObject:
    payload: JSONObject = dict(source_search.query_payload)
    raw_parameters = payload.get("parameters")
    parameters = (
        dict(raw_parameters) if isinstance(raw_parameters, dict) else dict(payload)
    )
    if source_search.max_records is not None and "max_results" not in parameters:
        parameters["max_results"] = source_search.max_records
    return {"parameters": parameters}


def _marrvel_search_parameters(payload: JSONObject) -> _MarrvelSearchParameters:
    gene_symbol = _optional_nonempty_string(payload, "gene_symbol")
    variant_hgvs = _optional_nonempty_string(payload, "variant_hgvs")
    protein_variant = _optional_nonempty_string(payload, "protein_variant")
    if variant_hgvs is not None and protein_variant is not None:
        raise EvidenceSelectionSourceSearchError(
            "Provide either variant_hgvs or protein_variant, not both.",
        )
    if gene_symbol is None and variant_hgvs is None and protein_variant is None:
        raise EvidenceSelectionSourceSearchError(
            "Provide at least one of gene_symbol, variant_hgvs, or protein_variant.",
        )
    taxon_id = _marrvel_taxon_id(payload)
    panels = _marrvel_panels(payload)
    return _MarrvelSearchParameters(
        gene_symbol=gene_symbol,
        variant_hgvs=variant_hgvs,
        protein_variant=protein_variant,
        taxon_id=taxon_id,
        panels=panels,
    )


def _optional_nonempty_string(payload: JSONObject, key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise EvidenceSelectionSourceSearchError(f"{key} must be a non-empty string.")
    return value.strip()


def _marrvel_taxon_id(payload: JSONObject) -> int:
    value = payload.get("taxon_id", 9606)
    if not isinstance(value, int) or value < 1:
        raise EvidenceSelectionSourceSearchError("taxon_id must be a positive integer.")
    return value


def _marrvel_panels(payload: JSONObject) -> list[str] | None:
    raw_panels = payload.get("panels")
    if raw_panels is None:
        return None
    if not isinstance(raw_panels, list) or not all(
        isinstance(panel, str) and panel for panel in raw_panels
    ):
        raise EvidenceSelectionSourceSearchError(
            "panels must be a list of supported MARRVEL panel names.",
        )
    unsupported = sorted(set(raw_panels) - set(SUPPORTED_MARRVEL_PANELS))
    if unsupported:
        raise EvidenceSelectionSourceSearchError(
            f"Unsupported MARRVEL panels: {', '.join(unsupported)}.",
        )
    return list(raw_panels)


def _pubmed_direct_source_record(
    *,
    space_id: UUID,
    result: DiscoverySearchJob,
) -> PubMedSourceSearchResponse:
    records = [
        json_object_or_empty(record)
        for record in json_array_or_empty(result.result_metadata.get("preview_records"))
    ]
    completed_at = result.completed_at or result.updated_at or result.created_at
    source_capture = source_result_capture_metadata(
        source_key="pubmed",
        capture_stage=SourceCaptureStage.SEARCH_RESULT,
        capture_method="direct_source_search",
        locator=f"pubmed:search:{result.id}",
        external_id=str(result.id),
        retrieved_at=completed_at,
        search_id=str(result.id),
        query=result.query_preview,
        query_payload=result.parameters.model_dump(mode="json"),
        result_count=result.total_results,
        provenance=compact_provenance(
            provider=result.provider.value,
            status=result.status.value,
            storage_key=result.storage_key,
        ),
    )
    return PubMedSourceSearchResponse(
        id=result.id,
        space_id=space_id,
        owner_id=result.owner_id,
        session_id=result.session_id,
        query=result.query_preview,
        query_preview=result.query_preview,
        parameters=result.parameters,
        total_results=result.total_results,
        result_metadata=result.result_metadata,
        record_count=len(records),
        records=records,
        error_message=result.error_message,
        storage_key=result.storage_key,
        created_at=result.created_at,
        updated_at=result.updated_at,
        completed_at=completed_at,
        source_capture=SourceResultCapture.model_validate(source_capture),
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


def _marrvel_direct_source_record(
    *,
    result: MarrvelDiscoveryResult,
    created_at: datetime,
    completed_at: datetime,
) -> MarrvelSourceSearchResponse:
    records = _marrvel_panel_records(result)
    source_capture = source_result_capture_metadata(
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
        result_count=len(records),
        provenance=compact_provenance(
            status=result.status,
            gene_found=result.gene_found,
            resolved_gene_symbol=result.resolved_gene_symbol,
            resolved_variant=result.resolved_variant,
            panel_counts=result.panel_counts,
        ),
    )
    return MarrvelSourceSearchResponse(
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
        source_capture=SourceResultCapture.model_validate(source_capture),
    )


def _marrvel_panel_records(result: MarrvelDiscoveryResult) -> list[JSONObject]:
    records: list[JSONObject] = []
    for panel_name, payload in result.panels.items():
        panel_items = payload if isinstance(payload, list) else [payload]
        for item_index, item in enumerate(panel_items):
            panel_payload = json_object_or_empty(item)
            if not panel_payload:
                continue
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
    result: MarrvelDiscoveryResult,
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


__all__ = [
    "EvidenceSelectionLiveSourceSearch",
    "EvidenceSelectionSourceSearchError",
    "EvidenceSelectionSourceSearchRunner",
    "validate_live_source_search",
]
