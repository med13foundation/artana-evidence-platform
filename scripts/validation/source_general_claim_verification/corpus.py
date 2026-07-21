"""Load and validate a self-contained, exposed-only corpus and its packets."""

from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.validation.source_general_claim_verification.contracts import (
    CorpusArtifact,
    ExactSpan,
    FrozenPacketSet,
    FrozenReferencePacket,
    ReviewerPacket,
    ReviewerPacketBatch,
    TiebreakerPacketBatch,
)
from scripts.validation.source_general_claim_verification.hashing import (
    canonical_sha256,
)

DEFAULT_CORPUS_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "exposed_31_scope_corpus.json"
)
MAX_UNRESOLVED_RATE = 0.20


def load_corpus(path: Path = DEFAULT_CORPUS_PATH) -> CorpusArtifact:
    """Load only caller-selected local bytes; this function has no network path."""

    if path.suffix != ".json":
        raise ValueError("exposed corpus must be a JSON artifact")
    corpus = CorpusArtifact.model_validate_json(path.read_text(encoding="utf-8"))
    validate_corpus(corpus)
    return corpus


def validate_corpus(corpus: CorpusArtifact) -> None:
    """Verify hashes, exact spans, and one-to-one identity for all 31 scopes."""

    sources = {source.source_id: source for source in corpus.sources}
    if len(sources) != len(corpus.sources):
        raise ValueError("corpus source IDs must be unique")
    for source in corpus.sources:
        digest = hashlib.sha256(source.text.encode("utf-8")).hexdigest()
        if digest != source.source_sha256:
            raise ValueError(f"source hash mismatch: {source.source_id}")

    scope_ids = {scope.scope_id for scope in corpus.scopes}
    if len(scope_ids) != len(corpus.scopes):
        raise ValueError("corpus scope IDs must be unique")
    for scope in corpus.scopes:
        scope_source = sources.get(scope.source_id)
        if scope_source is None:
            raise ValueError(f"scope references missing source: {scope.scope_id}")
        if scope.source_sha256 != scope_source.source_sha256:
            raise ValueError(f"scope source hash mismatch: {scope.scope_id}")
        _validate_exact_span(scope.scope, scope_source.text, label=scope.scope_id)


def validate_packet_batch(
    batch: ReviewerPacketBatch,
    corpus: CorpusArtifact,
) -> None:
    """Bind one blinded review batch to every frozen exposed scope."""

    validate_corpus(corpus)
    if batch.corpus_sha256 != canonical_sha256(corpus):
        raise ValueError("review batch corpus hash does not match corpus")
    if any(packet.reviewer != batch.reviewer for packet in batch.packets):
        raise ValueError("every packet must use the batch reviewer identity")
    packets = {packet.scope_id: packet for packet in batch.packets}
    if len(packets) != len(batch.packets):
        raise ValueError("review batch scope IDs must be unique")
    expected = {scope.scope_id for scope in corpus.scopes}
    if set(packets) != expected:
        raise ValueError("review batch must cover all 31 corpus scopes exactly once")
    scopes = {scope.scope_id: scope for scope in corpus.scopes}
    sources = {source.source_id: source for source in corpus.sources}
    for packet in batch.packets:
        _validate_packet(
            packet, scopes[packet.scope_id], sources[packet.source_id].text
        )


def validate_reference_set(
    packet_set: FrozenPacketSet,
    corpus: CorpusArtifact,
) -> None:
    """Validate packet and set hashes without interpreting biomedical meaning."""

    validate_corpus(corpus)
    if packet_set.corpus_sha256 != canonical_sha256(corpus):
        raise ValueError("reference set corpus hash does not match corpus")
    packets = {packet.scope_id: packet for packet in packet_set.packets}
    if len(packets) != len(packet_set.packets):
        raise ValueError("reference packet scope IDs must be unique")
    expected = {scope.scope_id for scope in corpus.scopes}
    if set(packets) != expected:
        raise ValueError("reference set must cover all 31 corpus scopes exactly once")
    if not set(packet_set.unresolved_scope_ids).issubset(expected):
        raise ValueError("unresolved scope IDs must belong to the frozen corpus")
    if len(packet_set.unresolved_scope_ids) / len(corpus.scopes) > MAX_UNRESOLVED_RATE:
        raise ValueError("reference set exceeds the unresolved-disagreement ceiling")
    scopes = {scope.scope_id: scope for scope in corpus.scopes}
    sources = {source.source_id: source for source in corpus.sources}
    for packet in packet_set.packets:
        _validate_packet(
            packet, scopes[packet.scope_id], sources[packet.source_id].text
        )
        if packet.packet_sha256 != reference_packet_sha256(packet):
            raise ValueError(f"reference packet hash mismatch: {packet.scope_id}")
    if packet_set.packet_set_sha256 != reference_set_sha256(packet_set):
        raise ValueError("reference packet-set hash mismatch")
    eligible_count = sum(
        packet.scope_id not in packet_set.unresolved_scope_ids
        and not packet.excluded_as_ambiguous
        for packet in packet_set.packets
    )
    if eligible_count == 0:
        raise ValueError("reference set must retain at least one eligible packet")


def validate_tiebreaker_batch(
    batch: TiebreakerPacketBatch,
    corpus: CorpusArtifact,
    *,
    permitted_scope_ids: frozenset[str],
) -> None:
    """Bind a third reviewer only to scopes disputed by the first two."""

    validate_corpus(corpus)
    if batch.corpus_sha256 != canonical_sha256(corpus):
        raise ValueError("tiebreaker batch corpus hash does not match corpus")
    if any(packet.reviewer != batch.reviewer for packet in batch.packets):
        raise ValueError("every tiebreaker packet must use the batch reviewer")
    packets = {packet.scope_id: packet for packet in batch.packets}
    if len(packets) != len(batch.packets):
        raise ValueError("tiebreaker scope IDs must be unique")
    if not set(packets).issubset(permitted_scope_ids):
        raise ValueError("tiebreaker may adjudicate only disputed scopes")
    scopes = {scope.scope_id: scope for scope in corpus.scopes}
    sources = {source.source_id: source for source in corpus.sources}
    for packet in batch.packets:
        if packet.scope_id not in scopes:
            raise ValueError(f"tiebreaker references unknown scope: {packet.scope_id}")
        source = sources.get(packet.source_id)
        if source is None:
            raise ValueError(
                f"tiebreaker references unknown source: {packet.source_id}"
            )
        _validate_packet(packet, scopes[packet.scope_id], source.text)


def reference_packet_sha256(packet: FrozenReferencePacket) -> str:
    return canonical_sha256(packet.model_dump(exclude={"packet_sha256"}, mode="json"))


def reference_set_sha256(packet_set: FrozenPacketSet) -> str:
    return canonical_sha256(
        packet_set.model_dump(exclude={"packet_set_sha256"}, mode="json"),
    )


def _validate_packet(
    packet: ReviewerPacket | FrozenReferencePacket,
    scope: object,
    source_text: str,
) -> None:
    from scripts.validation.source_general_claim_verification.contracts import (
        ExposedScope,
    )

    if not isinstance(scope, ExposedScope):
        raise TypeError("packet scope must be an ExposedScope")
    if packet.source_id != scope.source_id:
        raise ValueError(f"packet source mismatch: {packet.scope_id}")
    if packet.source_sha256 != scope.source_sha256:
        raise ValueError(f"packet source hash mismatch: {packet.scope_id}")
    if packet.atomic_scope != scope.scope:
        raise ValueError(f"packet atomic scope mismatch: {packet.scope_id}")
    spans = _packet_spans(packet)
    for label, span in spans:
        _validate_exact_span(span, source_text, label=f"{packet.scope_id}.{label}")
        if span.start < scope.scope.start or span.end > scope.scope.end:
            raise ValueError(
                f"packet evidence escapes atomic scope: {packet.scope_id}.{label}"
            )


def _packet_spans(
    packet: ReviewerPacket | FrozenReferencePacket,
) -> tuple[tuple[str, ExactSpan], ...]:
    spans: list[tuple[str, ExactSpan]] = [
        ("event", packet.claim.event_evidence),
        ("direction", packet.claim.direction_evidence),
        ("comparison", packet.claim.comparison_evidence),
        ("polarity", packet.claim.polarity_evidence),
        ("uncertainty", packet.claim.uncertainty_evidence),
    ]
    spans.extend(
        (f"participant.{participant.participant_id}", participant.evidence)
        for participant in packet.claim.participants
    )
    spans.extend(
        (f"quantity.{index}", quantity.evidence)
        for index, quantity in enumerate(packet.claim.quantitative_evidence)
    )
    statistical = packet.claim.statistical_evidence
    if statistical.observation_evidence is not None:
        spans.append(("statistical_observation", statistical.observation_evidence))
    if statistical.author_interpretation_evidence is not None:
        spans.append(
            (
                "author_statistical_interpretation",
                statistical.author_interpretation_evidence,
            ),
        )
    spans.extend(
        (f"modifier.{index}", modifier.evidence)
        for index, modifier in enumerate(packet.claim.required_modifiers)
    )
    spans.extend(
        (f"acceptable_equivalent.{index}", span)
        for index, span in enumerate(packet.acceptable_equivalent_evidence)
    )
    spans.extend(
        (f"ambiguity.{index}", condition.evidence)
        for index, condition in enumerate(packet.ambiguity_or_abstention_conditions)
        if condition.evidence is not None
    )
    return tuple(spans)


def _validate_exact_span(span: ExactSpan, source_text: str, *, label: str) -> None:
    if span.end > len(source_text):
        raise ValueError(f"span is outside source: {label}")
    if source_text[span.start : span.end] != span.text:
        raise ValueError(f"span text does not match source offsets: {label}")


__all__ = [
    "DEFAULT_CORPUS_PATH",
    "load_corpus",
    "reference_packet_sha256",
    "reference_set_sha256",
    "validate_corpus",
    "validate_packet_batch",
    "validate_reference_set",
    "validate_tiebreaker_batch",
]
