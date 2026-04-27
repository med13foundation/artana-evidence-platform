"""Source-owned policy helpers for captured source records."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from artana_evidence_api.types.common import (
    JSONObject,
    JSONValue,
    json_array_or_empty,
    json_value,
)

SourceHandoffTargetKind = Literal["source_document"]

_CLINVAR_ACCESSION_PATTERN = re.compile(
    r"^(?:VCV|RCV|SCV)\d+(?:\.\d+)?$",
    re.IGNORECASE,
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


@dataclass(frozen=True, slots=True)
class SourceRecordPolicy:
    """Source-specific record policy used after direct source-search capture."""

    source_key: str
    source_family: str
    provider_id_keys: tuple[str, ...]
    normalize_record: Callable[[JSONObject], JSONObject]
    recommends_variant_aware: Callable[[JSONObject], bool]
    handoff_target_kind: SourceHandoffTargetKind = "source_document"
    direct_search_supported: bool = True
    request_schema_ref: str | None = None
    result_schema_ref: str | None = None

    def provider_external_id(self, record: JSONObject) -> str | None:
        """Return the first stable provider identifier for one source record."""

        for key in self.provider_id_keys:
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None


def source_record_policy(source_key: str) -> SourceRecordPolicy | None:
    """Return the source record policy for one source key."""

    return _SOURCE_RECORD_POLICIES.get(source_key)


def source_record_policies() -> tuple[SourceRecordPolicy, ...]:
    """Return source record policies in stable registry order."""

    return tuple(_SOURCE_RECORD_POLICIES.values())


def _normalize_clinical_trials_record(record: JSONObject) -> JSONObject:
    return _compact_json_object(
        {
            "nct_id": _string_field(record, "nct_id"),
            "title": _string_field(record, "brief_title", "official_title"),
            "status": _string_field(record, "overall_status", "status"),
            "phase": _string_list_field(record, "phases"),
            "conditions": _string_list_field(record, "conditions"),
            "interventions": _intervention_names(record.get("interventions")),
            "study_type": _string_field(record, "study_type"),
        },
    )


def _normalize_clinvar_record(record: JSONObject) -> JSONObject:
    return _compact_json_object(
        {
            "accession": _string_field(record, "accession"),
            "variation_id": _json_value_field(record, "variation_id"),
            "gene_symbol": _string_field(record, "gene_symbol"),
            "title": _string_field(record, "title"),
            "clinical_significance": _json_value_field(
                record,
                "clinical_significance",
            ),
            "conditions": _json_value_field(record, "conditions"),
            "hgvs": _string_field(record, "hgvs", "hgvs_notation"),
        },
    )


def _normalize_pubmed_record(record: JSONObject) -> JSONObject:
    return _compact_json_object(
        {
            "pmid": _string_field(record, "pmid", "pubmed_id", "uid"),
            "title": _string_field(record, "title"),
            "abstract": _string_field(record, "abstract"),
            "journal": _string_field(record, "journal", "source"),
            "publication_year": _string_field(
                record,
                "publication_year",
                "year",
            ),
        },
    )


def _normalize_uniprot_record(record: JSONObject) -> JSONObject:
    return _compact_json_object(
        {
            "uniprot_id": _string_field(
                record,
                "uniprot_id",
                "primary_accession",
                "accession",
            ),
            "gene_symbol": _string_field(record, "gene_name", "gene_symbol"),
            "protein_name": _string_field(record, "protein_name", "name"),
            "organism": _string_field(record, "organism"),
            "function": _string_field(record, "function", "description"),
            "sequence_length": _json_value_field(record, "sequence_length"),
        },
    )


def _normalize_alphafold_record(record: JSONObject) -> JSONObject:
    return _compact_json_object(
        {
            "uniprot_id": _string_field(
                record,
                "uniprot_id",
                "primary_accession",
                "accession",
            ),
            "protein_name": _string_field(record, "protein_name", "name"),
            "gene_symbol": _string_field(record, "gene_name", "gene_symbol"),
            "organism": _string_field(record, "organism"),
            "confidence": _json_value_field(
                record,
                "predicted_structure_confidence",
                "confidence_avg",
            ),
            "model_url": _string_field(record, "model_url", "cifUrl"),
            "pdb_url": _string_field(record, "pdb_url", "pdbUrl"),
            "domains": _json_value_field(record, "domains"),
        },
    )


def _normalize_drugbank_record(record: JSONObject) -> JSONObject:
    return _compact_json_object(
        {
            "drugbank_id": _string_field(
                record,
                "drugbank_id",
                "drug_id",
                "drugbank-id",
            ),
            "drug_name": _string_field(record, "drug_name", "name"),
            "target_name": _string_field(record, "target_name"),
            "targets": _json_value_field(record, "targets", "target_names"),
            "mechanism": _string_field(
                record,
                "mechanism_of_action",
                "mechanism",
            ),
            "categories": _json_value_field(record, "categories"),
        },
    )


def _normalize_alliance_record(
    record: JSONObject,
    *,
    provider_id_keys: tuple[str, ...],
) -> JSONObject:
    return _compact_json_object(
        {
            "provider_id": _provider_external_id(
                record=record,
                provider_id_keys=provider_id_keys,
            ),
            "gene_symbol": _string_field(record, "gene_symbol", "symbol"),
            "gene_name": _string_field(record, "gene_name", "name"),
            "species": _string_field(record, "species"),
            "phenotypes": _json_value_field(record, "phenotype_statements"),
            "disease_associations": _json_value_field(
                record,
                "disease_associations",
            ),
            "expression_terms": _json_value_field(record, "expression_terms"),
        },
    )


def _normalize_marrvel_record(record: JSONObject) -> JSONObject:
    return _compact_json_object(
        {
            "marrvel_record_id": _string_field(record, "marrvel_record_id"),
            "panel_name": _string_field(record, "panel_name"),
            "panel_family": _string_field(record, "panel_family"),
            "gene_symbol": _string_field(record, "gene_symbol"),
            "resolved_gene_symbol": _string_field(
                record,
                "resolved_gene_symbol",
            ),
            "hgvs": _string_field(record, "hgvs", "hgvs_notation"),
            "query_mode": _string_field(record, "query_mode"),
            "query_value": _string_field(record, "query_value"),
        },
    )


def _marrvel_record_is_variant_panel(record: JSONObject) -> bool:
    if record.get("variant_aware_recommended") is True:
        return True
    panel_name = record.get("panel_name")
    if isinstance(panel_name, str) and panel_name.strip() in _MARRVEL_VARIANT_PANEL_KEYS:
        return True
    panel_family = record.get("panel_family")
    return isinstance(panel_family, str) and panel_family.strip() == "variant"


def _clinvar_record_has_variant_signal(record: JSONObject) -> bool:
    if record.get("variant_aware_recommended") is True:
        return True
    for key in (
        "hgvs",
        "hgvs_notation",
        "hgvs_c",
        "hgvs_p",
    ):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return True
    accession = record.get("accession")
    if isinstance(accession, str) and _CLINVAR_ACCESSION_PATTERN.fullmatch(
        accession.strip(),
    ):
        return True
    title = record.get("title")
    if isinstance(title, str):
        normalized_title = title.lower()
        return any(token in normalized_title for token in (":c.", ":p.", ":g.", ":m."))
    return False


def _never_variant_aware(record: JSONObject) -> bool:
    del record
    return False


def _compact_json_object(payload: dict[str, JSONValue | None]) -> JSONObject:
    return {
        key: value
        for key, value in payload.items()
        if not _is_empty_json_value(value)
    }


def _string_field(record: JSONObject, *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int | float) and not isinstance(value, bool):
            return str(value)
    return None


def _json_value_field(record: JSONObject, *keys: str) -> JSONValue | None:
    for key in keys:
        if key not in record:
            continue
        value = json_value(record[key])
        if _is_empty_json_value(value):
            continue
        return value
    return None


def _string_list_field(record: JSONObject, *keys: str) -> list[str]:
    for key in keys:
        values = [
            item.strip()
            for item in json_array_or_empty(record.get(key))
            if isinstance(item, str) and item.strip()
        ]
        if values:
            return values
    return []


def _intervention_names(value: object) -> list[str]:
    names: list[str] = []
    for item in json_array_or_empty(value):
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
            continue
        item_payload = (
            {key: json_value(raw_value) for key, raw_value in item.items()}
            if isinstance(item, dict)
            else {}
        )
        name = item_payload.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def _provider_external_id(
    *,
    record: JSONObject,
    provider_id_keys: tuple[str, ...],
) -> str | None:
    for key in provider_id_keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _is_empty_json_value(value: JSONValue | None) -> bool:
    if value is None:
        return True
    if value == "":
        return True
    return value in ({}, [])


_MARRVEL_POLICY = SourceRecordPolicy(
    source_key="marrvel",
    source_family="variant",
    provider_id_keys=("marrvel_record_id",),
    normalize_record=_normalize_marrvel_record,
    recommends_variant_aware=_marrvel_record_is_variant_panel,
    request_schema_ref="MarrvelSearchRequest",
    result_schema_ref="MarrvelSearchResponse",
)
_MGI_PROVIDER_ID_KEYS = ("mgi_id", "primary_id", "id")
_ZFIN_PROVIDER_ID_KEYS = ("zfin_id", "primary_id", "id")

_SOURCE_RECORD_POLICIES: dict[str, SourceRecordPolicy] = {
    "pubmed": SourceRecordPolicy(
        source_key="pubmed",
        source_family="literature",
        provider_id_keys=("pmid", "pubmed_id", "uid"),
        normalize_record=_normalize_pubmed_record,
        recommends_variant_aware=_never_variant_aware,
        request_schema_ref="PubMedSearchRequest",
        result_schema_ref="DiscoverySearchJob",
    ),
    "marrvel": _MARRVEL_POLICY,
    "clinvar": SourceRecordPolicy(
        source_key="clinvar",
        source_family="variant",
        provider_id_keys=("accession", "clinvar_id", "variation_id"),
        normalize_record=_normalize_clinvar_record,
        recommends_variant_aware=_clinvar_record_has_variant_signal,
        request_schema_ref="ClinVarSourceSearchRequest",
        result_schema_ref="ClinVarSourceSearchResponse",
    ),
    "clinical_trials": SourceRecordPolicy(
        source_key="clinical_trials",
        source_family="clinical",
        provider_id_keys=("nct_id",),
        normalize_record=_normalize_clinical_trials_record,
        recommends_variant_aware=_never_variant_aware,
        request_schema_ref="ClinicalTrialsSourceSearchRequest",
        result_schema_ref="ClinicalTrialsSourceSearchResponse",
    ),
    "uniprot": SourceRecordPolicy(
        source_key="uniprot",
        source_family="protein",
        provider_id_keys=("uniprot_id", "primary_accession", "accession"),
        normalize_record=_normalize_uniprot_record,
        recommends_variant_aware=_never_variant_aware,
        request_schema_ref="UniProtSourceSearchRequest",
        result_schema_ref="UniProtSourceSearchResponse",
    ),
    "alphafold": SourceRecordPolicy(
        source_key="alphafold",
        source_family="structure",
        provider_id_keys=("uniprot_id", "primary_accession", "accession"),
        normalize_record=_normalize_alphafold_record,
        recommends_variant_aware=_never_variant_aware,
        request_schema_ref="AlphaFoldSourceSearchRequest",
        result_schema_ref="AlphaFoldSourceSearchResponse",
    ),
    "drugbank": SourceRecordPolicy(
        source_key="drugbank",
        source_family="drug",
        provider_id_keys=("drugbank_id", "drug_id"),
        normalize_record=_normalize_drugbank_record,
        recommends_variant_aware=_never_variant_aware,
        request_schema_ref="DrugBankSourceSearchRequest",
        result_schema_ref="DrugBankSourceSearchResponse",
    ),
    "mgi": SourceRecordPolicy(
        source_key="mgi",
        source_family="model_organism",
        provider_id_keys=_MGI_PROVIDER_ID_KEYS,
        normalize_record=lambda record: _normalize_alliance_record(
            record,
            provider_id_keys=_MGI_PROVIDER_ID_KEYS,
        ),
        recommends_variant_aware=_never_variant_aware,
        request_schema_ref="MGISourceSearchRequest",
        result_schema_ref="MGISourceSearchResponse",
    ),
    "zfin": SourceRecordPolicy(
        source_key="zfin",
        source_family="model_organism",
        provider_id_keys=_ZFIN_PROVIDER_ID_KEYS,
        normalize_record=lambda record: _normalize_alliance_record(
            record,
            provider_id_keys=_ZFIN_PROVIDER_ID_KEYS,
        ),
        recommends_variant_aware=_never_variant_aware,
        request_schema_ref="ZFINSourceSearchRequest",
        result_schema_ref="ZFINSourceSearchResponse",
    ),
}

__all__ = [
    "SourceHandoffTargetKind",
    "SourceRecordPolicy",
    "source_record_policies",
    "source_record_policy",
]
