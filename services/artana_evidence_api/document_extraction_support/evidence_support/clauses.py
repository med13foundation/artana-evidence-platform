"""Clause segmentation for relation support and endpoint repair."""

from __future__ import annotations

import re

_RELATION_PREDICATE_PATTERN = (
    r"activat(?:e|es|ed|ing|ion)|associat(?:e|es|ed|ing|ion)|"
    r"bind(?:s|ing|bound)?|caus(?:e|es|ed|ing)|confer(?:s|red|ring)?|"
    r"correlat(?:e|es|ed|ing|ion)|increas(?:e|es|ed|ing)|"
    r"inhibit(?:s|ed|ing)?|link(?:s|ed|ing)?|predic(?:t|ts|ted|ting)|"
    r"protect(?:s|ed|ing)?|regulat(?:e|es|ed|ing|ion)|"
    r"sensitiz(?:e|es|ed|ing)|suppress(?:es|ed|ing)?|"
    r"target(?:s|ed|ing)?|treat(?:s|ed|ing|ment)?"
)
_NEW_CLAIM_LOOKAHEAD = (
    rf"(?=(?:and\s+)?(?:[A-Za-z0-9*./+-]+\s+){{0,6}}"
    rf"(?:{_RELATION_PREDICATE_PATTERN})\b)"
)
_CLAIM_BOUNDARY_RE = re.compile(
    rf"(?:"
    rf"[;:]|[.!?](?=\s|$)|"
    rf",\s*(?:and\s+)?{_NEW_CLAIM_LOOKAHEAD}|"
    rf"\band\s+{_NEW_CLAIM_LOOKAHEAD}|"
    rf"\b(?:although|because|but|however|whereas|while)\b"
    rf")",
    re.IGNORECASE,
)
_LEADING_RELATION_PREDICATE_RE = re.compile(
    rf"^(?:(?:is|are|was|were|has|have|had)\s+)?"
    rf"(?:{_RELATION_PREDICATE_PATTERN})\b",
    re.IGNORECASE,
)


def split_claim_clauses(
    sentence: str,
    *,
    inherited_subject: str | None = None,
) -> tuple[str, ...]:
    """Split independent biomedical claims without splitting coordinated objects."""

    clauses: list[str] = []
    start = 0
    inherited_for_clause: str | None = None
    for boundary in _CLAIM_BOUNDARY_RE.finditer(sentence):
        _append_clause(
            clauses=clauses,
            clause=sentence[start : boundary.start()],
            inherited_subject=inherited_for_clause,
        )
        start = boundary.end()
        inherited_for_clause = inherited_subject
    _append_clause(
        clauses=clauses,
        clause=sentence[start:],
        inherited_subject=inherited_for_clause,
    )
    return tuple(clauses)


def _append_clause(
    *,
    clauses: list[str],
    clause: str,
    inherited_subject: str | None,
) -> None:
    normalized = clause.strip(" ,")
    if normalized == "":
        return
    if (
        inherited_subject
        and clauses
        and _LEADING_RELATION_PREDICATE_RE.search(normalized) is not None
    ):
        normalized = f"{inherited_subject} {normalized}"
    clauses.append(normalized)


__all__ = ["split_claim_clauses"]
