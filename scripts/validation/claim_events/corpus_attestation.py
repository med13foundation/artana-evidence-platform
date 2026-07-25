"""Corpus attestation: distinguish out-of-scope truth from hallucination.

The frozen panel keeps 53 of 472 corpus events, so a prediction absent from
gold is ambiguous: it may be a real annotation the importer filtered out, or it
may be invented.  Precision computed against gold alone cannot tell those apart
-- measured directly, a corpus-faithful extractor and a pure hallucinator both
score 0.1920.

This module resolves that with an attestation index: an opaque digest for every
event the corpus annotates.  A prediction is then one of three things.

- matches gold                     -> correct, in scope
- attested but not gold            -> correct, out of scope; must not be penalised
- neither                          -> unattested; a real false positive

The index stores digests only.  It deliberately carries no trigger text, no
offsets, and no argument spans, so the repository never republishes annotation
content whose copyright belongs to the shared-task organisers.  Membership can
be checked; the annotations cannot be reconstructed.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path

INDEX_SCHEMA_VERSION = "artana.claim_events.corpus_attestation.v1"


def event_digest(
    *,
    document_id: str,
    trigger_span: str,
    trigger_source_start: int,
    argument_spans: Iterable[str],
) -> str:
    """Digest one event identity, corpus side and prediction side alike."""

    parts = [
        document_id,
        trigger_span,
        str(trigger_source_start),
        *sorted(argument_spans),
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def argument_span_key(exact_span: str, source_start: object) -> str:
    """Build one argument component of an event digest."""

    return f"{exact_span}|{source_start}"


def prediction_digest(document_id: str, event: Mapping[str, object]) -> str:
    """Digest a predicted event using the same identity as the corpus side."""

    arguments = event.get("arguments")
    spans: list[str] = []
    if isinstance(arguments, list):
        spans.extend(
            argument_span_key(
                str(argument.get("exact_span", "")),
                argument.get("source_start"),
            )
            for argument in arguments
            if isinstance(argument, Mapping)
        )
    start = event.get("trigger_source_start")
    return event_digest(
        document_id=document_id,
        trigger_span=str(event.get("trigger_span", "")),
        trigger_source_start=int(start) if isinstance(start, int) else 0,
        argument_spans=spans,
    )


def build_index(corpus: Path, document_ids: Iterable[str]) -> dict[str, object]:
    """Build the attestation index for the selected corpus documents.

    Offsets come from `load_standoff_document`, the importer's own loader, so
    they carry the same CRLF and whitespace normalisation the gold records do.
    Reading the raw `.a1`/`.a2` offsets instead silently misses roughly a third
    of gold events, because normalisation re-indexes every annotation.
    """

    from scripts.validation.claim_events.bionlp_import import load_standoff_document

    digests: set[str] = set()
    counted = 0
    identifiers = list(document_ids)
    for document_id in identifiers:
        document = load_standoff_document(corpus, document_id)
        for event in document.events:
            trigger = document.text_bounds.get(event.trigger_id)
            if trigger is None:
                continue
            spans = [
                argument_span_key(
                    document.text_bounds[argument.reference_id].text,
                    document.text_bounds[argument.reference_id].start,
                )
                for argument in event.arguments
                if argument.reference_id in document.text_bounds
            ]
            digests.add(
                event_digest(
                    document_id=document_id,
                    trigger_span=trigger.text,
                    trigger_source_start=trigger.start,
                    argument_spans=spans,
                ),
            )
            counted += 1
    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "corpus": "BioNLP-ST-2011-GE",
        "corpus_archive_sha256": (
            "f70e5f6d6e2a7f7fcdb5c8671715f3909a77662a6238015b2916ce939f2a890f"
        ),
        "document_count": len(identifiers),
        "corpus_event_count": counted,
        "digest_count": len(digests),
        "digests": sorted(digests),
    }


def classify_predictions(
    *,
    document_id: str,
    predictions: Iterable[Mapping[str, object]],
    gold_matched: Iterable[bool],
    attested: frozenset[str],
) -> tuple[int, int, int]:
    """Split predictions into (gold matches, attested-only, unattested).

    `attested-only` predictions are real corpus annotations the importer
    filtered out.  They earn no credit, because they are not in gold, but they
    must not count as false positives either -- penalising them is what makes
    the current precision gate unpassable for a faithful extractor.

    Note the digest deliberately omits the event type.  Attestation answers
    "does the corpus annotate an event with this trigger and these arguments
    here?", which is a question about structure rather than label.  A predicted
    event with the right structure and the wrong type therefore earns no credit
    and takes no penalty, instead of being scored as an invention.
    """

    matches = attested_only = unattested = 0
    for event, matched in zip(predictions, gold_matched, strict=True):
        if matched:
            matches += 1
        elif prediction_digest(document_id, event) in attested:
            attested_only += 1
        else:
            unattested += 1
    return matches, attested_only, unattested


def scope_aware_precision(
    *,
    matches: int,
    unattested: int,
) -> float | None:
    """Precision over in-scope decisions only.

    Attested-but-out-of-scope predictions are excluded from the denominator, so
    the metric measures how often the extractor invents an event rather than
    how closely it reproduces the importer's filter.
    """

    denominator = matches + unattested
    return None if denominator == 0 else matches / denominator


def load_index(path: Path) -> frozenset[str]:
    """Load an attestation index as a membership set."""

    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("schema_version") != INDEX_SCHEMA_VERSION:
        raise ValueError("unexpected corpus attestation index schema")
    digests = record.get("digests")
    if not isinstance(digests, list):
        raise TypeError("corpus attestation index has no digests")
    return frozenset(str(digest) for digest in digests)


__all__ = [
    "INDEX_SCHEMA_VERSION",
    "argument_span_key",
    "build_index",
    "event_digest",
    "load_index",
    "prediction_digest",
]
