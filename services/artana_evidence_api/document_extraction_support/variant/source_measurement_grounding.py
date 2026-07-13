"""Deterministic subject grounding for copied source measurements."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def measurement_is_uniquely_bound_to_subject(
    *,
    source_text: str,
    literal_span: str,
    selected_evidence_excerpt: str,
    selected_anchors: Mapping[str, object],
    competing_anchors: Sequence[Mapping[str, object]],
) -> bool:
    """Require one persisted excerpt to bind the measurement to one variant."""
    if len(_literal_spans(source_text, selected_evidence_excerpt)) != 1:
        return False
    if len(_literal_spans(selected_evidence_excerpt, literal_span)) != 1:
        return False
    if not _contains_identity_anchors(selected_evidence_excerpt, selected_anchors):
        return False
    return not any(
        _contains_identity_anchors(selected_evidence_excerpt, anchors)
        for anchors in competing_anchors
    )


def _contains_identity_anchors(
    evidence_excerpt: str,
    anchors: Mapping[str, object],
) -> bool:
    gene_symbol = anchors.get("gene_symbol")
    hgvs_notation = anchors.get("hgvs_notation")
    if not isinstance(gene_symbol, str) or not isinstance(hgvs_notation, str):
        return False
    normalized_excerpt = evidence_excerpt.casefold()
    return (
        gene_symbol.strip() != ""
        and hgvs_notation.strip() != ""
        and gene_symbol.strip().casefold() in normalized_excerpt
        and hgvs_notation.strip().casefold() in normalized_excerpt
    )


def _literal_spans(source_text: str, literal: str) -> list[tuple[int, int]]:
    if literal == "":
        return []
    spans: list[tuple[int, int]] = []
    start = 0
    while (index := source_text.find(literal, start)) >= 0:
        spans.append((index, index + len(literal)))
        start = index + 1
    return spans


__all__ = ["measurement_is_uniquely_bound_to_subject"]
