"""Port for text embedding generation services."""

from __future__ import annotations

from abc import ABC, abstractmethod


class TextEmbeddingPort(ABC):
    """Interface for computing fixed-size embedding vectors from text."""

    @abstractmethod
    def embed_text(
        self,
        text: str,
        *,
        model_name: str,
    ) -> list[float] | None:
        """Return an embedding vector for text, or None when unavailable."""

    def embed_texts(
        self,
        texts: list[str],
        *,
        model_name: str,
    ) -> list[list[float] | None]:
        """Return embedding vectors for texts, preserving input order."""
        return [self.embed_text(text, model_name=model_name) for text in texts]


__all__ = ["TextEmbeddingPort"]
