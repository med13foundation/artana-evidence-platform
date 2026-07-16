"""Exact source binding for qualified claim frames."""

from __future__ import annotations

import re
from collections.abc import Sequence

from artana_evidence_api.document_extraction_support.claim_frames.contracts import (
    ClaimFrame,
    ClaimQualifier,
    EpistemicStatus,
    Polarity,
    QualifierState,
)
from artana_evidence_api.variant_extraction_contracts import (
    source_contains_exact_measurement_literal,
)


class ClaimFrameNormalizationError(ValueError):
    """Raised when a frame cannot be bound exactly to one source chunk."""


_QUALIFIER_FIELDS: tuple[str, ...] = (
    "biological_or_variant_state",
    "condition",
    "population",
    "intervention",
    "comparator",
    "outcome",
    "study_design",
    "treatment_setting",
    "timeframe",
    "threshold",
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MATERIAL_STATE_TOKEN_RE = re.compile(
    r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9]+$|"
    r"^(?=.*\d)[A-Za-z0-9]+-(?:mutant|negative|positive)$|"
    r"^(?:amplified|amplification|deleted|deletion|deficient|expression|fusion|"
    r"high|low|loss|mutant|mutated|negative|overexpressed|positive|variant)$",
    re.IGNORECASE,
)
_NON_SUPPORT_CUES: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\bnot\s+(?:statistically\s+|significantly\s+)?associated\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bno\s+(?:statistically\s+)?significant\b", re.IGNORECASE),
    re.compile(
        r"\bno\s+(?:association|difference|effect|evidence|response)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bdid\s+not\b", re.IGNORECASE),
    re.compile(r"\bfailed\s+to\b", re.IGNORECASE),
)
_NON_ASSERTIVE_CUES: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:hypothesi[sz]e|hypothesis|propose)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:may|might|could)\b", re.IGNORECASE),
)


def normalize_claim_frame(
    frame: ClaimFrame,
    chunk_text: str,
    *,
    chunk_locator: str | None = None,
    expected_source_hash: str | None = None,
) -> ClaimFrame:
    """Bind every source-bearing span in ``frame`` to ``chunk_text``.

    Matching is literal and unique. Whitespace normalization, case folding, and
    fuzzy matching are deliberately absent because they could bind an agent span
    to a different sentence or measurement.
    """
    if not isinstance(frame, ClaimFrame):
        raise ClaimFrameNormalizationError("frame must be a ClaimFrame")
    if not isinstance(chunk_text, str) or chunk_text == "":
        raise ClaimFrameNormalizationError("chunk_text must be nonempty source text")
    if chunk_locator is not None and chunk_locator != frame.source_locator:
        raise ClaimFrameNormalizationError(
            "chunk_locator does not match the frame source locator",
        )

    _require_unique_span(
        source_text=chunk_text,
        exact_span=frame.source_evidence.exact_span,
        label="source evidence",
    )
    _require_endpoint_grounding(frame)
    _require_semantic_consistency(frame)
    _bind_assertion_arguments(frame)
    for field in _QUALIFIER_FIELDS:
        qualifier = getattr(frame, field)
        _bind_qualifier(
            chunk_text=chunk_text,
            evidence_span=frame.source_evidence.exact_span,
            qualifier=qualifier,
            label=field,
        )
    _require_no_endpoint_role_duplication(frame)

    if frame.source_measurements and expected_source_hash is None:
        raise ClaimFrameNormalizationError(
            "source measurements require the expected source hash",
        )
    if (
        expected_source_hash is not None
        and _SHA256_RE.fullmatch(
            expected_source_hash,
        )
        is None
    ):
        raise ClaimFrameNormalizationError("expected_source_hash must be SHA-256")

    for index, measurement in enumerate(frame.source_measurements):
        if measurement.source_locator != frame.source_locator:
            raise ClaimFrameNormalizationError(
                f"source_measurements[{index}] has a different source locator",
            )
        if measurement.source_hash != expected_source_hash:
            raise ClaimFrameNormalizationError(
                f"source_measurements[{index}] has a different source hash",
            )
        _require_unique_span(
            source_text=chunk_text,
            exact_span=measurement.literal_span,
            label=f"source_measurements[{index}] literal_span",
        )
        if measurement.literal_span not in frame.source_evidence.exact_span:
            raise ClaimFrameNormalizationError(
                f"source_measurements[{index}] literal_span is outside the "
                "claim evidence span",
            )
        if not source_contains_exact_measurement_literal(
            source_text=chunk_text,
            literal_span=measurement.literal_span,
            unit=measurement.unit,
        ):
            raise ClaimFrameNormalizationError(
                f"source_measurements[{index}] literal_span is not an isolated "
                "source measurement",
            )
        if not _literal_span_matches_measurement(
            literal_span=measurement.literal_span,
            value=measurement.value,
            unit=measurement.unit,
        ):
            raise ClaimFrameNormalizationError(
                f"source_measurements[{index}] value and unit do not match "
                "literal_span",
            )

    return frame


def _bind_assertion_arguments(frame: ClaimFrame) -> None:
    for index, argument in enumerate(frame.assertion_arguments):
        _require_unique_span(
            source_text=frame.source_evidence.exact_span,
            exact_span=argument.exact_span,
            label=f"assertion_arguments[{index}] exact_span",
        )


def bind_claim_frame(
    frame: ClaimFrame,
    chunk_text: str,
    *,
    chunk_locator: str | None = None,
    expected_source_hash: str | None = None,
) -> ClaimFrame:
    """Explicitly named alias for the exact-binding normalization boundary."""
    return normalize_claim_frame(
        frame,
        chunk_text,
        chunk_locator=chunk_locator,
        expected_source_hash=expected_source_hash,
    )


def _bind_qualifier(
    *,
    chunk_text: str,
    evidence_span: str,
    qualifier: ClaimQualifier,
    label: str,
) -> None:
    if qualifier.state is not QualifierState.PRESENT:
        return
    if qualifier.value is None or qualifier.exact_span is None:
        raise ClaimFrameNormalizationError(f"{label} is missing present content")
    _require_unique_span(
        source_text=chunk_text,
        exact_span=qualifier.exact_span,
        label=f"{label} exact_span",
    )
    if qualifier.value not in qualifier.exact_span:
        raise ClaimFrameNormalizationError(
            f"{label} value is not contained in its exact_span",
        )
    if qualifier.exact_span not in evidence_span:
        raise ClaimFrameNormalizationError(
            f"{label} exact_span is outside the claim evidence span",
        )


def _require_endpoint_grounding(frame: ClaimFrame) -> None:
    evidence = frame.source_evidence.exact_span
    _require_source_native_endpoint(
        endpoint=frame.subject,
        evidence=evidence,
        biological_state=frame.biological_or_variant_state,
        label="subject",
    )
    _require_source_native_endpoint(
        endpoint=frame.object,
        evidence=evidence,
        biological_state=frame.biological_or_variant_state,
        label="object",
    )


def _require_source_native_endpoint(
    *,
    endpoint: str,
    evidence: str,
    biological_state: ClaimQualifier,
    label: str,
) -> None:
    """Require an exact endpoint and preserve adjacent material state tokens."""

    occurrences = tuple(_endpoint_occurrences(evidence=evidence, endpoint=endpoint))
    if not occurrences:
        raise ClaimFrameNormalizationError(
            f"source evidence must contain the exact claim {label}",
        )
    material_tokens = _adjacent_material_state_tokens(
        evidence=evidence,
        occurrences=occurrences,
    )
    if not material_tokens:
        return
    state_span = (
        biological_state.exact_span
        if biological_state.state is QualifierState.PRESENT
        else None
    )
    if state_span is None or not all(token in state_span for token in material_tokens):
        raise ClaimFrameNormalizationError(
            f"claim {label} omits adjacent material state; preserve it in the "
            "endpoint or biological_or_variant_state qualifier",
        )


def _endpoint_occurrences(*, evidence: str, endpoint: str) -> Sequence[re.Match[str]]:
    pattern = re.compile(
        rf"(?<![A-Za-z0-9]){re.escape(endpoint)}(?![A-Za-z0-9])",
    )
    return tuple(pattern.finditer(evidence))


def _adjacent_material_state_tokens(
    *,
    evidence: str,
    occurrences: Sequence[re.Match[str]],
) -> tuple[str, ...]:
    """Return variant-like tokens directly adjoining every endpoint occurrence."""

    tokens: list[str] = []
    for match in occurrences:
        before = evidence[: match.start()].rstrip()
        after_raw = evidence[match.end() :]
        after = after_raw.lstrip()
        neighboring = []
        if before:
            neighboring.append(re.split(r"\s+", before)[-1].strip("(),.;:"))
        if after:
            neighboring.append(re.split(r"\s+", after)[0].strip("(),.;:"))
        if after_raw.startswith("-"):
            neighboring.append(
                re.split(r"\s+", after_raw[1:])[0].strip("(),.;:"),
            )
        tokens.extend(
            token
            for token in neighboring
            if token and _MATERIAL_STATE_TOKEN_RE.fullmatch(token)
        )
    return tuple(dict.fromkeys(tokens))


def _require_no_endpoint_role_duplication(frame: ClaimFrame) -> None:
    """Reject exact endpoint copies in incompatible qualifier roles."""

    subject = frame.subject.casefold().strip()
    object_ = frame.object.casefold().strip()
    intervention = _present_value(frame.intervention)
    population = _present_value(frame.population)
    outcome = _present_value(frame.outcome)
    if intervention == subject:
        raise ClaimFrameNormalizationError(
            "intervention qualifier cannot duplicate the claim subject",
        )
    if population == object_:
        raise ClaimFrameNormalizationError(
            "population qualifier cannot duplicate the claim object",
        )
    if outcome == object_:
        raise ClaimFrameNormalizationError(
            "outcome qualifier cannot duplicate the claim object",
        )


def _present_value(qualifier: ClaimQualifier) -> str | None:
    if qualifier.state is not QualifierState.PRESENT or qualifier.value is None:
        return None
    return qualifier.value.casefold().strip()


def _require_semantic_consistency(frame: ClaimFrame) -> None:
    evidence = frame.source_evidence.exact_span
    if (
        frame.polarity is Polarity.SUPPORT
        and frame.epistemic_status is EpistemicStatus.ASSERTED
        and any(pattern.search(evidence) for pattern in _NON_SUPPORT_CUES)
    ):
        raise ClaimFrameNormalizationError(
            "positive asserted claim contradicts an explicit non-support cue",
        )
    if frame.epistemic_status is EpistemicStatus.ASSERTED and any(
        pattern.search(evidence) for pattern in _NON_ASSERTIVE_CUES
    ):
        raise ClaimFrameNormalizationError(
            "asserted claim contradicts an explicit non-assertive cue",
        )


def _require_unique_span(
    *,
    source_text: str,
    exact_span: str,
    label: str,
) -> None:
    occurrences = _find_exact_occurrences(source_text, exact_span)
    if len(occurrences) != 1:
        raise ClaimFrameNormalizationError(
            f"{label} must occur exactly once in the supplied chunk; "
            f"found {len(occurrences)} occurrences",
        )


def _find_exact_occurrences(source_text: str, exact_span: str) -> Sequence[int]:
    positions: list[int] = []
    start = 0
    while True:
        position = source_text.find(exact_span, start)
        if position < 0:
            return positions
        positions.append(position)
        start = position + 1


def _literal_span_matches_measurement(
    *,
    literal_span: str,
    value: str,
    unit: str,
) -> bool:
    normalized_unit = unit.strip().casefold()
    if normalized_unit in {"dimensionless", "ratio", "unitless"}:
        return literal_span == value
    unit_aliases: tuple[str, ...]
    if normalized_unit in {"percent", "percentage"}:
        unit_aliases = ("%", "percent", "percentage")
    elif normalized_unit == "usd":
        unit_aliases = ("$", "usd")
    elif normalized_unit == "eur":
        unit_aliases = ("€", "eur")
    elif normalized_unit == "gbp":
        unit_aliases = ("£", "gbp")
    elif normalized_unit == "jpy":
        unit_aliases = ("¥", "jpy")
    else:
        unit_aliases = (unit.strip(),)
    escaped_value = re.escape(value)
    return any(
        re.fullmatch(
            rf"{escaped_value}\s*{re.escape(alias)}",
            literal_span,
            re.IGNORECASE,
        )
        or re.fullmatch(
            rf"{re.escape(alias)}\s*{escaped_value}",
            literal_span,
            re.IGNORECASE,
        )
        for alias in unit_aliases
    )


__all__ = [
    "ClaimFrameNormalizationError",
    "bind_claim_frame",
    "normalize_claim_frame",
]
