"""Durable and in-memory stores for document-linked study outcomes."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, datetime
from threading import Lock
from typing import TYPE_CHECKING, overload
from uuid import UUID, uuid4

from artana_evidence_api.models import HarnessStudyOutcomeModel
from artana_evidence_api.sqlalchemy_unit_of_work import commit_or_flush
from artana_evidence_api.study_outcomes.contracts import (
    StudyOutcomeDraft,
    StudyOutcomeRecord,
)
from artana_evidence_api.types.common import JSONObject
from sqlalchemy import func, select

if TYPE_CHECKING:
    from sqlalchemy.orm import InstrumentedAttribute, Session
    from sqlalchemy.sql import ColumnElement, Select


def normalize_study_outcome_draft(draft: StudyOutcomeDraft) -> StudyOutcomeDraft:
    """Normalize one study-outcome draft before persistence."""

    intervention = _required_text(draft.intervention, field_name="intervention")
    outcome_metric = _required_slug_text(
        draft.outcome_metric,
        field_name="outcome_metric",
    )
    unit = _required_slug_text(draft.unit, field_name="unit")
    population = _required_text(draft.population, field_name="population")
    source_quote = _required_text(draft.source_quote, field_name="source_quote")
    comparator = _optional_text(draft.comparator)
    source_pmid = _optional_text(draft.source_pmid) or ""
    return replace(
        draft,
        intervention=intervention,
        comparator=comparator,
        outcome_metric=outcome_metric,
        unit=unit,
        population=population,
        source_pmid=source_pmid,
        source_quote=source_quote,
        metadata=dict(draft.metadata),
    )


def study_outcome_fingerprint(
    *,
    document_id: UUID | str,
    draft: StudyOutcomeDraft,
) -> str:
    """Return a stable fingerprint for one document outcome."""

    normalized = normalize_study_outcome_draft(draft)
    parts = (
        str(document_id),
        normalized.intervention.casefold(),
        normalized.comparator.casefold() if normalized.comparator else "",
        normalized.outcome_metric,
        f"{normalized.value:.8g}",
        normalized.unit,
        normalized.population.casefold(),
        normalized.source_pmid,
        normalized.source_quote.casefold(),
    )
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


class HarnessStudyOutcomeStore:
    """In-memory store for structured quantitative study outcomes."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._records: dict[str, StudyOutcomeRecord] = {}
        self._record_ids_by_space: dict[str, list[str]] = {}
        self._fingerprints_by_space: dict[str, set[str]] = {}

    def create_outcomes(
        self,
        *,
        space_id: UUID | str,
        document_id: UUID | str,
        run_id: UUID | str | None,
        outcomes: tuple[StudyOutcomeDraft, ...],
    ) -> list[StudyOutcomeRecord]:
        """Persist new outcomes and skip duplicates in the same space."""

        normalized_space_id = str(space_id)
        normalized_document_id = str(document_id)
        normalized_run_id = str(run_id) if run_id is not None else None
        now = datetime.now(UTC)
        created: list[StudyOutcomeRecord] = []
        with self._lock:
            fingerprints = self._fingerprints_by_space.setdefault(
                normalized_space_id,
                set(),
            )
            for draft in outcomes:
                normalized = normalize_study_outcome_draft(draft)
                fingerprint = study_outcome_fingerprint(
                    document_id=normalized_document_id,
                    draft=normalized,
                )
                if fingerprint in fingerprints:
                    continue
                record = StudyOutcomeRecord(
                    id=str(uuid4()),
                    space_id=normalized_space_id,
                    document_id=normalized_document_id,
                    run_id=normalized_run_id,
                    intervention=normalized.intervention,
                    comparator=normalized.comparator,
                    outcome_metric=normalized.outcome_metric,
                    value=normalized.value,
                    unit=normalized.unit,
                    confidence_interval_low=normalized.confidence_interval_low,
                    confidence_interval_high=normalized.confidence_interval_high,
                    population=normalized.population,
                    n=normalized.n,
                    source_pmid=normalized.source_pmid,
                    source_quote=normalized.source_quote,
                    metadata=dict(normalized.metadata),
                    outcome_fingerprint=fingerprint,
                    created_at=now,
                    updated_at=now,
                )
                self._records[record.id] = record
                self._record_ids_by_space.setdefault(normalized_space_id, []).append(
                    record.id,
                )
                fingerprints.add(fingerprint)
                created.append(record)
        return created

    def list_outcomes(
        self,
        *,
        space_id: UUID | str,
        intervention: str | None = None,
        population: str | None = None,
        outcome_metric: str | None = None,
        document_id: UUID | str | None = None,
        offset: int = 0,
        limit: int = 200,
    ) -> list[StudyOutcomeRecord]:
        """List persisted outcomes for a space with optional filters."""

        with self._lock:
            records = [
                self._records[record_id]
                for record_id in self._record_ids_by_space.get(str(space_id), [])
            ]
        filtered = _filter_records(
            records,
            intervention=intervention,
            population=population,
            outcome_metric=outcome_metric,
            document_id=document_id,
        )
        return sorted(
            filtered,
            key=lambda record: record.created_at,
            reverse=True,
        )[offset : offset + limit]

    def count_outcomes(
        self,
        *,
        space_id: UUID | str,
        intervention: str | None = None,
        population: str | None = None,
        outcome_metric: str | None = None,
        document_id: UUID | str | None = None,
    ) -> int:
        """Count persisted outcomes for a space with optional filters."""

        return len(
            self.list_outcomes(
                space_id=space_id,
                intervention=intervention,
                population=population,
                outcome_metric=outcome_metric,
                document_id=document_id,
                offset=0,
                limit=1_000_000,
            ),
        )


class SqlAlchemyStudyOutcomeStore(HarnessStudyOutcomeStore):
    """SQLAlchemy-backed study-outcome store."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            msg = "Session not provided"
            raise ValueError(msg)
        return self._session

    def create_outcomes(
        self,
        *,
        space_id: UUID | str,
        document_id: UUID | str,
        run_id: UUID | str | None,
        outcomes: tuple[StudyOutcomeDraft, ...],
    ) -> list[StudyOutcomeRecord]:
        normalized_space_id = str(space_id)
        normalized_document_id = str(document_id)
        normalized_run_id = str(run_id) if run_id is not None else None
        created_models: list[HarnessStudyOutcomeModel] = []
        for draft in outcomes:
            normalized = normalize_study_outcome_draft(draft)
            fingerprint = study_outcome_fingerprint(
                document_id=normalized_document_id,
                draft=normalized,
            )
            existing = self.session.execute(
                select(HarnessStudyOutcomeModel.id).where(
                    HarnessStudyOutcomeModel.space_id == normalized_space_id,
                    HarnessStudyOutcomeModel.outcome_fingerprint == fingerprint,
                ),
            ).first()
            if existing is not None:
                continue
            model = HarnessStudyOutcomeModel(
                space_id=normalized_space_id,
                document_id=normalized_document_id,
                run_id=normalized_run_id,
                intervention=normalized.intervention,
                comparator=normalized.comparator,
                outcome_metric=normalized.outcome_metric,
                value=normalized.value,
                unit=normalized.unit,
                confidence_interval_low=normalized.confidence_interval_low,
                confidence_interval_high=normalized.confidence_interval_high,
                population=normalized.population,
                n=normalized.n,
                source_pmid=normalized.source_pmid,
                source_quote=normalized.source_quote,
                metadata_payload=normalized.metadata,
                outcome_fingerprint=fingerprint,
            )
            self.session.add(model)
            created_models.append(model)
        commit_or_flush(self.session)
        for model in created_models:
            self.session.refresh(model)
        return [_record_from_model(model) for model in created_models]

    def list_outcomes(
        self,
        *,
        space_id: UUID | str,
        intervention: str | None = None,
        population: str | None = None,
        outcome_metric: str | None = None,
        document_id: UUID | str | None = None,
        offset: int = 0,
        limit: int = 200,
    ) -> list[StudyOutcomeRecord]:
        stmt = select(HarnessStudyOutcomeModel).where(
            HarnessStudyOutcomeModel.space_id == str(space_id),
        )
        stmt = _apply_sql_filters(
            stmt,
            intervention=intervention,
            population=population,
            outcome_metric=outcome_metric,
            document_id=document_id,
        )
        models = (
            self.session.execute(
                stmt.order_by(HarnessStudyOutcomeModel.created_at.desc())
                .offset(offset)
                .limit(limit),
            )
            .scalars()
            .all()
        )
        return [_record_from_model(model) for model in models]

    def count_outcomes(
        self,
        *,
        space_id: UUID | str,
        intervention: str | None = None,
        population: str | None = None,
        outcome_metric: str | None = None,
        document_id: UUID | str | None = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(HarnessStudyOutcomeModel)
            .where(HarnessStudyOutcomeModel.space_id == str(space_id))
        )
        stmt = _apply_sql_filters(
            stmt,
            intervention=intervention,
            population=population,
            outcome_metric=outcome_metric,
            document_id=document_id,
        )
        return int(self.session.execute(stmt).scalar_one())


def _required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if normalized == "":
        msg = f"Study outcome {field_name} is required"
        raise ValueError(msg)
    return normalized


def _required_slug_text(value: str, *, field_name: str) -> str:
    normalized = _required_text(value, field_name=field_name).strip().lower()
    return "_".join(normalized.split())


def _optional_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _matches_text(value: str, query: str | None) -> bool:
    normalized = _optional_text(query)
    if normalized is None:
        return True
    return normalized.casefold() in value.casefold()


def _matches_metric(value: str, query: str | None) -> bool:
    normalized = _optional_text(query)
    if normalized is None:
        return True
    return value == _required_slug_text(normalized, field_name="outcome_metric")


def _filter_records(
    records: Iterable[StudyOutcomeRecord],
    *,
    intervention: str | None,
    population: str | None,
    outcome_metric: str | None,
    document_id: UUID | str | None,
) -> list[StudyOutcomeRecord]:
    normalized_document_id = str(document_id) if document_id is not None else None
    return [
        record
        for record in records
        if _matches_text(record.intervention, intervention)
        and _matches_text(record.population, population)
        and _matches_metric(record.outcome_metric, outcome_metric)
        and (
            normalized_document_id is None
            or record.document_id == normalized_document_id
        )
    ]


def _contains_filter(
    column: InstrumentedAttribute[str],
    query: str | None,
) -> ColumnElement[bool] | None:
    normalized = _optional_text(query)
    if normalized is None:
        return None
    return func.lower(column).like(f"%{normalized.casefold()}%")


def _metric_filter(
    column: InstrumentedAttribute[str],
    query: str | None,
) -> ColumnElement[bool] | None:
    normalized = _optional_text(query)
    if normalized is None:
        return None
    return column == _required_slug_text(normalized, field_name="outcome_metric")


@overload
def _apply_sql_filters(
    stmt: Select[tuple[HarnessStudyOutcomeModel]],
    *,
    intervention: str | None,
    population: str | None,
    outcome_metric: str | None,
    document_id: UUID | str | None,
) -> Select[tuple[HarnessStudyOutcomeModel]]: ...


@overload
def _apply_sql_filters(
    stmt: Select[tuple[int]],
    *,
    intervention: str | None,
    population: str | None,
    outcome_metric: str | None,
    document_id: UUID | str | None,
) -> Select[tuple[int]]: ...


def _apply_sql_filters(
    stmt: Select[tuple[HarnessStudyOutcomeModel]] | Select[tuple[int]],
    *,
    intervention: str | None,
    population: str | None,
    outcome_metric: str | None,
    document_id: UUID | str | None,
) -> Select[tuple[HarnessStudyOutcomeModel]] | Select[tuple[int]]:
    for condition in (
        _contains_filter(HarnessStudyOutcomeModel.intervention, intervention),
        _contains_filter(HarnessStudyOutcomeModel.population, population),
        _metric_filter(HarnessStudyOutcomeModel.outcome_metric, outcome_metric),
    ):
        if condition is not None:
            stmt = stmt.where(condition)
    if document_id is not None:
        stmt = stmt.where(HarnessStudyOutcomeModel.document_id == str(document_id))
    return stmt


def _json_object(value: object) -> JSONObject:
    return value if isinstance(value, dict) else {}


def _record_from_model(model: HarnessStudyOutcomeModel) -> StudyOutcomeRecord:
    return StudyOutcomeRecord(
        id=model.id,
        space_id=model.space_id,
        document_id=model.document_id,
        run_id=model.run_id,
        intervention=model.intervention,
        comparator=model.comparator,
        outcome_metric=model.outcome_metric,
        value=model.value,
        unit=model.unit,
        confidence_interval_low=model.confidence_interval_low,
        confidence_interval_high=model.confidence_interval_high,
        population=model.population,
        n=model.n,
        source_pmid=model.source_pmid,
        source_quote=model.source_quote,
        metadata=_json_object(model.metadata_payload),
        outcome_fingerprint=model.outcome_fingerprint,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


__all__ = [
    "HarnessStudyOutcomeStore",
    "SqlAlchemyStudyOutcomeStore",
    "normalize_study_outcome_draft",
    "study_outcome_fingerprint",
]
