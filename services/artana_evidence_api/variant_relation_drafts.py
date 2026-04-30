"""Relation proposal drafting for variant-aware document extraction."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast
from uuid import UUID

from artana_evidence_api.claim_fingerprint import compute_claim_fingerprint
from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.ranking import rank_candidate_claim
from artana_evidence_api.shared_fact_assessment_helpers import (
    fact_assessment_payload,
    fact_evidence_weight,
    to_json_value,
)
from artana_evidence_api.types.common import JSONObject, JSONValue
from artana_evidence_api.variant_extraction_contracts import (
    ExtractedEntityCandidate,
    ExtractedRelation,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_store import HarnessDocumentRecord
    from artana_evidence_api.graph_client import GraphTransportBundle

_REQUIRED_VARIANT_ANCHORS = ("gene_symbol", "hgvs_notation")
_MIN_PROTEIN_ALIAS_LENGTH = 7
_THREE_TO_ONE_AMINO_ACID_CODES: dict[str, str] = {
    "Ala": "A",
    "Arg": "R",
    "Asn": "N",
    "Asp": "D",
    "Cys": "C",
    "Gln": "Q",
    "Glu": "E",
    "Gly": "G",
    "His": "H",
    "Ile": "I",
    "Leu": "L",
    "Lys": "K",
    "Met": "M",
    "Phe": "F",
    "Pro": "P",
    "Ser": "S",
    "Thr": "T",
    "Trp": "W",
    "Tyr": "Y",
    "Val": "V",
}


def _build_relation_draft(
    *,
    space_id: UUID,
    document: HarnessDocumentRecord,
    relation: ExtractedRelation,
    graph_api_gateway: GraphTransportBundle,
    entity_index: dict[tuple[str, str], ExtractedEntityCandidate],
    raw_record: JSONObject,
    index: int,
) -> HarnessProposalDraft | None:
    source_label = _clean_text(relation.source_label)
    target_label = _clean_text(relation.target_label)
    if source_label is None or target_label is None:
        return None

    source_candidate = _resolve_relation_entity_candidate(
        relation_type=relation.source_type,
        label=source_label,
        anchors=relation.source_anchors,
        entity_index=entity_index,
    )
    target_candidate = _resolve_relation_entity_candidate(
        relation_type=relation.target_type,
        label=target_label,
        anchors=relation.target_anchors,
        entity_index=entity_index,
    )
    source_match = _resolve_graph_entity(
        space_id=space_id,
        label=source_label,
        graph_api_gateway=graph_api_gateway,
    )
    target_match = _resolve_graph_entity(
        space_id=space_id,
        label=target_label,
        graph_api_gateway=graph_api_gateway,
    )

    source_id = _resolved_or_unresolved_entity_id(
        label=source_label,
        graph_match=source_match,
    )
    target_id = _resolved_or_unresolved_entity_id(
        label=target_label,
        graph_match=target_match,
    )
    confidence = fact_evidence_weight(relation)
    ranking = rank_candidate_claim(
        confidence=confidence,
        supporting_document_count=1,
        evidence_reference_count=1,
    )
    resolved_source_label = (
        cast("str", source_match["display_label"])
        if source_match is not None
        and isinstance(source_match.get("display_label"), str)
        else source_label
    )
    resolved_target_label = (
        cast("str", target_match["display_label"])
        if target_match is not None
        and isinstance(target_match.get("display_label"), str)
        else target_label
    )
    claim_fingerprint = compute_claim_fingerprint(
        resolved_source_label,
        relation.relation_type,
        resolved_target_label,
    )
    source_document_ref = (
        cast("str", raw_record["document_id"])
        if isinstance(raw_record.get("document_id"), str)
        else document.id
    )
    summary = (
        relation.evidence_excerpt
        or relation.claim_text
        or f"{source_label} {relation.relation_type} {target_label}"
    )
    return HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key=f"{document.id}:relation:{index}",
        document_id=document.id,
        title=f"Extracted claim: {source_label} {relation.relation_type} {target_label}",
        summary=summary,
        confidence=confidence,
        ranking_score=ranking.score,
        reasoning_path={
            "kind": "relation_candidate",
            "source_type": relation.source_type,
            "target_type": relation.target_type,
            "source_label": source_label,
            "target_label": target_label,
            "claim_text": relation.claim_text,
            "evidence_locator": relation.evidence_locator,
            "assessment": fact_assessment_payload(relation),
            "source_anchors": relation.source_anchors,
            "target_anchors": relation.target_anchors,
        },
        evidence_bundle=[
            {
                "source_type": document.source_type,
                "locator": relation.evidence_locator
                or f"document:{source_document_ref}",
                "excerpt": summary,
                "relevance": confidence,
            },
        ],
        payload={
            "proposed_subject": source_id,
            "proposed_subject_label": source_label,
            "proposed_subject_entity_candidate": (
                _entity_candidate_payload(source_candidate)
                if source_candidate is not None
                else None
            ),
            "proposed_claim_type": relation.relation_type,
            "proposed_object": target_id,
            "proposed_object_label": target_label,
            "proposed_object_entity_candidate": (
                _entity_candidate_payload(target_candidate)
                if target_candidate is not None
                else None
            ),
            "evidence_entity_ids": [
                value
                for value in (source_id, target_id)
                if not value.startswith("unresolved:")
            ],
        },
        metadata={
            "document_id": document.id,
            "document_title": document.title,
            "document_source_type": document.source_type,
            "subject_label": source_label,
            "object_label": target_label,
            "resolved_subject_label": resolved_source_label,
            "resolved_object_label": resolved_target_label,
            "subject_resolved": source_match is not None,
            "object_resolved": target_match is not None,
            "subject_entity_type": relation.source_type,
            "object_entity_type": relation.target_type,
            "subject_anchors": relation.source_anchors,
            "object_anchors": relation.target_anchors,
            "assessment": fact_assessment_payload(relation),
            **ranking.metadata,
        },
        claim_fingerprint=claim_fingerprint,
    )


def _resolve_relation_entity_candidate(
    *,
    relation_type: str,
    label: str,
    anchors: JSONObject,
    entity_index: dict[tuple[str, str], ExtractedEntityCandidate],
) -> ExtractedEntityCandidate | None:
    normalized_type = relation_type.strip().upper()
    if anchors:
        gene_symbol = _normalized_string(anchors.get("gene_symbol"))
        hgvs_notation = _normalized_string(anchors.get("hgvs_notation"))
        if gene_symbol is not None and hgvs_notation is not None:
            for candidate in entity_index.values():
                if candidate.entity_type.strip().upper() != normalized_type:
                    continue
                if (
                    _normalized_string(candidate.anchors.get("gene_symbol"))
                    == gene_symbol
                    and _normalized_string(candidate.anchors.get("hgvs_notation"))
                    == hgvs_notation
                ):
                    return candidate
    return entity_index.get((normalized_type, label.strip().lower()))


def _resolve_graph_entity(
    *,
    space_id: UUID,
    label: str,
    graph_api_gateway: GraphTransportBundle,
) -> JSONObject | None:
    try:
        response = graph_api_gateway.list_entities(space_id=space_id, q=label, limit=5)
    except GraphServiceClientError:
        return None
    normalized_label = label.strip().casefold()
    for entity in response.entities:
        display_label = entity.display_label or ""
        aliases = {alias.casefold() for alias in entity.aliases}
        if display_label.casefold() == normalized_label or normalized_label in aliases:
            return {
                "id": str(entity.id),
                "display_label": display_label or str(entity.id),
            }
    return None


def _resolved_or_unresolved_entity_id(
    *,
    label: str,
    graph_match: JSONObject | None,
) -> str:
    if graph_match is not None:
        resolved_id = graph_match.get("id")
        if isinstance(resolved_id, str) and resolved_id.strip():
            return resolved_id
    normalized = "".join(
        character.lower() if character.isalnum() else "_" for character in label.strip()
    ).strip("_")
    return f"unresolved:{normalized or 'entity'}"


def _entity_candidate_payload(
    candidate: ExtractedEntityCandidate,
) -> JSONObject:
    identifiers: dict[str, str] = {}
    for key in ("gene_symbol", "hgvs_notation", "hpo_term"):
        value = candidate.anchors.get(key)
        if isinstance(value, str) and value.strip():
            identifiers[key] = value.strip()
    return {
        "entity_type": candidate.entity_type.strip().upper(),
        "label": candidate.label.strip(),
        "display_label": candidate.label.strip(),
        "aliases": _entity_candidate_aliases(candidate),
        "anchors": {
            str(key): to_json_value(value) for key, value in candidate.anchors.items()
        },
        "metadata": {
            str(key): to_json_value(value) for key, value in candidate.metadata.items()
        },
        "identifiers": identifiers,
        "evidence_excerpt": candidate.evidence_excerpt,
        "evidence_locator": candidate.evidence_locator,
        "assessment": fact_assessment_payload(candidate),
    }


def _entity_candidate_aliases(
    candidate: ExtractedEntityCandidate,
) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for raw_value in (
        candidate.metadata.get("hgvs_protein"),
        candidate.metadata.get("hgvs_cdna"),
        candidate.metadata.get("hgvs_genomic"),
        candidate.label,
    ):
        if not isinstance(raw_value, str) or not raw_value.strip():
            continue
        normalized = raw_value.strip()
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        aliases.append(normalized)
    transcript = candidate.metadata.get("transcript")
    hgvs_notation = candidate.anchors.get("hgvs_notation")
    hgvs_protein = candidate.metadata.get("hgvs_protein")
    if (
        isinstance(transcript, str)
        and transcript.strip()
        and isinstance(
            hgvs_notation,
            str,
        )
        and hgvs_notation.strip()
    ):
        for value in (
            f"{transcript.strip()}:{hgvs_notation.strip()}",
            (
                f"{transcript.strip()}:{hgvs_notation.strip()} ({hgvs_protein.strip()})"
                if isinstance(hgvs_protein, str) and hgvs_protein.strip()
                else None
            ),
        ):
            if value is None:
                continue
            key = value.casefold()
            if key in seen:
                continue
            seen.add(key)
            aliases.append(value)
    for protein_alias in _protein_aliases(hgvs_protein):
        key = protein_alias.casefold()
        if key in seen:
            continue
        seen.add(key)
        aliases.append(protein_alias)
    return aliases


def _variant_candidate_is_persistable(
    candidate: ExtractedEntityCandidate,
) -> bool:
    return all(
        _clean_text(candidate.anchors.get(key)) is not None
        for key in _REQUIRED_VARIANT_ANCHORS
    )


def _normalized_string(raw_value: object) -> str | None:
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    return normalized.lower() if normalized else None


def _clean_text(raw_value: object) -> str | None:
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    return normalized if normalized else None


def _json_object_value(raw_value: object) -> JSONObject | None:
    if not isinstance(raw_value, dict):
        return None
    return {str(key): to_json_value(value) for key, value in raw_value.items()}


def _normalized_metadata_value(raw_value: object) -> JSONValue | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, str):
        normalized = raw_value.strip()
        return normalized if normalized else None
    if isinstance(raw_value, list):
        normalized_list = [
            to_json_value(item)
            for item in raw_value
            if item is not None and (not isinstance(item, str) or item.strip())
        ]
        return normalized_list if normalized_list else None
    return to_json_value(raw_value)


def _protein_aliases(raw_value: object) -> tuple[str, ...]:
    if not isinstance(raw_value, str):
        return ()
    normalized = raw_value.strip()
    if not normalized:
        return ()
    stripped = normalized.removeprefix("p.")
    aliases: list[str] = []
    if stripped and stripped != normalized:
        aliases.append(stripped)
    short_alias = _short_protein_alias(stripped)
    if short_alias is not None:
        aliases.append(short_alias)
    return tuple(aliases)


def _short_protein_alias(protein_label: str) -> str | None:
    if len(protein_label) < _MIN_PROTEIN_ALIAS_LENGTH:
        return None
    prefix = protein_label[:3]
    suffix = protein_label[-3:]
    residue_index = protein_label[3:-3]
    if not residue_index.isdigit():
        return None
    start_code = _THREE_TO_ONE_AMINO_ACID_CODES.get(prefix)
    end_code = _THREE_TO_ONE_AMINO_ACID_CODES.get(suffix)
    if start_code is None or end_code is None:
        return None
    return f"{start_code}{residue_index}{end_code}"


__all__ = [
    "_build_relation_draft",
    "_clean_text",
    "_entity_candidate_aliases",
    "_entity_candidate_payload",
    "_json_object_value",
    "_normalized_metadata_value",
    "_normalized_string",
    "_protein_aliases",
    "_resolved_or_unresolved_entity_id",
    "_variant_candidate_is_persistable",
]
