"""Document-context summary helpers for chat workflows."""

from __future__ import annotations

from artana_evidence_api.document_store import HarnessDocumentRecord
from artana_evidence_api.types.common import JSONObject


def summarize_document_context(
    *,
    documents: tuple[HarnessDocumentRecord, ...],
    proposals_by_document_id: dict[str, list[JSONObject]],
) -> str | None:
    """Build a compact answer supplement for document-backed chat context."""

    if not documents:
        return None
    lines = ["Referenced document context:"]
    for document in documents:
        proposal_summaries = proposals_by_document_id.get(document.id, [])
        lines.append(
            f"- {document.title} [{document.source_type}] "
            f"({len(proposal_summaries)} staged proposal(s))",
        )
        for proposal_summary in proposal_summaries[:3]:
            summary = proposal_summary.get("summary")
            if isinstance(summary, str) and summary.strip() != "":
                lines.append(f"  - {summary.strip()}")
    return "\n".join(lines)


__all__ = ["summarize_document_context"]
