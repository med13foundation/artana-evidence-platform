"""Structured source alias extraction contracts and helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from src.domain.value_objects.entity_resolution import normalize_entity_alias_labels

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject


@dataclass(frozen=True)
class StructuredEntityAliasCandidate:
    """Alias persistence candidate extracted from one structured source record."""

    source_type: str
    entity_type: str
    display_label: str
    identifiers: dict[str, str] = field(default_factory=dict)
    aliases: tuple[str, ...] = ()
    metadata: JSONObject = field(default_factory=dict)


@dataclass(frozen=True)
class StructuredSourceAliasWriteResult:
    """Backend-derived alias persistence metrics for structured sources."""

    alias_candidates_count: int = 0
    aliases_persisted: int = 0
    aliases_skipped: int = 0
    alias_entities_touched: int = 0
    errors: tuple[str, ...] = ()


class StructuredSourceAliasWriter(Protocol):
    """Port for persisting extracted source aliases to the kernel graph."""

    def ensure_aliases(
        self,
        *,
        research_space_id: str,
        candidates: tuple[StructuredEntityAliasCandidate, ...],
    ) -> StructuredSourceAliasWriteResult:
        """Create/resolve entities and attach aliases idempotently."""


def count_alias_candidates(
    candidates: Iterable[StructuredEntityAliasCandidate],
) -> int:
    """Count normalized alias labels across extracted candidates."""
    return sum(len(candidate.aliases) for candidate in candidates)


def build_uniprot_alias_candidates(
    record: Mapping[str, object],
) -> tuple[StructuredEntityAliasCandidate, ...]:
    """Extract protein and gene alias candidates from one UniProt record."""
    uniprot_id = _first_text(record, ("uniprot_id", "primaryAccession", "accession"))
    entry_name = _first_text(record, ("entry_name", "uniProtkbId"))
    protein_name = _first_text(record, ("protein_name",))
    if protein_name is None:
        protein_name = _first_protein_description_name(record.get("proteinDescription"))

    description_names = _extract_protein_description_aliases(
        record.get("proteinDescription"),
    )
    alternative_names = _dedupe_labels(
        [
            *_text_values(record.get("alternative_names")),
            *_text_values(record.get("alternativeNames")),
            *_text_values(record.get("protein_aliases")),
            *description_names,
        ],
    )
    primary_gene, gene_aliases_from_raw = _extract_uniprot_gene_names(
        record.get("genes"),
    )
    gene_name = _first_text(record, ("gene_name", "gene_symbol")) or primary_gene
    gene_aliases = _dedupe_labels(
        [
            *_text_values(record.get("gene_aliases")),
            *_text_values(record.get("gene_synonyms")),
            *gene_aliases_from_raw,
        ],
    )

    candidates: list[StructuredEntityAliasCandidate] = []
    protein_label = protein_name or uniprot_id or entry_name
    if protein_label:
        protein_aliases = _dedupe_labels(
            [
                protein_label,
                uniprot_id,
                entry_name,
                *alternative_names,
                gene_name,
                *gene_aliases,
            ],
        )
        identifiers = {"uniprot_id": uniprot_id} if uniprot_id else {}
        candidates.append(
            StructuredEntityAliasCandidate(
                source_type="uniprot",
                entity_type="PROTEIN",
                display_label=protein_label,
                identifiers=identifiers,
                aliases=protein_aliases,
            ),
        )

    if gene_name:
        gene_aliases_for_entity = _dedupe_labels([gene_name, *gene_aliases])
        candidates.append(
            StructuredEntityAliasCandidate(
                source_type="uniprot",
                entity_type="GENE",
                display_label=gene_name,
                identifiers={"gene_symbol": gene_name},
                aliases=gene_aliases_for_entity,
            ),
        )

    return tuple(candidates)


def build_drugbank_alias_candidates(
    record: Mapping[str, object],
) -> tuple[StructuredEntityAliasCandidate, ...]:
    """Extract drug alias candidates from one DrugBank record."""
    drugbank_id = _first_text(record, ("drugbank_id", "id", "accession"))
    name = _first_text(record, ("name", "drug_name", "generic_name"))
    display_label = name or drugbank_id
    if not display_label:
        return ()

    aliases = _dedupe_labels(
        [
            display_label,
            drugbank_id,
            *_text_values(record.get("generic_name")),
            *_text_values(record.get("synonyms")),
            *_text_values(record.get("aliases")),
            *_text_values(record.get("brand_names")),
            *_text_values(record.get("product_names")),
            *_text_values(record.get("products")),
        ],
    )
    identifiers = {"drugbank_id": drugbank_id} if drugbank_id else {}
    return (
        StructuredEntityAliasCandidate(
            source_type="drugbank",
            entity_type="DRUG",
            display_label=display_label,
            identifiers=identifiers,
            aliases=aliases,
        ),
    )


def build_hgnc_alias_candidates(
    record: Mapping[str, object],
) -> tuple[StructuredEntityAliasCandidate, ...]:
    """Extract gene alias candidates from one HGNC-style record."""
    hgnc_id = _first_text(record, ("hgnc_id", "hgncId", "hgnc"))
    symbol = _first_text(record, ("symbol", "approved_symbol", "gene_symbol"))
    display_label = symbol or hgnc_id
    if not display_label:
        return ()

    aliases = _dedupe_labels(
        [
            display_label,
            *_text_values(record.get("name")),
            *_text_values(record.get("approved_name")),
            *_text_values(record.get("alias_symbol")),
            *_text_values(record.get("alias_symbols")),
            *_text_values(record.get("prev_symbol")),
            *_text_values(record.get("previous_symbols")),
            *_text_values(record.get("alias_name")),
            *_text_values(record.get("alias_names")),
            *_text_values(record.get("prev_name")),
            *_text_values(record.get("previous_names")),
        ],
    )
    identifiers: dict[str, str] = {}
    if hgnc_id:
        identifiers["hgnc_id"] = hgnc_id
    if symbol:
        identifiers["gene_symbol"] = symbol

    return (
        StructuredEntityAliasCandidate(
            source_type="hgnc",
            entity_type="GENE",
            display_label=display_label,
            identifiers=identifiers,
            aliases=aliases,
        ),
    )


def _first_text(record: Mapping[str, object], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        values = _text_values(record.get(key))
        if values:
            return values[0]
    return None


def _text_values(value: object) -> tuple[str, ...]:
    values: list[str] = []
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            values.append(stripped)
    elif isinstance(value, int | float) and not isinstance(value, bool):
        values.append(str(value))
    elif isinstance(value, Mapping):
        for key in (
            "value",
            "name",
            "label",
            "symbol",
            "synonym",
            "alias",
            "drug_name",
            "generic_name",
            "fullName",
            "shortName",
            "shortNames",
            "geneName",
        ):
            values.extend(_text_values(value.get(key)))
    elif isinstance(value, list | tuple):
        for item in value:
            values.extend(_text_values(item))
    return tuple(values)


def _dedupe_labels(values: Iterable[str | None]) -> tuple[str, ...]:
    return tuple(normalize_entity_alias_labels(v for v in values if isinstance(v, str)))


def _first_protein_description_name(value: object) -> str | None:
    names = _extract_name_block_values(value, preferred_keys=("recommendedName",))
    return names[0] if names else None


def _extract_protein_description_aliases(value: object) -> tuple[str, ...]:
    return _dedupe_labels(
        _extract_name_block_values(
            value,
            preferred_keys=(
                "recommendedName",
                "alternativeNames",
                "submissionNames",
            ),
        ),
    )


def _extract_name_block_values(
    value: object,
    *,
    preferred_keys: tuple[str, ...],
) -> tuple[str, ...]:
    if not isinstance(value, Mapping):
        return ()
    names: list[str] = []
    for key in preferred_keys:
        nested = value.get(key)
        if isinstance(nested, list | tuple):
            for item in nested:
                names.extend(_text_values(item))
        else:
            names.extend(_text_values(nested))
    return tuple(names)


def _extract_uniprot_gene_names(value: object) -> tuple[str | None, tuple[str, ...]]:
    if not isinstance(value, list | tuple):
        return None, ()

    primary: str | None = None
    aliases: list[str] = []
    fallback_primary: str | None = None
    for item in value:
        if not isinstance(item, Mapping):
            continue
        gene_values = _text_values(item.get("geneName"))
        if not gene_values:
            continue
        gene_name = gene_values[0]
        if fallback_primary is None:
            fallback_primary = gene_name
        type_value = item.get("type")
        if isinstance(type_value, str) and type_value.casefold() == "primary":
            primary = gene_name
        else:
            aliases.append(gene_name)

    if primary is None:
        primary = fallback_primary
        aliases = [alias for alias in aliases if alias != primary]
    return primary, _dedupe_labels(aliases)


__all__ = [
    "StructuredEntityAliasCandidate",
    "StructuredSourceAliasWriteResult",
    "StructuredSourceAliasWriter",
    "build_drugbank_alias_candidates",
    "build_hgnc_alias_candidates",
    "build_uniprot_alias_candidates",
    "count_alias_candidates",
]
