"""Unit tests for deterministic PubMed full-text retrieval."""

from __future__ import annotations

from collections.abc import Iterator

from artana_evidence_api import pubmed_full_text


def test_pmc_open_access_fetch_rejects_large_response_before_body_read(
    monkeypatch,
) -> None:
    response = _FakeLargeResponse()

    def fake_get(url: str, *, timeout: int, stream: bool = False) -> _FakeLargeResponse:
        assert "efetch.fcgi" in url
        assert timeout == 20
        assert stream is True
        return response

    monkeypatch.setattr(pubmed_full_text.requests, "get", fake_get)

    result = pubmed_full_text.fetch_pmc_open_access_full_text("PMC123")

    assert result.found is False
    assert result.warning is not None
    assert "response exceeded" in result.warning
    assert response.iterated is False
    assert response.content_accessed is False
    assert response.closed is True


class _FakeLargeResponse:
    headers = {"content-length": "6000000"}

    def __init__(self) -> None:
        self.closed = False
        self.content_accessed = False
        self.iterated = False

    def raise_for_status(self) -> None:
        return None

    @property
    def content(self) -> bytes:
        self.content_accessed = True
        return b"<article />"

    def iter_content(self, *, chunk_size: int) -> Iterator[bytes]:
        del chunk_size
        self.iterated = True
        yield b"<article />"

    def close(self) -> None:
        self.closed = True
