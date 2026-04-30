"""Entity payload parsing and label inference for proposal promotion."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.document_extraction import resolve_graph_entity_label
from artana_evidence_api.types.common import JSONObject
from fastapi import HTTPException, status

if TYPE_CHECKING:
    from artana_evidence_api.graph_client import GraphTransportBundle

_NON_GENE_DISEASE_LABELS = frozenset({"ADHD", "ASD"})
_DISEASE_HINTS = (
    "disease",
    "disorder",
    "encephalopathy",
    "cardiomyopathy",
    "cancer",
    "tumor",
    "tumour",
    "autism",
)
_PHENOTYPE_HINTS = (
    "phenotype",
    "delay",
    "impairment",
    "defect",
    "disability",
    "dd/id",
    "developmental",
)
_DRUG_SUFFIXES = (
    "nib",
    "mab",
    "zumab",
    "ximab",
    "tinib",
    "rafenib",
    "ciclib",
    "lisib",
    "parin",
    "parib",
    "platin",
    "statin",
    "olol",
    "pril",
    "sartan",
    "floxacin",
    "mycin",
    "cillin",
    "azole",
    "vir",
    "navir",
    "previr",
)
_DISEASE_SUFFIXES = (
    "oma",
    "emia",
    "itis",
    "osis",
    "pathy",
    "trophy",
    "plasia",
    "ectomy",
)
_PATHWAY_HINTS = ("pathway", "signaling", "signalling", "cascade", "network")
_KNOWN_GENE_SYMBOLS = frozenset(
    {
        "TP53",
        "BRCA1",
        "BRCA2",
        "EGFR",
        "KRAS",
        "BRAF",
        "MYC",
        "RB1",
        "PTEN",
        "PIK3CA",
        "AKT1",
        "CDKN2A",
        "NF1",
        "NF2",
        "KDR",
        "VEGFR2",
        "PTPRB",
        "PLCG1",
        "FLT1",
        "FLT4",
        "PDGFRA",
        "KIT",
        "ALK",
        "ROS1",
        "MET",
        "RET",
        "FGFR1",
        "FGFR2",
        "FGFR3",
        "JAK2",
        "IDH1",
        "IDH2",
        "ARID1A",
        "ATM",
        "ERBB2",
        "HER2",
        "APC",
        "VHL",
        "WT1",
        "MDM2",
        "SNCA",
        "LRRK2",
        "PARK2",
        "GBA",
        "SOD1",
        "FUS",
        "TARDBP",
        "HTT",
        "CFTR",
        "SMN1",
        "DMD",
        "FMR1",
    },
)
_MAX_GENE_SYMBOL_LENGTH = 10


def _looks_like_gene_symbol(label: str) -> bool:
    normalized = label.strip()
    upper = normalized.upper()
    if upper in _KNOWN_GENE_SYMBOLS:
        return True
    return (
        len(normalized) <= _MAX_GENE_SYMBOL_LENGTH
        and normalized.isascii()
        and normalized == upper
        and any(character.isalpha() for character in normalized)
        and any(character.isdigit() for character in normalized)
    )


def _looks_like_gene_family(label: str) -> bool:
    parts = [part.strip() for part in re.split(r"[\\/]", label) if part.strip() != ""]
    return len(parts) > 1 and all(_looks_like_gene_symbol(part) for part in parts)


def infer_graph_entity_type_from_label(label: str) -> str:
    """Infer one graph entity type for unresolved promotion labels."""
    normalized_label = label.strip()
    lowered = normalized_label.casefold()
    entity_type = "PHENOTYPE"
    if (
        normalized_label.upper() in _NON_GENE_DISEASE_LABELS
        or any(token in lowered for token in _DISEASE_HINTS)
        or any(
            lowered.endswith(suffix) and len(normalized_label) > len(suffix) + 2
            for suffix in _DISEASE_SUFFIXES
        )
    ):
        entity_type = "DISEASE"
    elif any(token in lowered for token in _PHENOTYPE_HINTS):
        entity_type = "PHENOTYPE"
    elif "complex" in lowered:
        entity_type = "PROTEIN_COMPLEX"
    elif any(token in lowered for token in _PATHWAY_HINTS):
        entity_type = "SIGNALING_PATHWAY"
    elif any(lowered.endswith(suffix) for suffix in _DRUG_SUFFIXES):
        entity_type = "DRUG"
    elif "syndrome" in lowered:
        entity_type = "SYNDROME"
    elif _looks_like_gene_family(normalized_label) or _looks_like_gene_symbol(
        normalized_label,
    ):
        entity_type = "GENE"
    return entity_type


def optional_json_string(value: object) -> str | None:
    if isinstance(value, str) and value.strip() != "":
        return value.strip()
    return None


def resolve_entity_reference_value(
    *,
    payload: JSONObject,
    field_name: str,
    label_field_name: str,
    metadata: JSONObject,
    metadata_label_field_name: str,
) -> str:
    raw_value = optional_json_string(payload.get(field_name))
    if raw_value is not None:
        return raw_value

    payload_label = optional_json_string(payload.get(label_field_name))
    if payload_label is not None:
        return f"unresolved:{payload_label}"

    metadata_label = optional_json_string(metadata.get(metadata_label_field_name))
    if metadata_label is not None:
        return f"unresolved:{metadata_label}"

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Proposal payload is missing required '{field_name}' or "
            f"'{label_field_name}' for graph promotion"
        ),
    )


def entity_candidate_field_name(field_name: str) -> str:
    if field_name == "proposed_subject":
        return "proposed_subject_entity_candidate"
    if field_name == "proposed_object":
        return "proposed_object_entity_candidate"
    return "subject_entity_candidate"


def optional_payload_object(
    payload: JSONObject,
    *,
    field_name: str,
) -> JSONObject | None:
    raw_value = payload.get(field_name)
    if not isinstance(raw_value, dict):
        return None
    return {
        str(key): value
        for key, value in raw_value.items()
    }


def payload_entity_aliases(candidate_payload: JSONObject) -> list[str]:
    raw_aliases = candidate_payload.get("aliases")
    if not isinstance(raw_aliases, list):
        return []
    aliases: list[str] = []
    seen: set[str] = set()
    for item in raw_aliases:
        if not isinstance(item, str):
            continue
        trimmed = item.strip()
        if not trimmed:
            continue
        key = trimmed.casefold()
        if key in seen:
            continue
        seen.add(key)
        aliases.append(trimmed)
    return aliases


def payload_entity_metadata(candidate_payload: JSONObject) -> JSONObject:
    raw_metadata = candidate_payload.get("metadata")
    if not isinstance(raw_metadata, dict):
        return {}
    return {
        str(key): value
        for key, value in raw_metadata.items()
    }


def payload_entity_identifiers(candidate_payload: JSONObject) -> dict[str, str]:
    raw_identifiers = candidate_payload.get("identifiers")
    identifiers: dict[str, str] = {}
    if isinstance(raw_identifiers, dict):
        for key, value in raw_identifiers.items():
            if not isinstance(value, str) or not value.strip():
                continue
            identifiers[str(key)] = value.strip()
    raw_anchors = candidate_payload.get("anchors")
    if isinstance(raw_anchors, dict):
        for key in ("gene_symbol", "hgvs_notation", "hpo_term"):
            value = raw_anchors.get(key)
            if not isinstance(value, str) or not value.strip():
                continue
            identifiers.setdefault(key, value.strip())
    return identifiers


def payload_entity_display_label(candidate_payload: JSONObject) -> str:
    for key in ("display_label", "label"):
        value = candidate_payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Entity candidate payload is missing 'label' or 'display_label'",
    )


def candidate_resolution_labels(candidate_payload: JSONObject) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()

    def _add(value: object) -> None:
        if not isinstance(value, str):
            return
        trimmed = value.strip()
        if trimmed == "":
            return
        key = trimmed.casefold()
        if key in seen:
            return
        seen.add(key)
        labels.append(trimmed)

    for key in ("display_label", "label"):
        _add(candidate_payload.get(key))
    for alias in payload_entity_aliases(candidate_payload):
        _add(alias)
    for identifier_value in payload_entity_identifiers(candidate_payload).values():
        _add(identifier_value)
    anchors = candidate_payload.get("anchors")
    if isinstance(anchors, dict):
        for value in anchors.values():
            _add(value)
    return labels


def resolve_existing_entity_from_candidate_payload(
    *,
    space_id: UUID,
    candidate_payload: JSONObject,
    graph_api_gateway: GraphTransportBundle,
) -> JSONObject | None:
    for label in candidate_resolution_labels(candidate_payload):
        resolved = resolve_graph_entity_label(
            space_id=space_id,
            label=label,
            graph_api_gateway=graph_api_gateway,
        )
        if resolved is not None:
            return resolved
    return None


def field_name_from_label_field(label_field_name: str) -> str:
    if label_field_name == "proposed_subject_label":
        return "proposed_subject_label"
    if label_field_name == "proposed_object_label":
        return "proposed_object_label"
    return label_field_name


__all__ = [
    "candidate_resolution_labels",
    "entity_candidate_field_name",
    "field_name_from_label_field",
    "infer_graph_entity_type_from_label",
    "optional_json_string",
    "optional_payload_object",
    "payload_entity_aliases",
    "payload_entity_display_label",
    "payload_entity_identifiers",
    "payload_entity_metadata",
    "resolve_entity_reference_value",
    "resolve_existing_entity_from_candidate_payload",
]
