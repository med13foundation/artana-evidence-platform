"""Helpers for optional literature refresh during graph-chat runs."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from artana_evidence_api.tool_catalog import RunPubMedSearchToolArgs
from artana_evidence_api.types.common import JSONObject  # noqa: TC001

if TYPE_CHECKING:
    from artana_evidence_api.graph_chat_runtime import GraphChatResult

_GENE_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9-]{2,20}$")
_NON_WORD_PATTERN = re.compile(r"[^A-Za-z0-9\\s-]+")
_MAX_SEARCH_TERM_TOKENS = 8
_MAX_PREVIEW_LINES = 3
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
        if _GENE_SYMBOL_PATTERN.fullmatch(display_label):
            return display_label
    for token in _normalized_tokens(question):
        if _GENE_SYMBOL_PATTERN.fullmatch(token):
            return token
    return None


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
            if gene_symbol is not None and token == gene_symbol:
                continue
            filtered_tokens.append(token)
            if len(filtered_tokens) >= _MAX_SEARCH_TERM_TOKENS:
                break
        if filtered_tokens:
            return " ".join(filtered_tokens)
    if gene_symbol is not None:
        return gene_symbol
    return "MED13"


def build_chat_literature_request(
    *,
    question: str,
    objective: str | None,
    result: GraphChatResult,
    max_results: int = 5,
) -> RunPubMedSearchToolArgs:
    gene_symbol = _candidate_gene_symbol(question=question, result=result)
    search_term = _candidate_search_term(
        question=question,
        objective=objective,
        gene_symbol=gene_symbol,
    )
    return RunPubMedSearchToolArgs(
        gene_symbol=gene_symbol,
        search_term=search_term,
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
