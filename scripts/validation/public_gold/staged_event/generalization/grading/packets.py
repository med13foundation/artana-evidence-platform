"""Build sealed source-only packets without generator output or evaluator labels."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Literal

from scripts.validation.public_gold.staged_event.generalization.panel import (
    GeneralizationCase,
    build_panel,
)


@dataclass(frozen=True, slots=True)
class BlindedCasePacket:
    case_id: str
    family: str
    source_id: str
    source_sha256: str
    context_start: int
    context_end: int
    local_context: str
    focus_start: int
    focus_end: int
    focus_passage: str
    primary_source_urls: tuple[str, ...]
    production_output_included: Literal[False] = False
    benchmark_labels_included: Literal[False] = False
    frozen_core_reference_included: Literal[False] = False


@dataclass(frozen=True, slots=True)
class BlindedPacketSet:
    schema_version: Literal["artana.staged_generalization.blinded_context_packets.v1"]
    instructions: str
    cases: tuple[BlindedCasePacket, ...]
    packet_sha256: str


INSTRUCTIONS = """You are an independent source grader. Review only the supplied exposed source
context and primary-source URLs. Do not inspect Artana output, the frozen core
reference, expected event counts, benchmark labels, or another grader's answer.

Enumerate only additional participant nodes that a scientifically faithful graph may
include beyond the focus event's indispensable population, comparator, outcome,
exposure, or causal core. Classify each as PERMITTED_CONTEXT,
AMBIGUOUS_REVIEW_ONLY, or FORBIDDEN. Every judgment must name exact source text,
the participant entity type, the focus-event argument role, and a concise rationale.

PERMITTED_CONTEXT must be explicit, correctly typed, nonduplicative in scientific
meaning, useful to interpreting the focus event, and attachable through the named
role without changing the source claim. Procedural or neighboring-event material is
not context merely because it appears in the paragraph. Mark uncertain cases
AMBIGUOUS_REVIEW_ONLY. Set inventory_complete only after considering the full packet.
"""


def build_blinded_packets() -> BlindedPacketSet:
    cases = tuple(_case_packet(case) for case in build_panel())
    payload = {
        "schema_version": "artana.staged_generalization.blinded_context_packets.v1",
        "instructions": INSTRUCTIONS,
        "cases": [asdict(case) for case in cases],
    }
    packet_sha256 = _canonical_sha256(payload)
    return BlindedPacketSet(
        schema_version="artana.staged_generalization.blinded_context_packets.v1",
        instructions=INSTRUCTIONS,
        cases=cases,
        packet_sha256=packet_sha256,
    )


def packet_json() -> dict[str, object]:
    packet_set = build_blinded_packets()
    return asdict(packet_set)


def _case_packet(case: GeneralizationCase) -> BlindedCasePacket:
    return BlindedCasePacket(
        case_id=case.case_id,
        family=case.family,
        source_id=case.source_id,
        source_sha256=case.source_sha256,
        context_start=case.context_start,
        context_end=case.context_end,
        local_context=case.local_context,
        focus_start=case.focus_start,
        focus_end=case.focus_end,
        focus_passage=case.focus_passage,
        primary_source_urls=_primary_source_urls(case.source_id),
    )


def _primary_source_urls(source_id: str) -> tuple[str, ...]:
    pmid_by_source = {
        "exposed-gold-40289860": "40289860",
        "exposed-human-genetics": "42454948",
        "PMID-21965773": "21965773",
        "PMID-7966592": "7966592",
    }
    pmid = pmid_by_source[source_id]
    return (
        f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            f"?db=pubmed&id={pmid}&rettype=abstract&retmode=xml"
        ),
    )


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "INSTRUCTIONS",
    "BlindedCasePacket",
    "BlindedPacketSet",
    "build_blinded_packets",
    "packet_json",
]
