"""Shared low-signal label detection for chase and follow-up generation."""

from __future__ import annotations

import re
from typing import Literal

LowSignalLabelReason = Literal[
    "generic_result_label",
    "clinical_significance_bucket",
    "accession_like_placeholder",
]

_LOW_SIGNAL_LABELS = frozenset(
    {
        "BENIGN",
        "BENIGN VARIANT",
        "BENIGN VARIANTS",
        "LIKELY BENIGN",
        "LIKELY BENIGN VARIANT",
        "LIKELY BENIGN VARIANTS",
        "LIKELY PATHOGENIC",
        "LIKELY PATHOGENIC VARIANT",
        "LIKELY PATHOGENIC VARIANTS",
        "PATHOGENIC",
        "PATHOGENIC VARIANT",
        "PATHOGENIC VARIANTS",
        "UNCERTAIN SIGNIFICANCE",
        "UNCERTAIN SIGNIFICANCE VARIANTS",
        "NOT PROVIDED",
        "UNSPECIFIED CONDITION",
    },
)
_LOW_SIGNAL_RESULT_PATTERN = re.compile(r"\bRESULT \d+\b")
_LOW_SIGNAL_ACCESSION_PATTERN = re.compile(r"^[A-Z]{2,}\d+[A-Z0-9]*[_-][A-Z0-9_-]+$")


def filtered_low_signal_label_reason(
    display_label: str,
) -> LowSignalLabelReason | None:
    """Return the shared low-signal reason for one label, when present."""

    normalized_label = " ".join(display_label.strip().upper().split())
    if normalized_label in _LOW_SIGNAL_LABELS:
        return "clinical_significance_bucket"
    if _LOW_SIGNAL_RESULT_PATTERN.search(normalized_label) is not None:
        return "generic_result_label"
    if (
        " " not in display_label
        and _LOW_SIGNAL_ACCESSION_PATTERN.fullmatch(normalized_label) is not None
    ):
        return "accession_like_placeholder"
    return None
