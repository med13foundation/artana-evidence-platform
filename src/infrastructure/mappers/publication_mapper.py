from __future__ import annotations

import json
from typing import TYPE_CHECKING

from src.domain.entities.publication import Publication, PublicationType
from src.domain.value_objects.identifiers import PublicationIdentifier
from src.models.database.publication import PublicationModel

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence


class PublicationMapper:
    """Maps between SQLAlchemy PublicationModel and domain Publication entities."""

    @staticmethod
    def to_domain(model: PublicationModel) -> Publication:
        identifier = PublicationIdentifier(
            pubmed_id=model.pubmed_id,
            pmc_id=model.pmc_id,
            doi=model.doi,
        )
        authors = PublicationMapper._parse_people(model.authors)
        keywords = PublicationMapper._parse_keywords(model.keywords)

        return Publication(
            identifier=identifier,
            title=model.title,
            authors=authors,
            journal=model.journal,
            publication_year=model.publication_year,
            publication_type=model.publication_type or PublicationType.JOURNAL_ARTICLE,
            volume=model.volume,
            issue=model.issue,
            pages=model.pages,
            publication_date=model.publication_date,
            abstract=model.abstract,
            keywords=keywords,
            citation_count=model.citation_count or 0,
            impact_factor=model.impact_factor,
            reviewed=model.reviewed,
            relevance_score=model.relevance_score,
            full_text_url=model.full_text_url,
            open_access=model.open_access,
            created_at=model.created_at,
            updated_at=model.updated_at,
            id=model.id,
        )

    @staticmethod
    def to_model(
        entity: Publication,
        model: PublicationModel | None = None,
    ) -> PublicationModel:
        target = model or PublicationModel()
        target.pubmed_id = entity.identifier.pubmed_id
        target.pmc_id = entity.identifier.pmc_id
        target.doi = entity.identifier.doi
        target.title = entity.title
        target.authors = PublicationMapper._serialize_people(entity.authors)
        target.journal = entity.journal
        target.publication_year = entity.publication_year
        target.publication_type = entity.publication_type
        target.volume = entity.volume
        target.issue = entity.issue
        target.pages = entity.pages
        target.publication_date = entity.publication_date
        target.abstract = entity.abstract
        target.keywords = PublicationMapper._serialize_keywords(entity.keywords)
        target.citation_count = entity.citation_count
        target.impact_factor = entity.impact_factor
        target.reviewed = entity.reviewed
        target.relevance_score = entity.relevance_score
        target.full_text_url = entity.full_text_url
        target.open_access = entity.open_access
        if entity.created_at:
            target.created_at = entity.created_at
        if entity.updated_at:
            target.updated_at = entity.updated_at
        return target

    @staticmethod
    def to_domain_sequence(models: Sequence[PublicationModel]) -> list[Publication]:
        return [PublicationMapper.to_domain(model) for model in models]

    @staticmethod
    def _parse_people(raw: str) -> tuple[str, ...]:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return tuple(str(item).strip() for item in parsed if str(item).strip())
        except (json.JSONDecodeError, TypeError):
            pass
        if not raw:
            return ()
        return tuple(name.strip() for name in raw.split(",") if name.strip())

    @staticmethod
    def _serialize_people(people: tuple[str, ...]) -> str:
        return json.dumps(list(people))

    @staticmethod
    def _parse_keywords(raw: str | None) -> tuple[str, ...]:
        if not raw:
            return ()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return tuple(
                    str(item).strip().lower() for item in parsed if str(item).strip()
                )
        except json.JSONDecodeError:
            pass
        return tuple(
            keyword.strip().lower() for keyword in raw.split(",") if keyword.strip()
        )

    @staticmethod
    def _serialize_keywords(keywords: tuple[str, ...]) -> str | None:
        if not keywords:
            return None
        return json.dumps(list(keywords))


__all__ = ["PublicationMapper"]
