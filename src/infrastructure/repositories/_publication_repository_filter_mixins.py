"""Internal filter helpers for the publication repository."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, or_

from src.models.database.publication import PublicationModel

if TYPE_CHECKING:
    from sqlalchemy.sql import ColumnElement

    from src.type_definitions.common import QueryFilters


class _PublicationRepositoryFilterMixin:
    """Shared search/filter parsing helpers for publication queries."""

    @staticmethod
    def _build_search_expression(query: str) -> ColumnElement[bool]:
        pattern = f"%{query}%"
        return or_(
            PublicationModel.title.ilike(pattern),
            PublicationModel.abstract.ilike(pattern),
            PublicationModel.authors.ilike(pattern),
            PublicationModel.journal.ilike(pattern),
            PublicationModel.pubmed_id.ilike(pattern),
            PublicationModel.doi.ilike(pattern),
        )

    @staticmethod
    def _build_filter_expressions(filters: QueryFilters) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = []
        for raw_field, raw_value in filters.items():
            expression = _PublicationRepositoryFilterMixin._build_filter_expression(
                raw_field=raw_field,
                raw_value=raw_value,
            )
            if expression is not None:
                expressions.append(expression)
        return expressions

    @staticmethod
    def _build_filter_expression(
        *,
        raw_field: str,
        raw_value: object,
    ) -> ColumnElement[bool] | None:
        if raw_value is None:
            return None
        field = raw_field.strip().lower()
        if field == "query":
            return _PublicationRepositoryFilterMixin._query_filter_expression(raw_value)

        handlers = {
            "publication_year_from": _PublicationRepositoryFilterMixin._publication_year_from_expression,
            "publication_year_to": _PublicationRepositoryFilterMixin._publication_year_to_expression,
            "reviewed": _PublicationRepositoryFilterMixin._reviewed_expression,
            "open_access": _PublicationRepositoryFilterMixin._open_access_expression,
            "pubmed_id": _PublicationRepositoryFilterMixin._pubmed_id_expression,
            "pmid": _PublicationRepositoryFilterMixin._pubmed_id_expression,
            "doi": _PublicationRepositoryFilterMixin._doi_expression,
            "journal": _PublicationRepositoryFilterMixin._journal_expression,
            "publication_type": _PublicationRepositoryFilterMixin._publication_type_expression,
            "min_relevance": _PublicationRepositoryFilterMixin._min_relevance_expression,
        }
        handler = handlers.get(field)
        if handler is None:
            return None
        return handler(raw_value)

    @staticmethod
    def _query_filter_expression(raw_value: object) -> ColumnElement[bool] | None:
        if not isinstance(raw_value, str):
            return None
        normalized = raw_value.strip()
        if not normalized:
            return None
        return _PublicationRepositoryFilterMixin._build_search_expression(normalized)

    @staticmethod
    def _publication_year_from_expression(
        raw_value: object,
    ) -> ColumnElement[bool] | None:
        year = _PublicationRepositoryFilterMixin._coerce_int(raw_value)
        if year is None:
            return None
        return PublicationModel.publication_year >= year

    @staticmethod
    def _publication_year_to_expression(
        raw_value: object,
    ) -> ColumnElement[bool] | None:
        year = _PublicationRepositoryFilterMixin._coerce_int(raw_value)
        if year is None:
            return None
        return PublicationModel.publication_year <= year

    @staticmethod
    def _reviewed_expression(raw_value: object) -> ColumnElement[bool] | None:
        reviewed = _PublicationRepositoryFilterMixin._coerce_bool(raw_value)
        if reviewed is None:
            return None
        return PublicationModel.reviewed.is_(reviewed)

    @staticmethod
    def _open_access_expression(raw_value: object) -> ColumnElement[bool] | None:
        open_access = _PublicationRepositoryFilterMixin._coerce_bool(raw_value)
        if open_access is None:
            return None
        return PublicationModel.open_access.is_(open_access)

    @staticmethod
    def _pubmed_id_expression(raw_value: object) -> ColumnElement[bool] | None:
        if not isinstance(raw_value, str):
            return None
        normalized = raw_value.strip()
        if not normalized:
            return None
        return PublicationModel.pubmed_id == normalized

    @staticmethod
    def _doi_expression(raw_value: object) -> ColumnElement[bool] | None:
        if not isinstance(raw_value, str):
            return None
        normalized = raw_value.strip().lower()
        if not normalized:
            return None
        return func.lower(PublicationModel.doi) == normalized

    @staticmethod
    def _journal_expression(raw_value: object) -> ColumnElement[bool] | None:
        if not isinstance(raw_value, str):
            return None
        normalized = raw_value.strip()
        if not normalized:
            return None
        return PublicationModel.journal.ilike(f"%{normalized}%")

    @staticmethod
    def _publication_type_expression(raw_value: object) -> ColumnElement[bool] | None:
        if not isinstance(raw_value, str):
            return None
        normalized = raw_value.strip()
        if not normalized:
            return None
        return PublicationModel.publication_type == normalized

    @staticmethod
    def _min_relevance_expression(raw_value: object) -> ColumnElement[bool] | None:
        relevance = _PublicationRepositoryFilterMixin._coerce_int(raw_value)
        if relevance is None:
            return None
        return PublicationModel.relevance_score >= relevance

    @staticmethod
    def _resolve_sort_column(sort_by: str) -> ColumnElement[object]:
        default_column = PublicationModel.__table__.c.publication_year
        normalized = sort_by.strip()
        if not normalized:
            return default_column
        column = PublicationModel.__table__.c.get(normalized)
        if column is None:
            return default_column
        return column

    @staticmethod
    def _coerce_int(value: object) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None

    @staticmethod
    def _coerce_bool(value: object) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return None


__all__ = ["_PublicationRepositoryFilterMixin"]
