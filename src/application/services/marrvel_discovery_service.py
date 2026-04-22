"""Application service for richer MARRVEL exploration queries."""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, Self, TypeGuard, runtime_checkable
from uuid import UUID, uuid4

from src.application.services._marrvel_discovery_helpers import (
    SUPPORTED_MARRVEL_PANELS,
    MarrvelQueryMode,
    _as_json_object,
    _build_marrvel_phenotype_association,
    _count_panel_items,
    _extract_entrez_id,
    _extract_nested_record,
    _gather_panels,
    _normalize_gene_symbol,
    _normalize_requested_panels,
    _resolve_gene_symbol_from_gene_payload,
    _resolve_gene_symbol_from_transvar,
    _resolve_query_input,
    _resolve_status,
    _resolve_variant_from_mutalyzer,
    _resolve_variant_from_transvar,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Sequence
    from types import TracebackType

    from src.type_definitions.common import JSONObject, JSONValue

logger = logging.getLogger(__name__)


@runtime_checkable
class MarrvelIngestorPort(Protocol):
    """Minimal ingestor contract needed by the discovery service."""

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None: ...

    async def fetch_gene_info(self, taxon_id: int, symbol: str) -> JSONValue | None: ...

    async def fetch_omim_data(self, gene_symbol: str) -> JSONValue | None: ...

    async def fetch_dbnsfp_data(self, gene_symbol: str) -> JSONValue | None: ...

    async def fetch_clinvar_data(self, entrez_id: int | str) -> JSONValue | None: ...

    async def fetch_geno2mp_data(self, entrez_id: int) -> JSONValue | None: ...

    async def fetch_gnomad_gene_data(self, entrez_id: int) -> JSONValue | None: ...

    async def fetch_dgv_gene_data(self, entrez_id: int) -> JSONValue | None: ...

    async def fetch_diopt_ortholog_data(self, entrez_id: int) -> JSONValue | None: ...

    async def fetch_diopt_alignment_data(self, entrez_id: int) -> JSONValue | None: ...

    async def fetch_gtex_gene_data(self, entrez_id: int) -> JSONValue | None: ...

    async def fetch_expression_ortholog_data(
        self,
        entrez_id: int,
    ) -> JSONValue | None: ...

    async def fetch_pharos_targets(self, entrez_id: int) -> JSONValue | None: ...

    async def fetch_mutalyzer_data(self, variant_hgvs: str) -> JSONValue | None: ...

    async def fetch_transvar_data(self, protein_variant: str) -> JSONValue | None: ...

    async def fetch_gnomad_variant_data(self, variant: str) -> JSONValue | None: ...

    async def fetch_geno2mp_variant_data(self, variant: str) -> JSONValue | None: ...

    async def fetch_dgv_variant_data(self, variant: str) -> JSONValue | None: ...

    async def fetch_decipher_variant_data(self, variant: str) -> JSONValue | None: ...


class _UnavailableMarrvelIngestor:
    """Lazy placeholder that preserves clean architecture when infra is absent."""

    async def __aenter__(self) -> MarrvelIngestorPort:
        msg = "MARRVEL ingestor implementation is unavailable."
        raise RuntimeError(msg)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        _ = exc_type, exc_val, exc_tb
        return None


class MarrvelIngestorFactory(Protocol):
    """Callable that constructs an ingestor for one discovery request."""

    def __call__(self) -> MarrvelIngestorPort | _UnavailableMarrvelIngestor: ...


def _looks_like_marrvel_ingestor(instance: object) -> TypeGuard[MarrvelIngestorPort]:
    """Return whether the resolved runtime exposes the required ingestor hooks.

    ``MarrvelIngestor`` binds fetch methods dynamically via ``__getattr__``, so
    ``isinstance(..., MarrvelIngestorPort)`` rejects a valid implementation at
    runtime. Use a small duck-typed guard instead.
    """
    required_methods = (
        "__aenter__",
        "__aexit__",
        "fetch_gene_info",
        "fetch_omim_data",
        "fetch_dbnsfp_data",
        "fetch_clinvar_data",
        "fetch_geno2mp_data",
        "fetch_gnomad_gene_data",
        "fetch_dgv_gene_data",
        "fetch_diopt_ortholog_data",
        "fetch_diopt_alignment_data",
        "fetch_gtex_gene_data",
        "fetch_expression_ortholog_data",
        "fetch_pharos_targets",
        "fetch_mutalyzer_data",
        "fetch_transvar_data",
        "fetch_gnomad_variant_data",
        "fetch_geno2mp_variant_data",
        "fetch_dgv_variant_data",
        "fetch_decipher_variant_data",
    )
    return all(
        callable(getattr(instance, method_name, None))
        for method_name in required_methods
    )


def _default_ingestor_factory() -> MarrvelIngestorFactory:
    """Load the infrastructure ingestor lazily without a static layer import."""
    try:
        module = importlib.import_module("src.infrastructure.ingest.marrvel_ingestor")
    except ModuleNotFoundError:
        return _UnavailableMarrvelIngestor
    resolved_factory = getattr(module, "MarrvelIngestor", None)
    if callable(resolved_factory):

        def _factory() -> MarrvelIngestorPort | _UnavailableMarrvelIngestor:
            instance = resolved_factory()
            if isinstance(instance, _UnavailableMarrvelIngestor):
                return instance
            if _looks_like_marrvel_ingestor(instance):
                return instance
            return _UnavailableMarrvelIngestor()

        return _factory
    return _UnavailableMarrvelIngestor


@dataclass(frozen=True)
class MarrvelDiscoveryResult:
    """Result of a MARRVEL discovery/exploration query."""

    id: UUID
    space_id: UUID
    owner_id: UUID
    query_mode: MarrvelQueryMode
    query_value: str
    gene_symbol: str | None
    resolved_gene_symbol: str | None
    resolved_variant: str | None
    taxon_id: int
    status: str  # "completed", "failed", "no_results"
    gene_found: bool
    gene_info: JSONObject | None
    omim_count: int
    variant_count: int
    panel_counts: dict[str, int]
    panels: JSONObject
    available_panels: list[str]
    created_at: datetime


class MarrvelDiscoveryService:
    """Lightweight MARRVEL discovery service for gene and variant exploration."""

    def __init__(
        self,
        ingestor_factory: MarrvelIngestorFactory | None = None,
    ) -> None:
        if ingestor_factory is None:
            ingestor_factory = _default_ingestor_factory()
        self._ingestor_factory = ingestor_factory
        self._results: dict[UUID, MarrvelDiscoveryResult] = {}

    async def search(  # noqa: C901, PLR0912, PLR0913, PLR0915
        self,
        *,
        owner_id: UUID,
        space_id: UUID,
        gene_symbol: str | None = None,
        variant_hgvs: str | None = None,
        protein_variant: str | None = None,
        taxon_id: int = 9606,
        panels: Sequence[str] | None = None,
    ) -> MarrvelDiscoveryResult:
        """Run a MARRVEL exploration query for a gene or variant."""
        result_id = uuid4()
        now = datetime.now(UTC)
        query_mode, query_value = _resolve_query_input(
            gene_symbol=gene_symbol,
            variant_hgvs=variant_hgvs,
            protein_variant=protein_variant,
        )
        requested_panels = _normalize_requested_panels(panels)

        ingestor = self._ingestor_factory()
        try:
            async with ingestor as active_ingestor:
                panels_payload: JSONObject = {}
                requested_gene_symbol = _normalize_gene_symbol(gene_symbol)
                resolved_gene_symbol = None
                resolved_variant = None

                mutalyzer_payload = None
                if variant_hgvs:
                    mutalyzer_payload = await active_ingestor.fetch_mutalyzer_data(
                        variant_hgvs,
                    )
                    if (
                        mutalyzer_payload is not None
                        and "mutalyzer" in requested_panels
                    ):
                        panels_payload["mutalyzer"] = mutalyzer_payload
                    mutalyzer_record = _as_json_object(mutalyzer_payload)
                    resolved_variant = _resolve_variant_from_mutalyzer(
                        mutalyzer_record,
                    )
                    resolved_gene_symbol = (
                        _resolve_gene_symbol_from_gene_payload(
                            _extract_nested_record(mutalyzer_record, "gene"),
                        )
                        or resolved_gene_symbol
                    )

                transvar_payload = None
                if protein_variant:
                    transvar_payload = await active_ingestor.fetch_transvar_data(
                        protein_variant,
                    )
                    if transvar_payload is not None and "transvar" in requested_panels:
                        panels_payload["transvar"] = transvar_payload
                    transvar_record = _as_json_object(transvar_payload)
                    resolved_variant = (
                        _resolve_variant_from_transvar(transvar_record)
                        or resolved_variant
                    )
                    resolved_gene_symbol = (
                        _resolve_gene_symbol_from_transvar(transvar_record)
                        or resolved_gene_symbol
                    )

                gene_info_record = None
                normalized_symbol = requested_gene_symbol or resolved_gene_symbol
                if normalized_symbol is not None:
                    gene_info_payload = await active_ingestor.fetch_gene_info(
                        taxon_id,
                        normalized_symbol,
                    )
                    gene_info_record = _as_json_object(gene_info_payload)
                    if gene_info_record is not None:
                        resolved_gene_symbol = (
                            _resolve_gene_symbol_from_gene_payload(
                                gene_info_record,
                            )
                            or normalized_symbol
                        )

                entrez_id = _extract_entrez_id(gene_info_record)

                if normalized_symbol is not None and entrez_id is not None:
                    gene_panel_tasks: dict[str, Awaitable[JSONValue | None]] = {}
                    if "omim" in requested_panels:
                        gene_panel_tasks["omim"] = active_ingestor.fetch_omim_data(
                            normalized_symbol,
                        )
                    if "dbnsfp" in requested_panels:
                        gene_panel_tasks["dbnsfp"] = active_ingestor.fetch_dbnsfp_data(
                            normalized_symbol,
                        )
                    if "clinvar" in requested_panels:
                        gene_panel_tasks["clinvar"] = (
                            active_ingestor.fetch_clinvar_data(
                                entrez_id,
                            )
                        )
                    if "geno2mp" in requested_panels:
                        gene_panel_tasks["geno2mp"] = (
                            active_ingestor.fetch_geno2mp_data(
                                entrez_id,
                            )
                        )
                    if "gnomad" in requested_panels:
                        gene_panel_tasks["gnomad"] = (
                            active_ingestor.fetch_gnomad_gene_data(entrez_id)
                        )
                    if "dgv" in requested_panels:
                        gene_panel_tasks["dgv"] = active_ingestor.fetch_dgv_gene_data(
                            entrez_id,
                        )
                    if "diopt_orthologs" in requested_panels:
                        gene_panel_tasks["diopt_orthologs"] = (
                            active_ingestor.fetch_diopt_ortholog_data(entrez_id)
                        )
                    if "diopt_alignment" in requested_panels:
                        gene_panel_tasks["diopt_alignment"] = (
                            active_ingestor.fetch_diopt_alignment_data(entrez_id)
                        )
                    if "gtex" in requested_panels:
                        gene_panel_tasks["gtex"] = active_ingestor.fetch_gtex_gene_data(
                            entrez_id,
                        )
                    if "expression" in requested_panels:
                        gene_panel_tasks["expression"] = (
                            active_ingestor.fetch_expression_ortholog_data(entrez_id)
                        )
                    if "pharos" in requested_panels:
                        gene_panel_tasks["pharos"] = (
                            active_ingestor.fetch_pharos_targets(
                                entrez_id,
                            )
                        )
                    gene_panels = await _gather_panels(
                        gene_panel_tasks,
                    )
                    panels_payload.update(gene_panels)

                if resolved_variant is not None:
                    variant_panel_tasks: dict[str, Awaitable[JSONValue | None]] = {}
                    if "gnomad_variant" in requested_panels:
                        variant_panel_tasks["gnomad_variant"] = (
                            active_ingestor.fetch_gnomad_variant_data(resolved_variant)
                        )
                    if "geno2mp_variant" in requested_panels:
                        variant_panel_tasks["geno2mp_variant"] = (
                            active_ingestor.fetch_geno2mp_variant_data(
                                resolved_variant,
                            )
                        )
                    if "dgv_variant" in requested_panels:
                        variant_panel_tasks["dgv_variant"] = (
                            active_ingestor.fetch_dgv_variant_data(resolved_variant)
                        )
                    if "decipher_variant" in requested_panels:
                        variant_panel_tasks["decipher_variant"] = (
                            active_ingestor.fetch_decipher_variant_data(
                                resolved_variant,
                            )
                        )
                    variant_panels = await _gather_panels(
                        variant_panel_tasks,
                    )
                    panels_payload.update(variant_panels)

                panel_counts = {
                    panel_name: _count_panel_items(panel_value)
                    for panel_name, panel_value in panels_payload.items()
                    if panel_name in SUPPORTED_MARRVEL_PANELS
                }
                variant_count = sum(
                    panel_counts.get(panel_name, 0)
                    for panel_name in (
                        "dbnsfp",
                        "clinvar",
                        "geno2mp",
                        "geno2mp_variant",
                        "gnomad_variant",
                    )
                )
                status = _resolve_status(
                    gene_info=gene_info_record,
                    resolved_gene_symbol=resolved_gene_symbol,
                    resolved_variant=resolved_variant,
                    panel_counts=panel_counts,
                )

                result = MarrvelDiscoveryResult(
                    id=result_id,
                    space_id=space_id,
                    owner_id=owner_id,
                    query_mode=query_mode,
                    query_value=query_value,
                    gene_symbol=requested_gene_symbol,
                    resolved_gene_symbol=resolved_gene_symbol,
                    resolved_variant=resolved_variant,
                    taxon_id=taxon_id,
                    status=status,
                    gene_found=resolved_gene_symbol is not None,
                    gene_info=gene_info_record,
                    omim_count=panel_counts.get("omim", 0),
                    variant_count=variant_count,
                    panel_counts=panel_counts,
                    panels=panels_payload,
                    available_panels=list(SUPPORTED_MARRVEL_PANELS),
                    created_at=now,
                )
                self._results[result_id] = result
                return result
        except Exception:  # noqa: BLE001
            logger.exception("MARRVEL discovery failed for %s", query_value)
            result = MarrvelDiscoveryResult(
                id=result_id,
                space_id=space_id,
                owner_id=owner_id,
                query_mode=query_mode,
                query_value=query_value,
                gene_symbol=_normalize_gene_symbol(gene_symbol),
                resolved_gene_symbol=None,
                resolved_variant=None,
                taxon_id=taxon_id,
                status="failed",
                gene_found=False,
                gene_info=None,
                omim_count=0,
                variant_count=0,
                panel_counts={},
                panels={},
                available_panels=list(SUPPORTED_MARRVEL_PANELS),
                created_at=now,
            )
            self._results[result_id] = result
            return result

    async def search_gene(
        self,
        *,
        owner_id: UUID,
        space_id: UUID,
        gene_symbol: str,
        taxon_id: int = 9606,
    ) -> MarrvelDiscoveryResult:
        """Backwards-compatible wrapper for gene-only MARRVEL searches."""
        return await self.search(
            owner_id=owner_id,
            space_id=space_id,
            gene_symbol=gene_symbol,
            taxon_id=taxon_id,
        )

    def get_result(
        self,
        *,
        owner_id: UUID,
        result_id: UUID,
    ) -> MarrvelDiscoveryResult | None:
        """Retrieve a stored discovery result."""
        result = self._results.get(result_id)
        if result is not None and result.owner_id == owner_id:
            return result
        return None

    @staticmethod
    def extract_omim_associations(
        result: MarrvelDiscoveryResult,
        gene_symbol: str | None = None,
    ) -> list[object]:
        """Extract OMIM phenotype associations from a completed result."""
        resolved_gene_symbol = (
            result.resolved_gene_symbol or result.gene_symbol or gene_symbol
        )
        if resolved_gene_symbol is None:
            return []

        omim_payload = result.panels.get("omim") if result.panels else None
        if isinstance(omim_payload, dict):
            omim_entries: list[dict[str, object]] = [omim_payload]
        elif isinstance(omim_payload, list):
            omim_entries = [e for e in omim_payload if isinstance(e, dict)]
        else:
            return []

        associations: list[object] = []
        for omim_entry in omim_entries:
            phenotypes = omim_entry.get("phenotypes", [])
            if not isinstance(phenotypes, list):
                continue
            for phenotype in phenotypes:
                phenotype_name = (
                    phenotype.get("phenotype") if isinstance(phenotype, dict) else None
                )
                if not phenotype_name:
                    continue
                clean_name = str(phenotype_name).strip("{}").strip()
                if clean_name == "":
                    continue
                associations.append(
                    _build_marrvel_phenotype_association(
                        gene_symbol=resolved_gene_symbol,
                        phenotype_label=clean_name,
                    ),
                )
        return associations

    def close(self) -> None:
        """Clean up resources."""


__all__ = [
    "MarrvelDiscoveryResult",
    "MarrvelDiscoveryService",
    "SUPPORTED_MARRVEL_PANELS",
]
