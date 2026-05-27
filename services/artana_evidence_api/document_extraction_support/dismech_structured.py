"""Deterministic extraction for DisMech LinkML YAML documents."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import yaml
from artana_evidence_api.claim_fingerprint import compute_claim_fingerprint
from artana_evidence_api.document_store import HarnessDocumentRecord
from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.types.common import JSONObject

_DISMECH_METADATA_VALUES = frozenset({"dismech", "dismech_yaml", "dismech_linkml"})
_RELATION_TOKEN_RE = re.compile(r"[^A-Za-z0-9]+")


@dataclass(frozen=True, slots=True)
class DisMechStructuredExtractionResult:
    """Proposal drafts and diagnostics from one DisMech structured extraction."""

    proposal_drafts: tuple[HarnessProposalDraft, ...]
    skipped_items: list[JSONObject] = field(default_factory=list)
    candidate_discovery: JSONObject = field(default_factory=dict)
    extraction_diagnostics: JSONObject = field(default_factory=dict)

    @property
    def candidate_count(self) -> int:
        return len(self.proposal_drafts)


def document_supports_dismech_structured_extraction(
    document: HarnessDocumentRecord,
) -> bool:
    """Return whether one document should use deterministic DisMech extraction."""

    for key in ("source_kind", "source", "doc_type", "content_type"):
        value = document.metadata.get(key)
        if (
            isinstance(value, str)
            and value.strip().casefold() in _DISMECH_METADATA_VALUES
        ):
            return True
    return document.media_type in {"application/x-yaml", "text/yaml"} and (
        "dismech" in document.title.casefold()
    )


def build_dismech_structured_extraction_drafts(
    *,
    document: HarnessDocumentRecord,
) -> DisMechStructuredExtractionResult:
    """Walk DisMech LinkML YAML and build reviewable proposal drafts."""

    payload = _parse_yaml_mapping(document.text_content)
    if payload is None:
        return DisMechStructuredExtractionResult(
            proposal_drafts=(),
            skipped_items=[
                {
                    "document_id": document.id,
                    "document_title": document.title,
                    "reason": "invalid_dismech_yaml",
                },
            ],
            candidate_discovery=_candidate_discovery(0),
            extraction_diagnostics={"dismech_structured_extraction": False},
        )
    drafts = [
        *_pathophysiology_drafts(document=document, payload=payload),
        *_variant_drafts(document=document, payload=payload),
        *_phenotype_drafts(document=document, payload=payload),
        *_dataset_drafts(document=document, payload=payload),
    ]
    return DisMechStructuredExtractionResult(
        proposal_drafts=tuple(drafts),
        skipped_items=[],
        candidate_discovery=_candidate_discovery(len(drafts)),
        extraction_diagnostics={
            "dismech_structured_extraction": True,
            "dismech_yaml_parsed": True,
        },
    )


def _parse_yaml_mapping(text_content: str) -> Mapping[str, object] | None:
    try:
        loaded = yaml.safe_load(text_content)
    except yaml.YAMLError:
        return None
    return _mapping(loaded)


def _pathophysiology_drafts(
    *,
    document: HarnessDocumentRecord,
    payload: Mapping[str, object],
) -> list[HarnessProposalDraft]:
    drafts: list[HarnessProposalDraft] = []
    nodes = _first_mapping_list(
        payload,
        ("pathophysiology_nodes", "pathophysiology", "mechanism_nodes"),
    )
    for node_index, node in enumerate(nodes):
        node_id = _text(node.get("id")) or f"pathophysiology:{node_index}"
        node_label = _text(node.get("label")) or node_id
        steps = _first_mapping_list(
            node,
            ("causal_chain", "causal_steps", "steps", "claims"),
        )
        for step_index, step in enumerate(steps):
            subject = _first_text(step, ("subject", "cause", "upstream", "from"))
            obj = _first_text(step, ("object", "effect", "downstream", "to"))
            if subject is None or obj is None:
                continue
            relation_type = _relation_type(
                _first_text(step, ("predicate", "relation", "mechanism")) or "CAUSES",
            )
            sentence = _first_text(step, ("sentence", "description", "summary")) or (
                f"{subject} {relation_type} {obj}"
            )
            pmids = _pmids(step)
            drafts.append(
                _claim_draft(
                    document=document,
                    source_key=(
                        f"{document.id}:dismech:pathophysiology:"
                        f"{node_index}:{step_index}"
                    ),
                    subject_label=subject,
                    relation_type=relation_type,
                    object_label=obj,
                    object_id=obj,
                    summary=sentence,
                    metadata={
                        "origin": "dismech_structured_extraction",
                        "pathophysiology_node_id": node_id,
                        "pathophysiology_node_label": node_label,
                        "pmids": pmids,
                    },
                    evidence_bundle=_evidence_bundle(
                        document=document,
                        pmids=pmids,
                        excerpt=sentence,
                    ),
                ),
            )
    return drafts


def _variant_drafts(
    *,
    document: HarnessDocumentRecord,
    payload: Mapping[str, object],
) -> list[HarnessProposalDraft]:
    drafts: list[HarnessProposalDraft] = []
    for index, variant in enumerate(_first_mapping_list(payload, ("variants",))):
        gene = _first_text(variant, ("gene", "gene_symbol", "subject"))
        hgvs = _first_text(variant, ("hgvs", "hgvs_p", "protein_change", "variant"))
        if gene is None and hgvs is None:
            continue
        variant_label = " ".join(value for value in (gene, hgvs) if value)
        disease = _first_text(variant, ("disease", "condition", "disorder"))
        consequence = _first_text(variant, ("consequence", "effect"))
        pmids = _pmids(variant)
        summary = f"DisMech variant candidate: {variant_label}"
        if disease is not None:
            summary = f"{summary} in {disease}"
        drafts.append(
            HarnessProposalDraft(
                proposal_type="variant_evidence_candidate",
                source_kind="dismech_extraction",
                source_key=f"{document.id}:dismech:variant:{index}",
                document_id=document.id,
                title=f"DisMech variant: {variant_label}",
                summary=summary,
                confidence=0.9,
                ranking_score=0.9,
                reasoning_path={
                    "document_id": document.id,
                    "document_title": document.title,
                    "variant_index": index,
                    "extraction_method": "dismech_linkml_yaml",
                },
                evidence_bundle=_evidence_bundle(
                    document=document,
                    pmids=pmids,
                    excerpt=summary,
                ),
                payload={
                    "gene_symbol": gene,
                    "variant_label": variant_label,
                    "hgvs": hgvs,
                    "disease": disease,
                    "consequence": consequence,
                },
                metadata={
                    "origin": "dismech_structured_extraction",
                    "gene_symbol": gene,
                    "hgvs": _first_text(variant, ("hgvs",)),
                    "hgvs_p": _first_text(variant, ("hgvs_p", "protein_change")),
                    "disease": disease,
                    "consequence": consequence,
                    "pmids": pmids,
                },
            ),
        )
    return drafts


def _phenotype_drafts(
    *,
    document: HarnessDocumentRecord,
    payload: Mapping[str, object],
) -> list[HarnessProposalDraft]:
    drafts: list[HarnessProposalDraft] = []
    phenotypes = _first_mapping_list(
        payload,
        ("phenotype_associations", "phenotypes", "hpo_associations"),
    )
    for index, phenotype in enumerate(phenotypes):
        hpo_id = _first_text(phenotype, ("phenotype_id", "hpo_id", "id"))
        label = _first_text(phenotype, ("phenotype_label", "label", "name"))
        subject = _first_text(phenotype, ("gene", "gene_symbol", "subject"))
        if hpo_id is None or subject is None:
            continue
        object_label = label or hpo_id
        pmids = _pmids(phenotype)
        sentence = f"{subject} ASSOCIATED_WITH {object_label} ({hpo_id})"
        drafts.append(
            _claim_draft(
                document=document,
                source_key=f"{document.id}:dismech:phenotype:{index}",
                subject_label=subject,
                relation_type="ASSOCIATED_WITH",
                object_label=object_label,
                object_id=hpo_id,
                summary=sentence,
                metadata={
                    "origin": "dismech_structured_extraction",
                    "hpo_id": hpo_id,
                    "phenotype_label": object_label,
                    "pmids": pmids,
                },
                evidence_bundle=_evidence_bundle(
                    document=document,
                    pmids=pmids,
                    excerpt=sentence,
                ),
            ),
        )
    return drafts


def _dataset_drafts(
    *,
    document: HarnessDocumentRecord,
    payload: Mapping[str, object],
) -> list[HarnessProposalDraft]:
    drafts: list[HarnessProposalDraft] = []
    for index, dataset in enumerate(_first_mapping_list(payload, ("datasets",))):
        dataset_id = _first_text(dataset, ("id", "dataset_id", "name"))
        label = _first_text(dataset, ("label", "title", "name")) or dataset_id
        if dataset_id is None:
            continue
        pmids = _pmids(dataset)
        summary = f"DisMech dataset reference: {label}"
        drafts.append(
            HarnessProposalDraft(
                proposal_type="source_dataset_candidate",
                source_kind="dismech_extraction",
                source_key=f"{document.id}:dismech:dataset:{index}",
                document_id=document.id,
                title=f"DisMech dataset: {label}",
                summary=summary,
                confidence=0.85,
                ranking_score=0.85,
                reasoning_path={
                    "document_id": document.id,
                    "document_title": document.title,
                    "dataset_id": dataset_id,
                    "extraction_method": "dismech_linkml_yaml",
                },
                evidence_bundle=_evidence_bundle(
                    document=document,
                    pmids=pmids,
                    excerpt=summary,
                ),
                payload={"dataset_id": dataset_id, "dataset_label": label},
                metadata={
                    "origin": "dismech_structured_extraction",
                    "dataset_id": dataset_id,
                    "dataset_label": label,
                    "pmids": pmids,
                },
            ),
        )
    return drafts


def _claim_draft(
    *,
    document: HarnessDocumentRecord,
    source_key: str,
    subject_label: str,
    relation_type: str,
    object_label: str,
    object_id: str,
    summary: str,
    metadata: JSONObject,
    evidence_bundle: list[JSONObject],
) -> HarnessProposalDraft:
    return HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="dismech_extraction",
        source_key=source_key,
        document_id=document.id,
        title=f"DisMech claim: {subject_label} {relation_type} {object_label}",
        summary=summary,
        confidence=0.9,
        ranking_score=0.9,
        reasoning_path={
            "document_id": document.id,
            "document_title": document.title,
            "extraction_method": "dismech_linkml_yaml",
            "subject_label": subject_label,
            "relation_type": relation_type,
            "object_label": object_label,
        },
        evidence_bundle=evidence_bundle,
        payload={
            "proposed_subject": subject_label,
            "proposed_subject_label": subject_label,
            "proposed_claim_type": relation_type,
            "proposed_object": object_id,
            "proposed_object_label": object_label,
            "evidence_entity_ids": [],
        },
        metadata={
            **metadata,
            "document_id": document.id,
            "document_title": document.title,
            "document_source_type": document.source_type,
        },
        claim_fingerprint=compute_claim_fingerprint(
            subject_label,
            relation_type,
            object_label,
        ),
    )


def _candidate_discovery(candidate_count: int) -> JSONObject:
    return {
        "method": "dismech_linkml_yaml",
        "source_kind": "dismech",
        "candidate_count": candidate_count,
    }


def _evidence_bundle(
    *,
    document: HarnessDocumentRecord,
    pmids: Sequence[str],
    excerpt: str,
) -> list[JSONObject]:
    if pmids:
        return [
            {
                "source_type": "paper",
                "locator": f"PMID:{pmid}",
                "excerpt": excerpt,
                "relevance": 0.9,
            }
            for pmid in pmids
        ]
    return [
        {
            "source_type": "document",
            "locator": f"document:{document.id}",
            "excerpt": excerpt,
            "relevance": 0.8,
        },
    ]


def _relation_type(value: str) -> str:
    normalized = _RELATION_TOKEN_RE.sub("_", value.strip().upper()).strip("_")
    return normalized or "ASSOCIATED_WITH"


def _pmids(record: Mapping[str, object]) -> list[str]:
    direct = _string_list(record.get("pmids") or record.get("publications"))
    evidence = _mapping(record.get("evidence"))
    if evidence is not None:
        direct.extend(
            _string_list(evidence.get("pmids") or evidence.get("publications"))
        )
    seen: set[str] = set()
    result: list[str] = []
    for pmid in direct:
        normalized = pmid.removeprefix("PMID:").strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _first_mapping_list(
    record: Mapping[str, object],
    keys: tuple[str, ...],
) -> list[Mapping[str, object]]:
    for key in keys:
        values = _mapping_list(record.get(key))
        if values:
            return values
    return []


def _first_text(record: Mapping[str, object], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = _text(record.get(key))
        if value is not None:
            return value
    return None


def _mapping(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return None


def _mapping_list(value: object) -> list[Mapping[str, object]]:
    if isinstance(value, Mapping):
        return [
            _mapping_value for _mapping_value in (_mapping(value),) if _mapping_value
        ]
    if not isinstance(value, list | tuple):
        return []
    result: list[Mapping[str, object]] = []
    for item in value:
        mapping = _mapping(item)
        if mapping is not None:
            result.append(mapping)
    return result


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list | tuple):
        result: list[str] = []
        for item in value:
            result.extend(_string_list(item))
        return result
    return []


def _text(value: object) -> str | None:
    if isinstance(value, str):
        normalized = " ".join(value.split())
        return normalized or None
    if isinstance(value, int | float):
        return str(value)
    return None


__all__ = [
    "DisMechStructuredExtractionResult",
    "build_dismech_structured_extraction_drafts",
    "document_supports_dismech_structured_extraction",
]
