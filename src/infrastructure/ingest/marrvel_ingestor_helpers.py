"""Helper functions for the MarrvelIngestor implementation."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import quote

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from src.infrastructure.ingest.base_ingestor import BaseIngestor
    from src.type_definitions.common import JSONValue, RawRecord

logger = logging.getLogger(__name__)


async def fetch_data(ingestor: BaseIngestor, **kwargs: JSONValue) -> list[RawRecord]:
    gene_symbols_raw = kwargs.get("gene_symbols")
    if not isinstance(gene_symbols_raw, list):
        gene_symbols_raw = []
    gene_symbols: list[str] = [
        symbol
        for symbol in gene_symbols_raw
        if isinstance(symbol, str) and symbol.strip()
    ]
    if not gene_symbols:
        return []

    taxon_id = _coerce_int(kwargs.get("taxon_id"), 9606)
    include_omim = kwargs.get("include_omim", True)
    include_dbnsfp = kwargs.get("include_dbnsfp", True)
    include_clinvar = kwargs.get("include_clinvar", False)
    include_geno2mp = kwargs.get("include_geno2mp", True)
    include_gnomad = kwargs.get("include_gnomad", True)
    include_dgv = kwargs.get("include_dgv", False)
    include_diopt = kwargs.get("include_diopt", False)
    include_gtex = kwargs.get("include_gtex", False)
    include_expression = kwargs.get("include_expression", False)
    include_pharos = kwargs.get("include_pharos", False)

    all_records: list[RawRecord] = []
    for symbol in gene_symbols:
        record = await fetch_all_for_gene(
            ingestor,
            taxon_id=taxon_id,
            symbol=symbol,
            include_omim=bool(include_omim),
            include_dbnsfp=bool(include_dbnsfp),
            include_clinvar=bool(include_clinvar),
            include_geno2mp=bool(include_geno2mp),
            include_gnomad=bool(include_gnomad),
            include_dgv=bool(include_dgv),
            include_diopt=bool(include_diopt),
            include_gtex=bool(include_gtex),
            include_expression=bool(include_expression),
            include_pharos=bool(include_pharos),
        )
        if record:
            all_records.append(record)
        await asyncio.sleep(0.2)

    return all_records


async def fetch_all_for_gene(  # noqa: C901, PLR0912, PLR0913, PLR0915
    ingestor: BaseIngestor,
    *,
    taxon_id: int,
    symbol: str,
    include_omim: bool = True,
    include_dbnsfp: bool = True,
    include_clinvar: bool = False,
    include_geno2mp: bool = True,
    include_gnomad: bool = True,
    include_dgv: bool = False,
    include_diopt: bool = False,
    include_gtex: bool = False,
    include_expression: bool = False,
    include_pharos: bool = False,
) -> RawRecord | None:
    now = datetime.now(UTC).isoformat()

    gene_info = await fetch_gene_info(ingestor, taxon_id, symbol)
    if gene_info is None:
        logger.info("No gene info found for %s (taxon %d)", symbol, taxon_id)
        return None

    record: RawRecord = {
        "gene_symbol": symbol.upper(),
        "taxon_id": taxon_id,
        "record_type": "gene_aggregate",
        "gene_info": gene_info,
        "omim_entries": [],
        "dbnsfp_variants": [],
        "clinvar_entries": [],
        "geno2mp_entries": [],
        "gnomad_gene": None,
        "dgv_entries": [],
        "diopt_orthologs": [],
        "diopt_alignments": [],
        "gtex_expression": None,
        "ortholog_expression": [],
        "pharos_targets": [],
        "source": "marrvel",
        "fetched_at": now,
    }

    entrez_id = gene_info.get("entrezGeneId") if isinstance(gene_info, dict) else None
    normalized_entrez_id = _coerce_int(entrez_id, -1)

    if include_omim:
        omim_data = await fetch_omim_data(ingestor, symbol)
        if isinstance(omim_data, list):
            record["omim_entries"] = omim_data

    if include_dbnsfp and entrez_id is not None:
        dbnsfp_data = await fetch_dbnsfp_data(ingestor, symbol)
        if isinstance(dbnsfp_data, list):
            record["dbnsfp_variants"] = dbnsfp_data

    if include_clinvar and normalized_entrez_id >= 0:
        clinvar_data = await fetch_clinvar_data(ingestor, normalized_entrez_id)
        if isinstance(clinvar_data, list):
            record["clinvar_entries"] = clinvar_data

    if include_geno2mp and normalized_entrez_id >= 0:
        geno2mp_data = await fetch_geno2mp_data(ingestor, normalized_entrez_id)
        if isinstance(geno2mp_data, list):
            record["geno2mp_entries"] = geno2mp_data

    if include_gnomad and normalized_entrez_id >= 0:
        gnomad_data = await fetch_gnomad_gene_data(ingestor, normalized_entrez_id)
        if isinstance(gnomad_data, dict):
            record["gnomad_gene"] = gnomad_data

    if include_dgv and normalized_entrez_id >= 0:
        dgv_data = await fetch_dgv_gene_data(ingestor, normalized_entrez_id)
        if isinstance(dgv_data, list):
            record["dgv_entries"] = dgv_data

    if include_diopt and normalized_entrez_id >= 0:
        diopt_orthologs = await fetch_diopt_ortholog_data(
            ingestor,
            normalized_entrez_id,
        )
        if isinstance(diopt_orthologs, list):
            record["diopt_orthologs"] = diopt_orthologs
        diopt_alignments = await fetch_diopt_alignment_data(
            ingestor,
            normalized_entrez_id,
        )
        if isinstance(diopt_alignments, dict):
            record["diopt_alignments"] = [diopt_alignments]

    if include_gtex and normalized_entrez_id >= 0:
        gtex_data = await fetch_gtex_gene_data(ingestor, normalized_entrez_id)
        if isinstance(gtex_data, dict):
            record["gtex_expression"] = gtex_data

    if include_expression and normalized_entrez_id >= 0:
        expression_data = await fetch_expression_ortholog_data(
            ingestor,
            normalized_entrez_id,
        )
        if isinstance(expression_data, list):
            record["ortholog_expression"] = expression_data

    if include_pharos and normalized_entrez_id >= 0:
        pharos_data = await fetch_pharos_targets(ingestor, normalized_entrez_id)
        if isinstance(pharos_data, list):
            record["pharos_targets"] = pharos_data

    return record


async def fetch_gene_info(
    ingestor: BaseIngestor,
    taxon_id: int,
    symbol: str,
) -> RawRecord | None:
    endpoint = f"gene/taxonId/{taxon_id}/symbol/{_encode_path_segment(symbol)}"
    data = await _fetch_json_payload(
        ingestor,
        endpoint,
        context=f"gene info for {symbol}",
    )
    return _coerce_record_payload(ingestor, data)


async def fetch_omim_data(
    ingestor: BaseIngestor,
    gene_symbol: str,
) -> list[RawRecord]:
    endpoint = f"omim/gene/symbol/{_encode_path_segment(gene_symbol)}"
    data = await _fetch_json_payload(
        ingestor,
        endpoint,
        context=f"OMIM data for {gene_symbol}",
    )
    return _coerce_record_list_payload(ingestor, data)


async def fetch_dbnsfp_data(
    ingestor: BaseIngestor,
    gene_symbol: str,
) -> list[RawRecord]:
    endpoint = f"dbnsfp/variant/{_encode_path_segment(gene_symbol)}"
    data = await _fetch_json_payload(
        ingestor,
        endpoint,
        context=f"dbNSFP data for {gene_symbol}",
        failure_log_level=logging.DEBUG,
    )
    return _coerce_record_list_payload(ingestor, data)


async def fetch_clinvar_data(
    ingestor: BaseIngestor,
    entrez_id: int | str,
) -> list[RawRecord]:
    endpoint = f"clinvar/gene/entrezId/{entrez_id}"
    data = await _fetch_json_payload(
        ingestor,
        endpoint,
        context=f"ClinVar data for entrez {entrez_id}",
    )
    return _coerce_record_list_payload(ingestor, data)


async def fetch_geno2mp_data(ingestor: BaseIngestor, entrez_id: int) -> list[RawRecord]:
    endpoint = f"geno2mp/gene/entrezId/{entrez_id}"
    data = await _fetch_json_payload(
        ingestor,
        endpoint,
        context=f"Geno2MP data for entrez {entrez_id}",
    )
    return _coerce_record_list_payload(ingestor, data)


async def fetch_geno2mp_variant_data(
    ingestor: BaseIngestor,
    variant: str,
) -> JSONValue | None:
    endpoint = f"geno2mp/variant/{_encode_path_segment(variant)}"
    return await _fetch_json_payload(
        ingestor,
        endpoint,
        context=f"Geno2MP variant data for {variant}",
    )


async def fetch_gnomad_gene_data(
    ingestor: BaseIngestor,
    entrez_id: int,
) -> RawRecord | None:
    endpoint = f"gnomad/gene/entrezId/{entrez_id}"
    data = await _fetch_json_payload(
        ingestor,
        endpoint,
        context=f"gnomAD gene data for entrez {entrez_id}",
    )
    return _coerce_record_payload(ingestor, data)


async def fetch_gnomad_variant_data(
    ingestor: BaseIngestor,
    variant: str,
) -> JSONValue | None:
    endpoint = f"gnomad/variant/{_encode_path_segment(variant)}"
    return await _fetch_json_payload(
        ingestor,
        endpoint,
        context=f"gnomAD variant data for {variant}",
    )


async def fetch_dgv_gene_data(
    ingestor: BaseIngestor,
    entrez_id: int,
) -> list[RawRecord]:
    endpoint = f"dgv/gene/entrezId/{entrez_id}"
    data = await _fetch_json_payload(
        ingestor,
        endpoint,
        context=f"DGV data for entrez {entrez_id}",
    )
    return _coerce_record_list_payload(ingestor, data)


async def fetch_dgv_variant_data(
    ingestor: BaseIngestor,
    variant: str,
) -> list[RawRecord]:
    endpoint = f"dgv/variant/{_encode_path_segment(variant)}"
    data = await _fetch_json_payload(
        ingestor,
        endpoint,
        context=f"DGV variant data for {variant}",
    )
    return _coerce_record_list_payload(ingestor, data)


async def fetch_decipher_variant_data(
    ingestor: BaseIngestor,
    variant: str,
) -> list[RawRecord]:
    endpoint = f"decipher/variant/{_encode_path_segment(variant)}"
    data = await _fetch_json_payload(
        ingestor,
        endpoint,
        context=f"DECIPHER data for {variant}",
    )
    return _coerce_record_list_payload(ingestor, data)


async def fetch_diopt_ortholog_data(
    ingestor: BaseIngestor,
    entrez_id: int,
) -> list[RawRecord]:
    endpoint = f"diopt/ortholog/gene/entrezId/{entrez_id}"
    data = await _fetch_json_payload(
        ingestor,
        endpoint,
        context=f"DIOPT ortholog data for entrez {entrez_id}",
    )
    return _coerce_record_list_payload(ingestor, data)


async def fetch_diopt_alignment_data(
    ingestor: BaseIngestor,
    entrez_id: int,
) -> RawRecord | None:
    endpoint = f"diopt/alignment/gene/entrezId/{entrez_id}"
    data = await _fetch_json_payload(
        ingestor,
        endpoint,
        context=f"DIOPT alignment data for entrez {entrez_id}",
    )
    return _coerce_record_payload(ingestor, data)


async def fetch_gtex_gene_data(
    ingestor: BaseIngestor,
    entrez_id: int,
) -> RawRecord | None:
    endpoint = f"gtex/gene/entrezId/{entrez_id}"
    data = await _fetch_json_payload(
        ingestor,
        endpoint,
        context=f"GTEx data for entrez {entrez_id}",
    )
    return _coerce_record_payload(ingestor, data)


async def fetch_expression_ortholog_data(
    ingestor: BaseIngestor,
    entrez_id: int,
) -> list[RawRecord]:
    endpoint = f"expression/orthologs/gene/entrezId/{entrez_id}"
    data = await _fetch_json_payload(
        ingestor,
        endpoint,
        context=f"ortholog expression data for entrez {entrez_id}",
    )
    return _coerce_record_list_payload(ingestor, data)


async def fetch_pharos_targets(
    ingestor: BaseIngestor,
    entrez_id: int,
) -> list[RawRecord]:
    endpoint = f"pharos/targets/gene/entrezId/{entrez_id}"
    data = await _fetch_json_payload(
        ingestor,
        endpoint,
        context=f"Pharos data for entrez {entrez_id}",
    )
    return _coerce_record_list_payload(ingestor, data)


async def fetch_mutalyzer_data(
    ingestor: BaseIngestor,
    variant_hgvs: str,
) -> RawRecord | None:
    endpoint = f"mutalyzer/hgvs/{_encode_path_segment(variant_hgvs)}"
    data = await _fetch_json_payload(
        ingestor,
        endpoint,
        context=f"Mutalyzer data for {variant_hgvs}",
    )
    return _coerce_record_payload(ingestor, data)


async def fetch_transvar_data(
    ingestor: BaseIngestor,
    protein_variant: str,
) -> RawRecord | None:
    endpoint = f"transvar/protein/{_encode_path_segment(protein_variant)}"
    data = await _fetch_json_payload(
        ingestor,
        endpoint,
        context=f"TransVar data for {protein_variant}",
    )
    return _coerce_record_payload(ingestor, data)


def _coerce_int(value: JSONValue | None, default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return default


def _encode_path_segment(value: str) -> str:
    return quote(value.strip(), safe="")


async def _fetch_json_payload(
    ingestor: BaseIngestor,
    endpoint: str,
    *,
    context: str,
    failure_log_level: int = logging.WARNING,
) -> JSONValue | None:
    try:
        response = await ingestor._make_request("GET", endpoint)  # noqa: SLF001
        return ingestor._coerce_json_value(response.json())  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        logger.log(failure_log_level, "Failed to fetch %s: %s", context, exc)
        return None


def _coerce_record_list_payload(
    ingestor: BaseIngestor,
    payload: JSONValue | None,
) -> list[RawRecord]:
    if isinstance(payload, list):
        return [
            ingestor._ensure_raw_record(entry)  # noqa: SLF001
            for entry in payload
            if isinstance(entry, dict)
        ]
    if isinstance(payload, dict):
        return [ingestor._ensure_raw_record(payload)]  # noqa: SLF001
    return []


def _coerce_record_payload(
    ingestor: BaseIngestor,
    payload: JSONValue | None,
) -> RawRecord | None:
    if isinstance(payload, dict):
        return ingestor._ensure_raw_record(payload)  # noqa: SLF001
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return ingestor._ensure_raw_record(payload[0])  # noqa: SLF001
    return None


MARRVEL_FETCH_DISPATCH: dict[str, Callable[..., Awaitable[object]]] = {
    "fetch_clinvar_data": fetch_clinvar_data,
    "fetch_dbnsfp_data": fetch_dbnsfp_data,
    "fetch_decipher_variant_data": fetch_decipher_variant_data,
    "fetch_diopt_alignment_data": fetch_diopt_alignment_data,
    "fetch_diopt_ortholog_data": fetch_diopt_ortholog_data,
    "fetch_dgv_gene_data": fetch_dgv_gene_data,
    "fetch_dgv_variant_data": fetch_dgv_variant_data,
    "fetch_expression_ortholog_data": fetch_expression_ortholog_data,
    "fetch_gene_info": fetch_gene_info,
    "fetch_geno2mp_data": fetch_geno2mp_data,
    "fetch_geno2mp_variant_data": fetch_geno2mp_variant_data,
    "fetch_gnomad_gene_data": fetch_gnomad_gene_data,
    "fetch_gnomad_variant_data": fetch_gnomad_variant_data,
    "fetch_gtex_gene_data": fetch_gtex_gene_data,
    "fetch_mutalyzer_data": fetch_mutalyzer_data,
    "fetch_omim_data": fetch_omim_data,
    "fetch_pharos_targets": fetch_pharos_targets,
    "fetch_transvar_data": fetch_transvar_data,
}
