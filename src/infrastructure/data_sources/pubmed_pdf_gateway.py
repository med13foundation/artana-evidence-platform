"""PubMed PDF gateway implementations for download workflows."""

from __future__ import annotations

from datetime import UTC, datetime

from src.domain.services.pubmed_search import PubMedPdfGateway


class SimplePubMedPdfGateway(PubMedPdfGateway):
    """Creates lightweight PDF-like payloads for download orchestration tests."""

    async def fetch_pdf(self, article_id: str) -> bytes:
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        content = (
            "Artana Resource Library - PubMed Article\n"
            f"Article ID: {article_id}\n"
            f"Generated at: {timestamp}\n"
            "\n"
            "This is a placeholder document generated for development environments.\n"
        )
        return content.encode("utf-8")


__all__ = ["SimplePubMedPdfGateway"]
