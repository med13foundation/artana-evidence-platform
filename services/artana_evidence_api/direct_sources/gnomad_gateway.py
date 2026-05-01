"""Service-local gnomAD structured-source gateway."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://gnomad.broadinstitute.org/api"
_DEFAULT_TIMEOUT_SECONDS = 30.0
_USER_AGENT = "artana-evidence-platform/gnomad-gateway"

_GENE_CONSTRAINT_QUERY = """
query GnomADGeneConstraint($geneSymbol: String!, $referenceGenome: ReferenceGenomeId!) {
  gene(gene_symbol: $geneSymbol, reference_genome: $referenceGenome) {
    reference_genome
    gene_id
    symbol
    name
    chrom
    start
    stop
    gnomad_constraint {
      exp_lof
      exp_mis
      exp_syn
      obs_lof
      obs_mis
      obs_syn
      oe_lof
      oe_lof_lower
      oe_lof_upper
      oe_lof_percentile
      oe_mis
      oe_mis_lower
      oe_mis_upper
      oe_syn
      oe_syn_lower
      oe_syn_upper
      lof_z
      mis_z
      syn_z
      pli
      pLI
      flags
    }
  }
}
"""

_VARIANT_FREQUENCY_QUERY = """
query GnomADVariantFrequency($variantId: String!, $dataset: DatasetId!) {
  variant(variantId: $variantId, dataset: $dataset) {
    variant_id
    variantId
    reference_genome
    chrom
    pos
    ref
    alt
    rsids
    rsid
    exome {
      ac
      an
      af
      homozygote_count
      hemizygote_count
      filters
      populations {
        id
        ac
        an
        homozygote_count
        hemizygote_count
      }
    }
    genome {
      ac
      an
      af
      homozygote_count
      hemizygote_count
      filters
      populations {
        id
        ac
        an
        homozygote_count
        hemizygote_count
      }
    }
    joint {
      ac
      an
      homozygote_count
      hemizygote_count
      filters
      populations {
        id
        ac
        an
        homozygote_count
        hemizygote_count
      }
    }
    transcript_consequences {
      gene_id
      gene_symbol
      transcript_id
      major_consequence
      consequence_terms
      hgvsc
      hgvsp
      lof
      lof_filter
      lof_flags
      canonical
    }
  }
}
"""


@dataclass(frozen=True)
class GnomADGatewayFetchResult:
    """Result of a gnomAD fetch operation."""

    records: list[dict[str, object]] = field(default_factory=list)
    fetched_records: int = 0
    checkpoint_after: dict[str, object] | None = None
    checkpoint_kind: str = "none"


class GnomADGatewayError(RuntimeError):
    """Raised when gnomAD returns an unusable response."""


class GnomADSourceGateway:
    """Fetch and normalize direct gnomAD gene constraint or variant frequency data."""

    def __init__(
        self,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def fetch_records(
        self,
        *,
        gene_symbol: str | None = None,
        variant_id: str | None = None,
        reference_genome: str = "GRCh38",
        dataset: str = "gnomad_r4",
        max_results: int = 20,
    ) -> GnomADGatewayFetchResult:
        """Fetch one bounded gnomAD lookup result."""

        if variant_id is not None and variant_id.strip():
            records = self._fetch_variant_records(
                variant_id=variant_id.strip(),
                dataset=dataset,
            )
        elif gene_symbol is not None and gene_symbol.strip():
            records = self._fetch_gene_records(
                gene_symbol=gene_symbol.strip().upper(),
                reference_genome=reference_genome,
            )
        else:
            return GnomADGatewayFetchResult()

        bounded_records = records[: max(max_results, 0)]
        return GnomADGatewayFetchResult(
            records=bounded_records,
            fetched_records=len(bounded_records),
        )

    def _fetch_gene_records(
        self,
        *,
        gene_symbol: str,
        reference_genome: str,
    ) -> list[dict[str, object]]:
        payload = self._post_graphql(
            query=_GENE_CONSTRAINT_QUERY,
            variables={
                "geneSymbol": gene_symbol,
                "referenceGenome": reference_genome,
            },
        )
        data = _dict_value(payload.get("data"))
        gene = _dict_value(data.get("gene")) if data is not None else None
        if gene is None:
            return []
        return [
            _normalize_gene_record(
                gene=gene,
                fallback_gene_symbol=gene_symbol,
                reference_genome=reference_genome,
            ),
        ]

    def _fetch_variant_records(
        self,
        *,
        variant_id: str,
        dataset: str,
    ) -> list[dict[str, object]]:
        payload = self._post_graphql(
            query=_VARIANT_FREQUENCY_QUERY,
            variables={"variantId": variant_id, "dataset": dataset},
        )
        data = _dict_value(payload.get("data"))
        variant = _dict_value(data.get("variant")) if data is not None else None
        if variant is None:
            return []
        return [_normalize_variant_record(variant=variant, dataset=dataset)]

    def _post_graphql(
        self,
        *,
        query: str,
        variables: Mapping[str, object],
    ) -> dict[str, object]:
        try:
            with httpx.Client(
                headers={"User-Agent": _USER_AGENT},
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.post(
                    self._base_url,
                    json={"query": query, "variables": dict(variables)},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"gnomAD GraphQL request failed: {exc}"
            raise GnomADGatewayError(msg) from exc

        payload: object = response.json()
        if not isinstance(payload, dict):
            msg = "gnomAD GraphQL response was not a JSON object"
            raise GnomADGatewayError(msg)
        normalized_payload = {str(key): value for key, value in payload.items()}
        errors = _error_messages(normalized_payload)
        if errors and not _only_not_found_errors(errors):
            msg = "gnomAD GraphQL response returned errors: " + "; ".join(errors)
            raise GnomADGatewayError(msg)
        if errors:
            logger.info("gnomAD GraphQL lookup returned no record: %s", "; ".join(errors))
        return normalized_payload


def _normalize_gene_record(
    *,
    gene: Mapping[str, object],
    fallback_gene_symbol: str,
    reference_genome: str,
) -> dict[str, object]:
    constraint = _dict_value(gene.get("gnomad_constraint")) or {}
    gene_symbol = _first_string(gene, ("symbol",)) or fallback_gene_symbol
    gene_id = _first_string(gene, ("gene_id",))
    return {
        "source": "gnomad",
        "record_type": "gene_constraint",
        "gene_symbol": gene_symbol,
        "gene_id": gene_id,
        "name": _first_string(gene, ("name",)) or gene_symbol,
        "reference_genome": _first_string(gene, ("reference_genome",))
        or reference_genome,
        "chrom": _first_string(gene, ("chrom",)) or "",
        "start": _first_int(gene, ("start",)),
        "stop": _first_int(gene, ("stop",)),
        "constraint": constraint,
        "pLI": _first_number(constraint, ("pLI", "pli")),
        "pli": _first_number(constraint, ("pli", "pLI")),
        "oe_lof": _first_number(constraint, ("oe_lof",)),
        "oe_lof_upper": _first_number(constraint, ("oe_lof_upper",)),
        "oe_mis": _first_number(constraint, ("oe_mis",)),
        "oe_mis_upper": _first_number(constraint, ("oe_mis_upper",)),
        "mis_z": _first_number(constraint, ("mis_z",)),
        "syn_z": _first_number(constraint, ("syn_z",)),
        "flags": _string_list(constraint.get("flags")),
    }


def _normalize_variant_record(
    *,
    variant: Mapping[str, object],
    dataset: str,
) -> dict[str, object]:
    transcript_consequences = _dict_list(variant.get("transcript_consequences"))
    preferred_consequence = _preferred_consequence(transcript_consequences)
    variant_id = (
        _first_string(variant, ("variant_id", "variantId"))
        or _variant_id_from_parts(variant)
    )
    return {
        "source": "gnomad",
        "record_type": "variant_frequency",
        "variant_id": variant_id,
        "variantId": variant_id,
        "dataset": dataset,
        "reference_genome": _first_string(variant, ("reference_genome",)) or "",
        "chrom": _first_string(variant, ("chrom",)) or "",
        "pos": _first_int(variant, ("pos",)),
        "ref": _first_string(variant, ("ref",)) or "",
        "alt": _first_string(variant, ("alt",)) or "",
        "rsids": _string_list(variant.get("rsids")),
        "rsid": _first_string(variant, ("rsid",)),
        "gene_symbol": _first_string(preferred_consequence, ("gene_symbol",)),
        "gene_id": _first_string(preferred_consequence, ("gene_id",)),
        "major_consequence": _first_string(
            preferred_consequence,
            ("major_consequence",),
        ),
        "hgvsc": _first_string(preferred_consequence, ("hgvsc",)),
        "hgvsp": _first_string(preferred_consequence, ("hgvsp",)),
        "transcript_consequences": transcript_consequences,
        "exome": _normalize_sequencing_data(variant.get("exome")),
        "genome": _normalize_sequencing_data(variant.get("genome")),
        "joint": _normalize_sequencing_data(variant.get("joint")),
        "flags": _string_list(variant.get("flags")),
    }


def _normalize_sequencing_data(value: object) -> dict[str, object] | None:
    data = _dict_value(value)
    if data is None:
        return None
    ac = _first_int(data, ("ac",))
    an = _first_int(data, ("an",))
    af = _first_number(data, ("af",))
    if af is None:
        af = _allele_frequency(ac=ac, an=an)
    return {
        "ac": ac,
        "an": an,
        "af": af,
        "homozygote_count": _first_int(data, ("homozygote_count", "ac_hom")),
        "hemizygote_count": _first_int(data, ("hemizygote_count", "ac_hemi")),
        "filters": _string_list(data.get("filters")),
        "populations": [
            _normalize_population(population)
            for population in _dict_list(data.get("populations"))
        ],
    }


def _normalize_population(population: Mapping[str, object]) -> dict[str, object]:
    ac = _first_int(population, ("ac",))
    an = _first_int(population, ("an",))
    return {
        "id": _first_string(population, ("id",)) or "",
        "ac": ac,
        "an": an,
        "af": _allele_frequency(ac=ac, an=an),
        "homozygote_count": _first_int(population, ("homozygote_count", "ac_hom")),
        "hemizygote_count": _first_int(population, ("hemizygote_count", "ac_hemi")),
    }


def _preferred_consequence(
    transcript_consequences: Sequence[Mapping[str, object]],
) -> Mapping[str, object]:
    for consequence in transcript_consequences:
        if _truthy(consequence.get("canonical")):
            return consequence
    return transcript_consequences[0] if transcript_consequences else {}


def _variant_id_from_parts(variant: Mapping[str, object]) -> str:
    chrom = _first_string(variant, ("chrom",))
    pos = _first_int(variant, ("pos",))
    ref = _first_string(variant, ("ref",))
    alt = _first_string(variant, ("alt",))
    if chrom and pos is not None and ref and alt:
        return f"{chrom}-{pos}-{ref}-{alt}"
    return ""


def _error_messages(payload: Mapping[str, object]) -> list[str]:
    raw_errors = payload.get("errors")
    if not isinstance(raw_errors, list | tuple):
        return []
    messages: list[str] = []
    for raw_error in raw_errors:
        error = _dict_value(raw_error)
        if error is None:
            continue
        message = _first_string(error, ("message",))
        if message:
            messages.append(message)
    return messages


def _only_not_found_errors(messages: Sequence[str]) -> bool:
    return bool(messages) and all(_is_record_not_found_error(message) for message in messages)


def _is_record_not_found_error(message: str) -> bool:
    cleaned = " ".join(message.casefold().rstrip(".").split())
    return cleaned in {"gene not found", "variant not found"}


def _allele_frequency(*, ac: int | None, an: int | None) -> float | None:
    if ac is None or an is None:
        return None
    return 0.0 if an <= 0 else ac / an


def _dict_value(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in value.items()}


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list | tuple):
        return []
    result: list[dict[str, object]] = []
    for item in value:
        parsed = _dict_value(item)
        if parsed is not None:
            result.append(parsed)
    return result


def _first_string(
    mapping: Mapping[str, object],
    keys: tuple[str, ...],
) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str):
            cleaned = " ".join(value.split())
            if cleaned:
                return cleaned
        elif isinstance(value, int | float) and not isinstance(value, bool):
            return str(value)
    return None


def _first_int(
    mapping: Mapping[str, object],
    keys: tuple[str, ...],
) -> int | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value)
    return None


def _first_number(
    mapping: Mapping[str, object],
    keys: tuple[str, ...],
) -> float | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [
        cleaned
        for item in value
        if isinstance(item, str)
        for cleaned in (" ".join(item.split()),)
        if cleaned
    ]


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"true", "1", "yes"}
    return False


__all__ = [
    "GnomADGatewayError",
    "GnomADGatewayFetchResult",
    "GnomADSourceGateway",
]
