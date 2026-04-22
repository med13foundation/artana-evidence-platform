"""Application service for presenting curated Artana resources."""

from collections.abc import Sequence

from src.models.resource_model import Resource


def list_resources() -> Sequence[Resource]:
    """Return curated resources. Placeholder until database integration is added."""
    return [
        Resource(
            id=1,
            title="Artana.bio",
            url="https://artana.bio",
            summary="Central information hub for the Artana research platform.",
        ),
    ]


__all__ = ["list_resources"]
