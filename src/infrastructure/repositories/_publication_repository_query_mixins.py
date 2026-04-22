"""Internal query helpers for the publication repository."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import and_, asc, desc, func, or_, select

from src.infrastructure.mappers.publication_mapper import PublicationMapper
from src.infrastructure.repositories._publication_repository_update_mixins import (
    _PublicationRepositoryUpdateMixin,
)
from src.models.database.publication import PublicationModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.domain.entities.publication import Publication
    from src.domain.repositories.base import QuerySpecification
    from src.type_definitions.common import PublicationUpdate, QueryFilters


class _PublicationRepositoryQueryMixin(_PublicationRepositoryUpdateMixin):
    """Query-oriented mixin for publication repository operations."""

    @property
    def session(self) -> Session:  # pragma: no cover - contract for mixin methods
        message = "Session property must be implemented by repository class"
        raise NotImplementedError(message)

    def count(self) -> int:  # pragma: no cover - implemented by concrete repository
        message = "count must be implemented by concrete repository class"
        raise NotImplementedError(message)

    def update(  # pragma: no cover - implemented by concrete repository
        self,
        entity_id: int,
        updates: PublicationUpdate,
    ) -> Publication:
        _ = entity_id
        _ = updates
        message = "update must be implemented by concrete repository class"
        raise NotImplementedError(message)

    def find_by_criteria(self, spec: QuerySpecification) -> list[Publication]:
        stmt = select(PublicationModel)
        filters = self._build_filter_expressions(spec.filters)
        if filters:
            stmt = stmt.where(*filters)

        sort_column = self._resolve_sort_column(spec.sort_by or "")
        sort_order = (spec.sort_order or "desc").strip().lower()
        stmt = stmt.order_by(
            desc(sort_column) if sort_order == "desc" else asc(sort_column),
            desc(PublicationModel.id),
        )

        if spec.offset:
            stmt = stmt.offset(spec.offset)
        if spec.limit:
            stmt = stmt.limit(spec.limit)

        models = list(self.session.execute(stmt).scalars())
        return PublicationMapper.to_domain_sequence(models)

    def find_by_pmid(self, pmid: str) -> Publication | None:
        normalized = pmid.strip()
        if not normalized:
            return None
        stmt = select(PublicationModel).where(PublicationModel.pubmed_id == normalized)
        model = self.session.execute(stmt).scalar_one_or_none()
        return PublicationMapper.to_domain(model) if model else None

    def find_by_doi(self, doi: str) -> Publication | None:
        normalized = doi.strip().lower()
        if not normalized:
            return None
        stmt = select(PublicationModel).where(
            func.lower(PublicationModel.doi) == normalized,
        )
        model = self.session.execute(stmt).scalar_one_or_none()
        return PublicationMapper.to_domain(model) if model else None

    def find_by_title(self, title: str, *, fuzzy: bool = False) -> list[Publication]:
        normalized = title.strip()
        if not normalized:
            return []
        if fuzzy:
            stmt = select(PublicationModel).where(
                PublicationModel.title.ilike(f"%{normalized}%"),
            )
        else:
            stmt = select(PublicationModel).where(PublicationModel.title == normalized)
        stmt = stmt.order_by(
            desc(PublicationModel.publication_year),
            desc(PublicationModel.id),
        )
        models = list(self.session.execute(stmt).scalars())
        return PublicationMapper.to_domain_sequence(models)

    def find_by_author(self, author_name: str) -> list[Publication]:
        normalized = author_name.strip()
        if not normalized:
            return []
        stmt = (
            select(PublicationModel)
            .where(PublicationModel.authors.ilike(f"%{normalized}%"))
            .order_by(
                desc(PublicationModel.publication_year),
                desc(PublicationModel.id),
            )
        )
        models = list(self.session.execute(stmt).scalars())
        return PublicationMapper.to_domain_sequence(models)

    def find_by_year_range(self, start_year: int, end_year: int) -> list[Publication]:
        lower = min(start_year, end_year)
        upper = max(start_year, end_year)
        stmt = (
            select(PublicationModel)
            .where(
                and_(
                    PublicationModel.publication_year >= lower,
                    PublicationModel.publication_year <= upper,
                ),
            )
            .order_by(
                desc(PublicationModel.publication_year),
                desc(PublicationModel.id),
            )
        )
        models = list(self.session.execute(stmt).scalars())
        return PublicationMapper.to_domain_sequence(models)

    def find_by_gene_associations(self, gene_id: int) -> list[Publication]:
        _ = gene_id
        return []

    def find_by_variant_associations(self, variant_id: int) -> list[Publication]:
        _ = variant_id
        return []

    def search_publications(
        self,
        query: str,
        limit: int = 10,
        filters: QueryFilters | None = None,
    ) -> list[Publication]:
        normalized_query = query.strip()
        requested_limit = max(limit, 1)

        stmt = select(PublicationModel)
        if normalized_query:
            stmt = stmt.where(self._build_search_expression(normalized_query))
        filter_expressions = self._build_filter_expressions(filters or {})
        if filter_expressions:
            stmt = stmt.where(*filter_expressions)
        stmt = stmt.order_by(
            desc(PublicationModel.publication_year),
            desc(PublicationModel.id),
        )
        stmt = stmt.limit(requested_limit)

        models = list(self.session.execute(stmt).scalars())
        return PublicationMapper.to_domain_sequence(models)

    def paginate_publications(
        self,
        page: int,
        per_page: int,
        sort_by: str,
        sort_order: str,
        filters: QueryFilters | None = None,
    ) -> tuple[list[Publication], int]:
        normalized_page = max(page, 1)
        normalized_per_page = max(per_page, 1)
        offset = (normalized_page - 1) * normalized_per_page
        filter_expressions = self._build_filter_expressions(filters or {})

        data_stmt = select(PublicationModel)
        count_stmt = select(func.count()).select_from(PublicationModel)
        if filter_expressions:
            data_stmt = data_stmt.where(*filter_expressions)
            count_stmt = count_stmt.where(*filter_expressions)

        sort_column = self._resolve_sort_column(sort_by)
        normalized_sort_order = sort_order.strip().lower()
        data_stmt = data_stmt.order_by(
            desc(sort_column) if normalized_sort_order == "desc" else asc(sort_column),
            desc(PublicationModel.id),
        )
        data_stmt = data_stmt.offset(offset).limit(normalized_per_page)

        models = list(self.session.execute(data_stmt).scalars())
        total = int(self.session.execute(count_stmt).scalar_one())
        return PublicationMapper.to_domain_sequence(models), total

    def get_publication_statistics(self) -> dict[str, int | float | bool | str | None]:
        total = self.count()
        reviewed = int(
            self.session.execute(
                select(func.count()).where(PublicationModel.reviewed.is_(True)),
            ).scalar_one(),
        )
        open_access = int(
            self.session.execute(
                select(func.count()).where(PublicationModel.open_access.is_(True)),
            ).scalar_one(),
        )
        with_pubmed = int(
            self.session.execute(
                select(func.count()).where(PublicationModel.pubmed_id.is_not(None)),
            ).scalar_one(),
        )
        with_doi = int(
            self.session.execute(
                select(func.count()).where(PublicationModel.doi.is_not(None)),
            ).scalar_one(),
        )
        average_relevance_raw = self.session.execute(
            select(func.avg(PublicationModel.relevance_score)),
        ).scalar_one()
        average_citations_raw = self.session.execute(
            select(func.avg(PublicationModel.citation_count)),
        ).scalar_one()

        average_relevance = (
            float(average_relevance_raw)
            if isinstance(average_relevance_raw, int | float)
            else None
        )
        average_citations = (
            float(average_citations_raw)
            if isinstance(average_citations_raw, int | float)
            else None
        )

        return {
            "total_publications": total,
            "reviewed_publications": reviewed,
            "open_access_publications": open_access,
            "publications_with_pubmed_id": with_pubmed,
            "publications_with_doi": with_doi,
            "average_relevance_score": average_relevance,
            "average_citation_count": average_citations,
        }

    def find_recent_publications(self, days: int = 30) -> list[Publication]:
        normalized_days = max(days, 1)
        cutoff_datetime = datetime.now(UTC) - timedelta(days=normalized_days)
        cutoff_date = datetime.now(UTC).date() - timedelta(days=normalized_days)
        stmt = (
            select(PublicationModel)
            .where(
                or_(
                    PublicationModel.publication_date >= cutoff_date,
                    PublicationModel.created_at >= cutoff_datetime,
                ),
            )
            .order_by(
                desc(PublicationModel.publication_date),
                desc(PublicationModel.id),
            )
        )
        models = list(self.session.execute(stmt).scalars())
        return PublicationMapper.to_domain_sequence(models)

    def find_med13_relevant(
        self,
        min_relevance: int = 3,
        limit: int | None = None,
    ) -> list[Publication]:
        normalized_min_relevance = max(min_relevance, 0)
        stmt = (
            select(PublicationModel)
            .where(
                or_(
                    PublicationModel.relevance_score >= normalized_min_relevance,
                    PublicationModel.title.ilike("%med13%"),
                    PublicationModel.abstract.ilike("%med13%"),
                    PublicationModel.keywords.ilike("%med13%"),
                ),
            )
            .order_by(
                desc(PublicationModel.relevance_score).nullslast(),
                desc(PublicationModel.publication_year),
                desc(PublicationModel.id),
            )
        )
        if limit:
            stmt = stmt.limit(max(limit, 1))
        models = list(self.session.execute(stmt).scalars())
        return PublicationMapper.to_domain_sequence(models)

    def update_publication(
        self,
        publication_id: int,
        updates: PublicationUpdate,
    ) -> Publication:
        return self.update(publication_id, updates)


__all__ = ["_PublicationRepositoryQueryMixin"]
