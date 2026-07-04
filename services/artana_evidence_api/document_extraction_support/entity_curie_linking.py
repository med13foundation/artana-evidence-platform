"""CURIE normalization and draft payload support for extracted entities."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from artana_evidence_api.types.common import JSONObject

CurieSource = Literal["none", "model", "verified_linker"]

_CURIE_RE = re.compile(r"^(?P<prefix>[A-Za-z][A-Za-z0-9_.-]{1,31}):(?P<local>[A-Za-z0-9][A-Za-z0-9_.:-]{0,127})$")
_GENE_TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9-]{1,11}$")
_CURIE_PREFIXES: dict[str, tuple[str, str, str]] = {
    "CHEBI": ("CHEBI", "chebi_id", "DRUG"),
    "DRUGBANK": ("DRUGBANK", "drugbank_id", "DRUG"),
    "GO": ("GO", "go_id", "BIOLOGICAL_PROCESS"),
    "HGNC": ("HGNC", "hgnc_id", "GENE"),
    "HP": ("HP", "hpo_id", "PHENOTYPE"),
    "HPO": ("HP", "hpo_id", "PHENOTYPE"),
    "MESH": ("MESH", "mesh_id", "BIOMEDICAL_CONCEPT"),
    "MONDO": ("MONDO", "mondo_id", "DISEASE"),
    "NCBIGENE": ("NCBIGene", "ncbigene_id", "GENE"),
    "OMIM": ("OMIM", "omim_id", "DISEASE"),
    "UMLS": ("UMLS", "umls_id", "BIOMEDICAL_CONCEPT"),
}


@dataclass(frozen=True, slots=True)
class EntityCurieLink:
    """Validated entity identity link or an explicit abstention."""

    status: str
    curie: str | None = None
    namespace: str | None = None
    identifier_key: str | None = None
    entity_type: str | None = None
    source: CurieSource = "none"
    reason: str | None = None

    @property
    def identifiers(self) -> dict[str, str]:
        """Return graph entity identifier payload for linked endpoints."""

        if (
            self.curie is None
            or self.identifier_key is None
            or self.source != "verified_linker"
        ):
            return {}
        return {self.identifier_key: self.curie}

    def to_metadata(self) -> JSONObject:
        """Return JSON-safe link metadata."""

        payload: JSONObject = {"status": self.status}
        if self.curie is not None:
            payload["curie"] = self.curie
        if self.namespace is not None:
            payload["namespace"] = self.namespace
        if self.entity_type is not None:
            payload["entity_type"] = self.entity_type
        payload["source"] = self.source
        payload["trusted_identifier"] = (
            self.status == "linked" and self.source == "verified_linker"
        )
        if self.reason is not None:
            payload["reason"] = self.reason
        return payload


def normalize_entity_curie(
    raw_curie: str | None,
    *,
    label: str,
    source: CurieSource = "model",
) -> EntityCurieLink:
    """Normalize a model-supplied CURIE or return a typed abstention."""

    if raw_curie is None or raw_curie.strip() == "":
        return EntityCurieLink(
            status="abstained",
            source="none",
            reason="missing_curie",
        )

    match = _CURIE_RE.match(raw_curie.strip())
    if match is None:
        return EntityCurieLink(
            status="abstained",
            source=source,
            reason="invalid_curie",
        )

    prefix_key = match.group("prefix").upper()
    prefix_config = _CURIE_PREFIXES.get(prefix_key)
    if prefix_config is None:
        return EntityCurieLink(
            status="abstained",
            source=source,
            reason="unsupported_curie_prefix",
        )

    namespace, identifier_key, entity_type = prefix_config
    normalized = f"{namespace}:{match.group('local')}"
    if _label_conflicts_with_entity_type(label=label, entity_type=entity_type):
        return EntityCurieLink(
            status="abstained",
            source=source,
            reason="curie_label_type_mismatch",
        )
    return EntityCurieLink(
        status="linked",
        curie=normalized,
        namespace=namespace,
        identifier_key=identifier_key,
        entity_type=entity_type,
        source=source,
    )


def entity_candidate_payload_from_curie(
    *,
    label: str,
    link: EntityCurieLink,
    evidence_excerpt: str,
    evidence_locator: str,
) -> JSONObject | None:
    """Build a graph-promotion entity candidate payload from a linked CURIE."""

    if (
        link.status != "linked"
        or link.curie is None
        or link.entity_type is None
        or link.source != "verified_linker"
    ):
        return None
    normalized_label = label.strip()
    return {
        "entity_type": link.entity_type,
        "label": normalized_label,
        "display_label": normalized_label,
        "aliases": [normalized_label],
        "anchors": {"curie": link.curie},
        "metadata": {"curie_namespace": link.namespace or ""},
        "identifiers": link.identifiers,
        "evidence_excerpt": evidence_excerpt,
        "evidence_locator": evidence_locator,
    }


def _label_conflicts_with_entity_type(*, label: str, entity_type: str) -> bool:
    looks_gene = _label_looks_gene_like(label)
    if entity_type == "GENE":
        return not looks_gene
    if entity_type in {"DISEASE", "PHENOTYPE"}:
        return looks_gene
    return False


def _label_looks_gene_like(label: str) -> bool:
    tokens = [
        token
        for token in re.split(r"[^A-Za-z0-9-]+", label.strip())
        if token != ""
    ]
    return any(_GENE_TOKEN_RE.match(token) is not None for token in tokens)


__all__ = [
    "EntityCurieLink",
    "entity_candidate_payload_from_curie",
    "normalize_entity_curie",
]
