"""Service-owned bridges for shared variant-aware extraction runtime code."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime

from artana_evidence_api.shared_fact_assessment_helpers import to_json_value
from artana_evidence_api.types.common import (
    JSONObject,
    JSONValue,
    ResearchSpaceSettings,
)
from artana_evidence_api.variant_extraction_contracts import ExtractionContract
from pydantic import BaseModel, Field

_TEXT_FIELD_PRIORITY = (
    "full_text",
    "text",
    "content",
    "abstract",
    "description",
    "summary",
    "clinical_summary",
    "interpretation",
    "title",
)
_PHENOTYPE_TRIGGER_WORDS = (
    "phenotype",
    "disease",
    "disorder",
    "syndrome",
    "delay",
    "cardiomyopathy",
    "epilepsy",
    "ataxia",
    "autism",
    "seizure",
)
_CLASSIFICATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Likely Pathogenic", re.compile(r"\blikely pathogenic\b", re.IGNORECASE)),
    ("Pathogenic", re.compile(r"\bpathogenic\b", re.IGNORECASE)),
    (
        "Variant of Uncertain Significance",
        re.compile(
            r"\b(?:vus|variant of uncertain significance|uncertain significance)\b",
            re.IGNORECASE,
        ),
    ),
    ("Likely Benign", re.compile(r"\blikely benign\b", re.IGNORECASE)),
    ("Benign", re.compile(r"\bbenign\b", re.IGNORECASE)),
)
_ZYGOSITY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "compound heterozygous",
        re.compile(r"\bcompound heterozyg(?:ous|osity)\b", re.IGNORECASE),
    ),
    ("heterozygous", re.compile(r"\bheterozyg(?:ous|osity)\b", re.IGNORECASE)),
    ("homozygous", re.compile(r"\bhomozyg(?:ous|osity)\b", re.IGNORECASE)),
    ("hemizygous", re.compile(r"\bhemizyg(?:ous|osity)\b", re.IGNORECASE)),
)
_INHERITANCE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("autosomal dominant", re.compile(r"\bautosomal dominant\b", re.IGNORECASE)),
    ("autosomal recessive", re.compile(r"\bautosomal recessive\b", re.IGNORECASE)),
    ("maternally inherited", re.compile(r"\bmaternally inherited\b", re.IGNORECASE)),
    ("paternally inherited", re.compile(r"\bpaternally inherited\b", re.IGNORECASE)),
    ("x-linked", re.compile(r"\bx-linked\b", re.IGNORECASE)),
    ("de novo", re.compile(r"\bde\s+novo\b", re.IGNORECASE)),
    ("inherited", re.compile(r"\binherited\b", re.IGNORECASE)),
)
_TRANSCRIPT_PATTERN = re.compile(r"\bNM_\d+(?:\.\d+)?\b")
_GENE_VARIANT_PATTERN = re.compile(
    r"\b(?P<gene>[A-Z][A-Z0-9-]{1,15})"
    r"(?:\s*\((?P<transcript_paren>NM_\d+(?:\.\d+)?)\))?"
    r"(?:\s+(?P<transcript_inline>NM_\d+(?:\.\d+)?))?"
    r"(?:\s+|:\s*)(?P<hgvs>(?:c|p|g)\.[A-Za-z0-9_().:+\-=>*?]+)\b",
)
_CDNA_HGVS_PATTERN = re.compile(
    r"\bc\.[0-9*_\-+]+"
    r"(?:[ACGT]>[ACGT]|del(?:[ACGT]+)?|dup(?:[ACGT]+)?|ins(?:[ACGT]+)|"
    r"_[0-9*_\-+]+(?:del|dup|ins(?:[ACGT]+)))\b",
    re.IGNORECASE,
)
_PROTEIN_HGVS_PATTERN = re.compile(
    r"\bp\.[A-Z][a-z]{2}\d+(?:[A-Z][a-z]{2}|Ter|=|fs\*?\d*)\b",
)
_GENOMIC_HGVS_PATTERN = re.compile(
    r"\bg\.[0-9_]+(?:[ACGT]>[ACGT]|del|dup|ins[ACGT]+)\b",
    re.IGNORECASE,
)
_COORDINATE_PATTERN = re.compile(
    r"\b(?P<coordinate>(?:chr)?[0-9XYM]{1,2}:[0-9,]+(?:-[0-9,]+)?)\b",
    re.IGNORECASE,
)
_GENOME_BUILD_PATTERN = re.compile(r"\b(GRCh(?:37|38)|hg(?:19|38))\b", re.IGNORECASE)
_EXON_INTRON_PATTERN = re.compile(
    r"\b((?:exon|intron)\s+\d+[A-Za-z]?)\b",
    re.IGNORECASE,
)


def _empty_payload() -> JSONObject:
    return {}


def _empty_settings() -> ResearchSpaceSettings:
    return {}


class ExtractionContext(BaseModel):
    """Service-local extraction context for bridged extraction execution."""

    document_id: str = Field(..., min_length=1, max_length=64)
    source_type: str = Field(default="clinvar", min_length=1, max_length=64)
    research_space_id: str | None = Field(default=None)
    research_space_settings: ResearchSpaceSettings = Field(
        default_factory=_empty_settings,
    )
    raw_record: JSONObject = Field(default_factory=_empty_payload)
    recognized_entities: list[JSONObject] = Field(default_factory=list)
    recognized_observations: list[JSONObject] = Field(default_factory=list)
    genomics_signals: JSONObject = Field(default_factory=_empty_payload)
    shadow_mode: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def build_genomics_signal_bundle(
    *,
    raw_record: JSONObject,
    source_type: str,
) -> JSONObject:
    """Return a JSON-safe structured genomics hint bundle for extraction."""
    text_blobs = _collect_text_blobs(raw_record)
    text = "\n".join(blob["text"] for blob in text_blobs if blob["text"]).strip()
    variant_candidates = _extract_variant_candidates(raw_record=raw_record, text=text)
    source_grounding_present = any(
        isinstance(raw_record.get(key), dict)
        for key in ("clinvar_grounding", "marrvel_grounding")
    )
    normalized_source_type = source_type.strip().lower()
    genomics_tagged_source = normalized_source_type in {"clinvar", "marrvel"}
    variant_language_present = bool(
        variant_candidates
        or _CDNA_HGVS_PATTERN.search(text)
        or _PROTEIN_HGVS_PATTERN.search(text)
        or _GENOMIC_HGVS_PATTERN.search(text)
        or raw_record.get("gene_symbol")
        or raw_record.get("hgvs_notation")
    )
    return {
        "source_type": normalized_source_type,
        "variant_aware_recommended": (
            bool(variant_candidates)
            or source_grounding_present
            or (genomics_tagged_source and variant_language_present)
        ),
        "source_grounding_present": source_grounding_present,
        "text_blob_count": len(text_blobs),
        "variant_candidates": variant_candidates,
    }


def _extract_variant_candidates(
    *,
    raw_record: JSONObject,
    text: str,
) -> list[JSONObject]:
    candidates: list[JSONObject] = []
    seen: set[tuple[str, str]] = set()
    raw_gene_symbol = _read_scalar(raw_record, "gene_symbol", "gene")
    raw_transcript = _read_scalar(raw_record, "transcript", "transcript_id")
    raw_cdna = _read_scalar(raw_record, "hgvs_cdna")
    raw_protein = _read_scalar(raw_record, "hgvs_protein")
    raw_genomic = _read_scalar(raw_record, "hgvs_genomic")
    raw_hgvs = _read_scalar(raw_record, "hgvs_notation", "hgvs", "variant")

    for match in _GENE_VARIANT_PATTERN.finditer(text):
        gene_symbol = match.group("gene").strip()
        transcript = _normalize_transcript(
            match.group("transcript_paren")
            or match.group("transcript_inline")
            or raw_transcript,
        )
        hgvs = _normalize_hgvs(match.group("hgvs"))
        if hgvs is None:
            continue
        candidate = _build_variant_candidate(
            gene_symbol=gene_symbol,
            transcript=transcript,
            raw_hgvs=hgvs,
            raw_record=raw_record,
            window_text=_surrounding_text(text, match.start(), match.end()),
            match_start=match.start(),
            match_end=match.end(),
        )
        key = _variant_candidate_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)

    if raw_gene_symbol is not None:
        raw_variant_candidate = _build_raw_record_variant_candidate(
            raw_record=raw_record,
            gene_symbol=raw_gene_symbol,
            transcript=raw_transcript,
            raw_hgvs=raw_hgvs,
            raw_cdna=raw_cdna,
            raw_protein=raw_protein,
            raw_genomic=raw_genomic,
            text=text,
        )
        if raw_variant_candidate is not None:
            key = _variant_candidate_key(raw_variant_candidate)
            if key not in seen:
                seen.add(key)
                candidates.append(raw_variant_candidate)

    return candidates


def _variant_candidate_key(candidate: JSONObject) -> tuple[str, str]:
    anchors = candidate.get("anchors")
    if not isinstance(anchors, dict):
        return ("", "")
    gene_symbol = anchors.get("gene_symbol")
    hgvs_notation = anchors.get("hgvs_notation")
    return (
        gene_symbol if isinstance(gene_symbol, str) else "",
        hgvs_notation if isinstance(hgvs_notation, str) else "",
    )


def _build_raw_record_variant_candidate(
    *,
    raw_record: JSONObject,
    gene_symbol: str,
    transcript: str | None,
    raw_hgvs: str | None,
    raw_cdna: str | None,
    raw_protein: str | None,
    raw_genomic: str | None,
    text: str,
) -> JSONObject | None:
    effective_cdna = _normalize_hgvs(raw_cdna or raw_hgvs)
    effective_protein = _normalize_hgvs(raw_protein)
    effective_genomic = _normalize_hgvs(raw_genomic)
    hgvs_notation = effective_cdna or effective_protein or effective_genomic
    if hgvs_notation is None:
        return None
    return _build_variant_candidate(
        gene_symbol=gene_symbol,
        transcript=transcript,
        raw_hgvs=hgvs_notation,
        raw_record=raw_record,
        window_text=_first_non_empty_excerpt(text),
        match_start=None,
        match_end=None,
    )


def _build_variant_candidate(
    *,
    gene_symbol: str,
    transcript: str | None,
    raw_hgvs: str,
    raw_record: JSONObject,
    window_text: str,
    match_start: int | None,
    match_end: int | None,
) -> JSONObject:
    hgvs_cdna = raw_hgvs if raw_hgvs.startswith("c.") else None
    hgvs_protein = _first_match(_PROTEIN_HGVS_PATTERN, window_text)
    hgvs_genomic = _first_match(_GENOMIC_HGVS_PATTERN, window_text)
    if raw_hgvs.startswith("p."):
        hgvs_protein = raw_hgvs
    if raw_hgvs.startswith("g."):
        hgvs_genomic = raw_hgvs
    hgvs_notation = hgvs_cdna or hgvs_protein or hgvs_genomic or raw_hgvs
    coordinate = _first_match(_COORDINATE_PATTERN, window_text, group="coordinate")
    genome_build = _first_match(_GENOME_BUILD_PATTERN, window_text)
    exon_or_intron = _first_match(_EXON_INTRON_PATTERN, window_text)
    classification = _extract_first_label(window_text, _CLASSIFICATION_PATTERNS)
    metadata: JSONObject = {
        "transcript": to_json_value(transcript),
        "genomic_position": to_json_value(coordinate),
        "genome_build": to_json_value(genome_build),
        "hgvs_cdna": to_json_value(hgvs_cdna),
        "hgvs_protein": to_json_value(hgvs_protein),
        "hgvs_genomic": to_json_value(hgvs_genomic),
        "exon_or_intron": to_json_value(exon_or_intron),
        "zygosity": to_json_value(_extract_first_label(window_text, _ZYGOSITY_PATTERNS)),
        "inheritance": to_json_value(
            _extract_first_label(window_text, _INHERITANCE_PATTERNS),
        ),
        "classification": to_json_value(classification),
        "source_record_ids": [
            to_json_value(item) for item in _collect_source_record_ids(raw_record)
        ],
        "phenotype_spans": _extract_phenotype_spans(window_text),
        "source_span": (
            {"start": match_start, "end": match_end}
            if match_start is not None and match_end is not None
            else {}
        ),
    }
    return {
        "gene_symbol": gene_symbol,
        "hgvs_notation": hgvs_notation,
        "anchors": {
            "gene_symbol": gene_symbol,
            "hgvs_notation": hgvs_notation,
        },
        "metadata": metadata,
        "evidence_excerpt": _truncate_text(window_text),
        "evidence_locator": _build_locator(
            match_start=match_start,
            match_end=match_end,
            genome_build=genome_build,
        ),
    }


def _collect_source_record_ids(raw_record: JSONObject) -> list[str]:
    identifiers: list[str] = []
    for key in ("clinvar_id", "variation_id", "accession", "source_record_id"):
        value = raw_record.get(key)
        if isinstance(value, str) and value.strip():
            identifiers.append(value.strip())
        elif isinstance(value, int):
            identifiers.append(str(value))
    return identifiers


def _collect_text_blobs(payload: JSONObject) -> list[dict[str, str]]:
    blobs: list[dict[str, str]] = []
    for field_name in _TEXT_FIELD_PRIORITY:
        value = payload.get(field_name)
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if normalized:
            blobs.append({"field": field_name, "text": normalized})
    if blobs:
        return blobs
    flattened = _flatten_text_values(payload.values())
    return [{"field": "flattened", "text": value} for value in flattened]


def _flatten_text_values(values: Iterable[JSONValue]) -> list[str]:
    flattened: list[str] = []
    for value in values:
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                flattened.append(normalized)
            continue
        if isinstance(value, list | tuple):
            flattened.extend(_flatten_text_values(value))
            continue
        if isinstance(value, dict):
            flattened.extend(_flatten_text_values(list(value.values())))
    return flattened


def _normalize_hgvs(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    for pattern in (_CDNA_HGVS_PATTERN, _PROTEIN_HGVS_PATTERN, _GENOMIC_HGVS_PATTERN):
        match = pattern.fullmatch(normalized)
        if match is not None:
            return match.group(0)
    return None


def _normalize_transcript(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    match = _TRANSCRIPT_PATTERN.fullmatch(normalized)
    if match is None:
        return None
    return match.group(0)


def _extract_phenotype_spans(window_text: str) -> list[JSONObject]:
    spans: list[JSONObject] = []
    seen: set[str] = set()
    lowered = window_text.lower()
    for trigger in _PHENOTYPE_TRIGGER_WORDS:
        if trigger not in lowered:
            continue
        sentence = _extract_sentence_for_keyword(window_text, trigger)
        if sentence is None:
            continue
        normalized_sentence = sentence.strip()
        if not normalized_sentence or normalized_sentence in seen:
            continue
        seen.add(normalized_sentence)
        spans.append({"text": normalized_sentence, "trigger": trigger})
    return spans


def _extract_sentence_for_keyword(text: str, keyword: str) -> str | None:
    lowered = text.lower()
    index = lowered.find(keyword.lower())
    if index < 0:
        return None
    start = max(text.rfind(".", 0, index), text.rfind("\n", 0, index))
    end_period = text.find(".", index)
    end_newline = text.find("\n", index)
    endpoints = [value for value in (end_period, end_newline) if value >= 0]
    end = min(endpoints) if endpoints else len(text)
    return text[(start + 1 if start >= 0 else 0) : end].strip()


def _surrounding_text(text: str, start: int, end: int, *, radius: int = 220) -> str:
    lower = max(start - radius, 0)
    upper = min(end + radius, len(text))
    return text[lower:upper].strip()


def _truncate_text(text: str, *, limit: int = 500) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return f"{stripped[: limit - 3]}..."


def _first_non_empty_excerpt(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "structured_source_record"
    return _truncate_text(stripped)


def _extract_first_label(
    text: str,
    patterns: tuple[tuple[str, re.Pattern[str]], ...],
) -> str | None:
    for label, pattern in patterns:
        if pattern.search(text):
            return label
    return None


def _first_match(
    pattern: re.Pattern[str],
    text: str,
    *,
    group: str | int = 0,
) -> str | None:
    match = pattern.search(text)
    if match is None:
        return None
    value = match.group(group)
    return value.strip() if isinstance(value, str) else None


def _build_locator(
    *,
    match_start: int | None,
    match_end: int | None,
    genome_build: str | None,
) -> str:
    if match_start is None or match_end is None:
        return "structured_record"
    if genome_build is None:
        return f"text_span:{match_start}-{match_end}"
    return f"text_span:{match_start}-{match_end}:{genome_build}"


def _read_scalar(payload: JSONObject, *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int):
            return str(value)
    return None


class ArtanaExtractionAdapter:
    """Fail-closed extraction adapter until the LLM runtime is service-local."""

    async def extract(self, context: ExtractionContext) -> ExtractionContract:
        """Return a fallback contract when the extraction runtime is unavailable."""
        return ExtractionContract(
            decision="fallback",
            confidence_score=0.0,
            rationale="Variant-aware extraction runtime is not available in this service.",
            evidence=[],
            source_type=context.source_type,
            document_id=context.document_id,
            entities=[],
            observations=[],
            relations=[],
            rejected_facts=[],
            pipeline_payloads=[],
            shadow_mode=context.shadow_mode,
            agent_run_id=None,
        )

    async def close(self) -> None:
        """No-op close hook for interface compatibility."""
        return


__all__ = [
    "ArtanaExtractionAdapter",
    "ExtractionContext",
    "build_genomics_signal_bundle",
]
