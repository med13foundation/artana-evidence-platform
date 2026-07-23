"""Mechanically select the first eight eligible events from the frozen reserve."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from scripts.validation.public_gold.bionlp_cg_adapter import (
    Document,
    Event,
    TextBound,
    load_development_directory,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.contracts import (
    ArtanaEntityType,
    ArtanaEventType,
    ConsideredEvent,
    DirectCGArgument,
    DirectCGEvent,
    DirectCGParticipant,
    ExactSourceSpan,
    FreshCGCase,
    FreshCGSelection,
    SkippedDocument,
)
from scripts.validation.public_gold.staged_event.generalization.span_identity import (
    token_bounded_spans,
)
from scripts.validation.source_general_claim_verification.hashing import (
    canonical_sha256,
)

RESERVE_ORDER = (
    "PMID-3287150",
    "PMID-18165897",
    "PMID-21963494",
    "PMID-2681013",
    "PMID-16098727",
    "PMID-7904970",
    "PMID-19648108",
    "PMID-11306510",
    "PMID-18841154",
    "PMID-15268651",
    "PMID-20448329",
    "PMID-15967832",
)
TARGET_CASE_COUNT = 8
EVENT_TYPE_MAP: dict[str, ArtanaEventType] = {
    "Regulation": "REGULATION",
    "Positive_regulation": "POSITIVE_REGULATION",
    "Negative_regulation": "NEGATIVE_REGULATION",
    "Gene_expression": "GENE_EXPRESSION",
}
ENTITY_TYPE_MAP: dict[str, ArtanaEntityType] = {
    "Cancer": "CANCER",
    "Simple_chemical": "SIMPLE_CHEMICAL",
    "Gene_or_gene_product": "GENE_OR_PROTEIN",
}
_CORE_ROLE = re.compile(r"^(Theme|Cause)\d*$")
_PRONOMINAL_MENTIONS = frozenset(
    {
        "he",
        "her",
        "hers",
        "him",
        "his",
        "it",
        "its",
        "itself",
        "she",
        "their",
        "theirs",
        "them",
        "themselves",
        "they",
        "this",
        "these",
        "those",
        "we",
        "which",
    }
)
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")


@dataclass(frozen=True, slots=True)
class _SelectionMetadata:
    case_order: int
    decisions: tuple[ConsideredEvent, ...]


def build_selection(development_path: Path) -> FreshCGSelection:
    """Select without model data and stop interpreting documents at eight cases."""

    documents = {
        document.document_id: document
        for document in load_development_directory(development_path)
    }
    cases: list[FreshCGCase] = []
    skipped: list[SkippedDocument] = []
    for document_id in RESERVE_ORDER:
        if len(cases) == TARGET_CASE_COUNT:
            break
        document = documents.get(document_id)
        if document is None:
            raise ValueError(f"reserved CG document is absent: {document_id}")
        case, decisions = _select_document(
            development_path,
            document,
            case_order=len(cases) + 1,
        )
        if case is None:
            skipped.append(
                SkippedDocument(
                    document_id=document_id,
                    reason="NO_ELIGIBLE_EVENT",
                    considered_events=decisions,
                )
            )
        else:
            cases.append(case)
    if len(cases) != TARGET_CASE_COUNT:
        raise ValueError("frozen reserve does not contain eight eligible cases")
    selected_ids = tuple(case.document_id for case in cases)
    unused_ids = tuple(item for item in RESERVE_ORDER if item not in selected_ids)
    return FreshCGSelection(
        reserve_order=RESERVE_ORDER,
        selected_document_ids=selected_ids,
        unused_document_ids=unused_ids,
        skipped_documents=tuple(skipped),
        cases=tuple(cases),
        provider_packet_excludes=(
            "direct CG annotations",
            "expected event and entity types",
            "expected Theme and Cause roles",
            "Artana source-semantic references",
            "expected counts",
            "benchmark projections",
            "reviewer artifacts",
            "historical model outputs",
        ),
    )


def load_frozen_selection(path: Path) -> FreshCGSelection:
    """Load and independently verify a self-contained frozen selection."""

    selection = FreshCGSelection.model_validate_json(path.read_text(encoding="utf-8"))
    for case in selection.cases:
        source_bytes = base64.b64decode(case.source_bytes_base64, validate=True)
        if source_bytes.decode(case.source_encoding) != case.source_text:
            raise ValueError(f"frozen source bytes differ from text: {case.case_id}")
        if hashlib.sha256(source_bytes).hexdigest() != case.source_sha256:
            raise ValueError(f"frozen source hash mismatch: {case.case_id}")
        _verify_exact_span(case.source_text, case.permitted_context, case.case_id)
        _verify_exact_span(case.source_text, case.event.trigger, case.case_id)
        if not _is_frozen_token_span(case.source_text, case.event.trigger):
            raise ValueError(f"frozen event mention splits a token: {case.case_id}")
        for participant in case.participants:
            _verify_exact_span(case.source_text, participant.mention, case.case_id)
            if not _is_frozen_token_span(case.source_text, participant.mention):
                raise ValueError(
                    f"frozen participant mention splits a token: {case.case_id}"
                )
        participant_ids = {item.annotation_id for item in case.participants}
        argument_ids = {
            item.target_annotation_id for item in case.event.arguments
        }
        if participant_ids != argument_ids:
            raise ValueError(f"direct CG argument coverage changed: {case.case_id}")
        reference_payload = {
            "document_id": case.document_id,
            "event": case.event,
            "participants": case.participants,
        }
        if canonical_sha256(reference_payload) != case.direct_cg_reference_sha256:
            raise ValueError(f"direct CG reference hash mismatch: {case.case_id}")
    return selection


def write_selection(path: Path, development_path: Path) -> None:
    """Write the deterministic create-once selection artifact."""

    selection = build_selection(development_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(selection.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _verify_exact_span(
    source: str,
    span: ExactSourceSpan,
    case_id: str,
) -> None:
    if source[span.start : span.end] != span.text:
        raise ValueError(f"frozen exact span mismatch: {case_id}")


def _select_document(
    development_path: Path,
    document: Document,
    *,
    case_order: int,
) -> tuple[FreshCGCase | None, tuple[ConsideredEvent, ...]]:
    mentions = {
        mention.annotation_id: mention
        for mention in (*document.entities, *document.triggers)
    }
    event_ids = {event.event_id for event in document.events}
    ordered_events = sorted(
        document.events,
        key=lambda item: (mentions[item.trigger_id].start, _numeric_id(item.event_id)),
    )
    decisions: list[ConsideredEvent] = []
    for event in ordered_events:
        trigger = mentions[event.trigger_id]
        reasons = _eligibility_reasons(document, event, mentions, event_ids)
        if reasons:
            decisions.append(
                ConsideredEvent(
                    event_id=event.event_id,
                    trigger_start=trigger.start,
                    disposition="INELIGIBLE",
                    reasons=reasons,
                )
            )
            continue
        decisions.append(
            ConsideredEvent(
                event_id=event.event_id,
                trigger_start=trigger.start,
                disposition="SELECTED",
                reasons=("FIRST_ELIGIBLE",),
            )
        )
        return (
            _case(
                development_path,
                document,
                event,
                mentions,
                metadata=_SelectionMetadata(case_order, tuple(decisions)),
            ),
            tuple(decisions),
        )
    return None, tuple(decisions)


def _eligibility_reasons(
    document: Document,
    event: Event,
    mentions: dict[str, TextBound],
    event_ids: set[str],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if event.event_type not in EVENT_TYPE_MAP:
        reasons.append("UNREPRESENTABLE_EVENT_TYPE")
    if not event.arguments:
        reasons.append("NO_CORE_ARGUMENT")
    if any(not _CORE_ROLE.fullmatch(argument.role) for argument in event.arguments):
        reasons.append("UNSUPPORTED_CORE_ARGUMENT_ROLE")
    if any(argument.target_id in event_ids for argument in event.arguments):
        reasons.append("NESTED_CORE_ARGUMENT")
    targets = tuple(mentions.get(argument.target_id) for argument in event.arguments)
    if any(
        target is None or target.annotation_type not in ENTITY_TYPE_MAP
        for target in targets
    ):
        reasons.append("UNREPRESENTABLE_DIRECT_ENTITY_TYPE")
    concrete_targets = tuple(target for target in targets if target is not None)
    if any(_is_pronominal(target.text) for target in concrete_targets):
        reasons.append("UNRESOLVED_PRONOMINAL_COREFERENCE")
    trigger = mentions[event.trigger_id]
    if not _is_exact_token_span(document.text, trigger):
        reasons.append("OCCURRENCE_V2_TRIGGER_NOT_TOKEN_BOUNDED")
    if any(
        not _is_exact_token_span(document.text, target)
        for target in concrete_targets
    ):
        reasons.append("OCCURRENCE_V2_ARGUMENT_NOT_TOKEN_BOUNDED")
    if not reasons:
        context = _permitted_context(document.text, trigger, concrete_targets)
        if any(
            target.start < context.start or target.end > context.end
            for target in concrete_targets
        ):
            reasons.append("CORE_ARGUMENT_OUTSIDE_PERMITTED_CONTEXT")
    return tuple(dict.fromkeys(reasons))


def _case(
    development_path: Path,
    document: Document,
    event: Event,
    mentions: dict[str, TextBound],
    *,
    metadata: _SelectionMetadata,
) -> FreshCGCase:
    source_path = development_path / f"{document.document_id}.txt"
    a1_path = source_path.with_suffix(".a1")
    a2_path = source_path.with_suffix(".a2")
    source_bytes = source_path.read_bytes()
    if source_bytes.decode("utf-8") != document.text:
        raise ValueError(f"source bytes changed during selection: {document.document_id}")
    trigger = mentions[event.trigger_id]
    participants = tuple(mentions[item.target_id] for item in event.arguments)
    direct_participants = tuple(
        DirectCGParticipant(
            annotation_id=participant.annotation_id,
            source_entity_type=participant.annotation_type,
            artana_entity_type=ENTITY_TYPE_MAP[participant.annotation_type],
            mention=_span(participant),
        )
        for participant in _unique_mentions(participants)
    )
    direct_event = DirectCGEvent(
        event_id=event.event_id,
        source_event_type=event.event_type,
        artana_event_type=EVENT_TYPE_MAP[event.event_type],
        trigger_annotation_id=event.trigger_id,
        trigger=_span(trigger),
        arguments=tuple(
            DirectCGArgument(
                source_role=argument.role,
                target_annotation_id=argument.target_id,
            )
            for argument in event.arguments
        ),
    )
    reference_payload = {
        "document_id": document.document_id,
        "event": direct_event,
        "participants": direct_participants,
    }
    return FreshCGCase(
        case_id=f"fresh-cg-{document.document_id.lower()}-{event.event_id.lower()}",
        case_order=metadata.case_order,
        document_id=document.document_id,
        source_text=document.text,
        source_bytes_base64=base64.b64encode(source_bytes).decode("ascii"),
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        a1_sha256=_file_sha256(a1_path),
        a2_sha256=_file_sha256(a2_path),
        annotation_source_sha256=_annotation_sha256(a1_path, a2_path),
        permitted_context=_permitted_context(document.text, trigger, participants),
        event=direct_event,
        participants=direct_participants,
        considered_events=metadata.decisions,
        selection_reason=(
            "FIRST_OFFSET_ORDER_EVENT_MEETING_ALL_FROZEN_ELIGIBILITY_RULES"
        ),
        direct_cg_reference_sha256=canonical_sha256(reference_payload),
    )


def _permitted_context(
    source: str,
    trigger: TextBound,
    participants: Iterable[TextBound],
) -> ExactSourceSpan:
    mentions = (trigger, *tuple(participants))
    left = min(item.start for item in mentions)
    right = max(item.end for item in mentions)
    boundaries = tuple(match.end() for match in _SENTENCE_END.finditer(source))
    context_start = max((item for item in boundaries if item <= left), default=0)
    while context_start < len(source) and source[context_start].isspace():
        context_start += 1
    context_end = next((item for item in boundaries if item >= right), len(source))
    return ExactSourceSpan(
        start=context_start,
        end=context_end,
        text=source[context_start:context_end],
    )


def _span(mention: TextBound) -> ExactSourceSpan:
    return ExactSourceSpan(
        start=mention.start,
        end=mention.end,
        text=mention.text,
    )


def _unique_mentions(mentions: Iterable[TextBound]) -> tuple[TextBound, ...]:
    result: list[TextBound] = []
    seen: set[str] = set()
    for mention in mentions:
        if mention.annotation_id not in seen:
            seen.add(mention.annotation_id)
            result.append(mention)
    return tuple(result)


def _is_pronominal(text: str) -> bool:
    normalized = re.sub(r"[^a-z]+", " ", text.lower()).strip()
    return normalized in _PRONOMINAL_MENTIONS


def _is_exact_token_span(source: str, mention: TextBound) -> bool:
    candidates = token_bounded_spans(
        source=source,
        scope_start=0,
        scope_end=len(source),
        exact_text=mention.text,
    )
    return any(
        item.start == mention.start and item.end == mention.end for item in candidates
    )


def _is_frozen_token_span(source: str, mention: ExactSourceSpan) -> bool:
    candidates = token_bounded_spans(
        source=source,
        scope_start=0,
        scope_end=len(source),
        exact_text=mention.text,
    )
    return any(
        item.start == mention.start and item.end == mention.end for item in candidates
    )


def _numeric_id(value: str) -> int:
    return int(value[1:])


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _annotation_sha256(a1_path: Path, a2_path: Path) -> str:
    payload = {
        "a1": a1_path.read_text(encoding="utf-8"),
        "a2": a2_path.read_text(encoding="utf-8"),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "ENTITY_TYPE_MAP",
    "EVENT_TYPE_MAP",
    "RESERVE_ORDER",
    "TARGET_CASE_COUNT",
    "build_selection",
    "load_frozen_selection",
    "write_selection",
]
