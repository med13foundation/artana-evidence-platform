"""Internal update helpers for the publication repository."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from src.infrastructure.repositories._publication_repository_filter_mixins import (
    _PublicationRepositoryFilterMixin,
)

if TYPE_CHECKING:
    from src.models.database.publication import PublicationModel
    from src.type_definitions.common import PublicationUpdate


class _PublicationRepositoryUpdateMixin(_PublicationRepositoryFilterMixin):
    """Shared mutation helpers for publication updates."""

    @staticmethod
    def _apply_updates(
        *,
        model: PublicationModel,
        updates: PublicationUpdate,
    ) -> None:
        handlers = {
            "title": _PublicationRepositoryUpdateMixin._update_title,
            "authors": _PublicationRepositoryUpdateMixin._update_authors,
            "journal": _PublicationRepositoryUpdateMixin._update_journal,
            "publication_year": _PublicationRepositoryUpdateMixin._update_publication_year,
            "doi": _PublicationRepositoryUpdateMixin._update_doi,
            "pmid": _PublicationRepositoryUpdateMixin._update_pmid,
            "abstract": _PublicationRepositoryUpdateMixin._update_abstract,
        }
        for field, value in updates.items():
            handler = handlers.get(field)
            if handler is None:
                continue
            handler(model, value)

    @staticmethod
    def _update_title(model: PublicationModel, value: object) -> None:
        if not isinstance(value, str):
            return
        normalized = value.strip()
        if normalized:
            model.title = normalized

    @staticmethod
    def _update_authors(model: PublicationModel, value: object) -> None:
        if not isinstance(value, list):
            return
        normalized_authors = [
            author.strip()
            for author in value
            if isinstance(author, str) and author.strip()
        ]
        if normalized_authors:
            model.authors = json.dumps(normalized_authors)

    @staticmethod
    def _update_journal(model: PublicationModel, value: object) -> None:
        if not isinstance(value, str):
            return
        normalized = value.strip()
        if normalized:
            model.journal = normalized

    @staticmethod
    def _update_publication_year(model: PublicationModel, value: object) -> None:
        year = _PublicationRepositoryUpdateMixin._coerce_int(value)
        if year is not None:
            model.publication_year = year

    @staticmethod
    def _update_doi(model: PublicationModel, value: object) -> None:
        if value is None:
            model.doi = None
            return
        if isinstance(value, str):
            normalized = value.strip()
            model.doi = normalized or None

    @staticmethod
    def _update_pmid(model: PublicationModel, value: object) -> None:
        if value is None:
            model.pubmed_id = None
            return
        if isinstance(value, str):
            normalized = value.strip()
            model.pubmed_id = normalized or None

    @staticmethod
    def _update_abstract(model: PublicationModel, value: object) -> None:
        if value is None:
            model.abstract = None
            return
        if isinstance(value, str):
            normalized = value.strip()
            model.abstract = normalized or None


__all__ = ["_PublicationRepositoryUpdateMixin"]
