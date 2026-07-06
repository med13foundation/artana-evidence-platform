"""CURIE normalization and draft payload support for extracted entities."""

from __future__ import annotations

import re
from dataclasses import dataclass

from artana_evidence_api.document_extraction_support.entity_grounding.contracts import (
    CurieSource,
    ModelHintStatus,
    ReviewOnlyEntityRecord,
    VerifiedEntityRecord,
)
from artana_evidence_api.document_extraction_support.entity_grounding.verified_dictionary import (
    review_only_record_for_label,
    verified_record_for_label,
)
from artana_evidence_api.types.common import JSONObject

_CURIE_RE = re.compile(r"^(?P<prefix>[A-Za-z][A-Za-z0-9_.-]{1,31}):(?P<local>[A-Za-z0-9][A-Za-z0-9_.:-]{0,127})$")
_GENE_TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9-]{1,11}$")
_CURIE_PREFIXES: dict[str, tuple[str, str, str]] = {
    "CHEBI": ("CHEBI", "chebi_id", "DRUG"),
    "CLINVAR": ("ClinVar", "clinvar_id", "VARIANT"),
    "DRUGBANK": ("DRUGBANK", "drugbank_id", "DRUG"),
    "GO": ("GO", "go_id", "BIOLOGICAL_PROCESS"),
    "HGNC": ("HGNC", "hgnc_id", "GENE"),
    "HP": ("HP", "hpo_id", "PHENOTYPE"),
    "HPO": ("HP", "hpo_id", "PHENOTYPE"),
    "MESH": ("MESH", "mesh_id", "BIOMEDICAL_CONCEPT"),
    "MONDO": ("MONDO", "mondo_id", "DISEASE"),
    "NCBIGENE": ("NCBIGene", "ncbigene_id", "GENE"),
    "NCIT": ("NCIT", "ncit_id", "BIOMEDICAL_CONCEPT"),
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
    grounding_curation_status: str | None = None
    grounding_reason_code: str | None = None
    trusted_identifier_allowed: bool | None = None
    model_hint_curie: str | None = None
    model_hint_status: ModelHintStatus | None = None

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
        if self.trusted_identifier_allowed is not None:
            payload["trusted_identifier_allowed"] = self.trusted_identifier_allowed
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.grounding_curation_status is not None:
            payload["grounding_curation_status"] = self.grounding_curation_status
        if self.grounding_reason_code is not None:
            payload["grounding_reason_code"] = self.grounding_reason_code
        if self.model_hint_curie is not None:
            payload["model_hint_curie"] = self.model_hint_curie
        if self.model_hint_status is not None:
            payload["model_hint_status"] = self.model_hint_status
        return payload


def normalize_entity_curie(
    raw_curie: str | None,
    *,
    label: str,
    source: CurieSource = "model",
) -> EntityCurieLink:
    """Normalize a model-supplied CURIE or return a typed abstention."""

    if source in {"model", "verified_linker", "none"}:
        review_record = review_only_record_for_label(label)
        if review_record is not None:
            return _review_only_link_from_record(review_record, raw_curie=raw_curie)

    if source in {"model", "verified_linker"}:
        record = verified_record_for_label(label)
        if record is not None:
            return _link_from_verified_record_with_hint(
                record,
                raw_curie=raw_curie,
            )

    if source == "verified_linker":
        return _normalize_raw_curie(raw_curie, label=label, source="model")

    return _normalize_raw_curie(raw_curie, label=label, source=source)


def _normalize_raw_curie(
    raw_curie: str | None,
    *,
    label: str,
    source: CurieSource,
    enforce_label_type: bool = True,
) -> EntityCurieLink:
    """Normalize a raw CURIE without upgrading model hints to trusted links."""

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
    if enforce_label_type and _label_conflicts_with_entity_type(
        label=label,
        entity_type=entity_type,
    ):
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


def _link_from_verified_record(
    record: VerifiedEntityRecord,
    *,
    model_hint_curie: str | None = None,
    model_hint_status: ModelHintStatus | None = None,
) -> EntityCurieLink:
    link = _normalize_raw_curie(
        record.curie,
        label=record.label,
        source="verified_linker",
        enforce_label_type=False,
    )
    if link.status != "linked":
        return link
    return EntityCurieLink(
        status=link.status,
        curie=link.curie,
        namespace=link.namespace,
        identifier_key=link.identifier_key,
        entity_type=link.entity_type,
        source=link.source,
        reason=link.reason,
        model_hint_curie=model_hint_curie,
        model_hint_status=model_hint_status,
    )


def _link_from_verified_record_with_hint(
    record: VerifiedEntityRecord,
    *,
    raw_curie: str | None,
) -> EntityCurieLink:
    if raw_curie is None or raw_curie.strip() == "":
        return _link_from_verified_record(record)
    normalized_hint = _normalize_supported_curie_value(raw_curie)
    if normalized_hint is None:
        return _link_from_verified_record(
            record,
            model_hint_curie=raw_curie.strip(),
            model_hint_status="invalid",
        )
    model_hint_status: ModelHintStatus = (
        "matched" if _curies_equal(normalized_hint, record.curie) else "replaced"
    )
    return _link_from_verified_record(
        record,
        model_hint_curie=normalized_hint,
        model_hint_status=model_hint_status,
    )


def _review_only_link_from_record(
    record: ReviewOnlyEntityRecord,
    *,
    raw_curie: str | None,
) -> EntityCurieLink:
    model_hint_curie: str | None = None
    model_hint_status: ModelHintStatus | None = None
    if raw_curie is not None and raw_curie.strip() != "":
        normalized_hint = _normalize_supported_curie_value(raw_curie)
        model_hint_curie = normalized_hint or raw_curie.strip()
        if normalized_hint is None:
            model_hint_status = "invalid"
    return EntityCurieLink(
        status="abstained",
        source="none",
        reason=record.reason,
        grounding_curation_status=record.curation_status,
        grounding_reason_code=record.reason_code,
        trusted_identifier_allowed=record.trusted_identifier_allowed,
        model_hint_curie=model_hint_curie,
        model_hint_status=model_hint_status,
    )


def _curies_equal(left: str, right: str) -> bool:
    return _normalize_curie_for_match(left) == _normalize_curie_for_match(right)


def _normalize_curie_for_match(value: str) -> str:
    prefix, separator, local = value.strip().partition(":")
    if separator == "":
        return value.strip().upper()
    return f"{prefix.upper()}:{local}"


def _normalize_supported_curie_value(raw_curie: str) -> str | None:
    match = _CURIE_RE.match(raw_curie.strip())
    if match is None:
        return None
    prefix_config = _CURIE_PREFIXES.get(match.group("prefix").upper())
    if prefix_config is None:
        return None
    namespace = prefix_config[0]
    return f"{namespace}:{match.group('local')}"


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
