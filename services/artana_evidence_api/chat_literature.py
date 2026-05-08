"""Helpers for optional literature refresh during graph-chat runs."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from artana_evidence_api.tool_catalog import RunPubMedSearchToolArgs
from artana_evidence_api.types.common import JSONObject  # noqa: TC001

if TYPE_CHECKING:
    from artana_evidence_api.graph_chat_runtime import GraphChatResult

_GENE_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9-]{2,20}$")
_NON_WORD_PATTERN = re.compile(r"[^A-Za-z0-9\s-]+")
_MAX_SEARCH_TERM_TOKENS = 8
_MAX_PREVIEW_LINES = 3
_MAX_RELATIVE_YEAR_WINDOW = 100
_CASE_QUERY_TERMS = frozenset({"case", "cases"})
_RELATIVE_YEAR_START_WORDS = frozenset({"last", "lats"})
_RELATIVE_YEAR_UNITS = frozenset({"year", "years", "yr", "yrs", "yerar", "yerars"})
_STOPWORDS = frozenset(
    {
        "a",
        "about",
        "an",
        "and",
        "are",
        "can",
        "do",
        "does",
        "for",
        "from",
        "graph",
        "how",
        "in",
        "into",
        "is",
        "it",
        "last",
        "lats",
        "next",
        "of",
        "on",
        "say",
        "should",
        "that",
        "the",
        "this",
        "to",
        "we",
        "what",
        "which",
        "with",
        "year",
        "years",
        "yerar",
        "yerars",
    },
)


def _normalized_tokens(text: str) -> list[str]:
    normalized_text = re.sub(_NON_WORD_PATTERN, " ", text).strip()
    if normalized_text == "":
        return []
    return [token for token in normalized_text.split() if token != ""]


def _candidate_gene_symbol(
    *,
    question: str,
    result: GraphChatResult,
) -> str | None:
    for evidence_item in result.evidence_bundle:
        display_label = (
            evidence_item.display_label.strip()
            if isinstance(evidence_item.display_label, str)
            else ""
        )
        gene_symbol = _normalized_gene_symbol(
            display_label,
            allow_lowercase_alpha=evidence_item.entity_type == "gene",
        )
        if gene_symbol is not None:
            return gene_symbol
    for token in _normalized_tokens(question):
        gene_symbol = _normalized_gene_symbol(token, allow_lowercase_alpha=False)
        if gene_symbol is not None:
            return gene_symbol
    return None


def _normalized_gene_symbol(
    token: str,
    *,
    allow_lowercase_alpha: bool,
) -> str | None:
    normalized = token.upper()
    if not _GENE_SYMBOL_PATTERN.fullmatch(normalized):
        return None
    if not any(character.isalpha() for character in normalized):
        return None
    if token != normalized and not allow_lowercase_alpha:
        has_digit = any(character.isdigit() for character in normalized)
        if not has_digit:
            return None
    return normalized


def _candidate_search_term(
    *,
    question: str,
    objective: str | None,
    gene_symbol: str | None,
) -> str:
    for candidate in (objective, question):
        if not isinstance(candidate, str):
            continue
        filtered_tokens: list[str] = []
        for token in _normalized_tokens(candidate):
            lowered = token.lower()
            if lowered in _STOPWORDS:
                continue
            if token.isdigit():
                continue
            if gene_symbol is not None and token.upper() == gene_symbol:
                continue
            filtered_tokens.append(_search_term_alias(lowered) or token)
            if len(filtered_tokens) >= _MAX_SEARCH_TERM_TOKENS:
                break
        if filtered_tokens:
            return " ".join(filtered_tokens)
    if gene_symbol is not None:
        return gene_symbol
    raw_tokens = _normalized_tokens(question)
    if raw_tokens:
        return " ".join(raw_tokens[:_MAX_SEARCH_TERM_TOKENS])
    msg = "Could not derive a PubMed search term from the chat question."
    raise ValueError(msg)


def _search_term_alias(token: str) -> str | None:
    if token in _CASE_QUERY_TERMS:
        return "case reports"
    return None


def _relative_publication_window(
    *,
    question: str,
    today: date,
) -> tuple[date, date] | None:
    tokens = [token.lower() for token in _normalized_tokens(question)]
    for index in range(max(len(tokens) - 2, 0)):
        start_word = tokens[index]
        year_count = tokens[index + 1]
        unit = tokens[index + 2]
        if (
            start_word in _RELATIVE_YEAR_START_WORDS
            and year_count.isdigit()
            and unit in _RELATIVE_YEAR_UNITS
        ):
            years = int(year_count)
            if 1 <= years <= _MAX_RELATIVE_YEAR_WINDOW:
                return (_subtract_years(today, years), today)
    return None


def _subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def build_chat_literature_request(
    *,
    question: str,
    objective: str | None,
    result: GraphChatResult,
    max_results: int = 5,
    today: date | None = None,
) -> RunPubMedSearchToolArgs:
    effective_today = today or datetime.now(UTC).date()
    gene_symbol = _candidate_gene_symbol(question=question, result=result)
    search_term = _candidate_search_term(
        question=question,
        objective=objective,
        gene_symbol=gene_symbol,
    )
    publication_window = _relative_publication_window(
        question=question,
        today=effective_today,
    )
    return RunPubMedSearchToolArgs(
        gene_symbol=gene_symbol,
        search_term=search_term,
        date_from=publication_window[0] if publication_window else None,
        date_to=publication_window[1] if publication_window else None,
        max_results=max_results,
    )


def build_chat_literature_answer_supplement(
    *,
    query_preview: str,
    preview_records: list[JSONObject],
) -> str | None:
    highlighted_records: list[str] = []
    for record in preview_records[:_MAX_PREVIEW_LINES]:
        title = record.get("title")
        pmid = record.get("pmid")
        if not isinstance(title, str) or title.strip() == "":
            continue
        normalized_title = title.strip()
        if isinstance(pmid, str) and pmid.strip() != "":
            highlighted_records.append(f"- {normalized_title} ({pmid.strip()})")
        else:
            highlighted_records.append(f"- {normalized_title}")
    if not highlighted_records:
        return None
    return (
        "Fresh literature to review:\n"
        f"PubMed query: {query_preview}\n" + "\n".join(highlighted_records)
    )


__all__ = [
    "build_chat_literature_answer_supplement",
    "build_chat_literature_request",
]
