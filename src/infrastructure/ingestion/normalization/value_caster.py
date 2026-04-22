"""
Value type caster for the ingestion pipeline.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from artana_evidence_db.semantic_ports import DictionaryPort

    from src.infrastructure.ingestion.types import (
        IngestedValue,
        MappedObservation,
        NormalizedObservation,
    )

_MIN_YEAR = 1
_MAX_YEAR = 9999
_DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",
    "%Y-%b-%d",
    "%Y-%B-%d",
    "%Y-%m",
    "%Y-%b",
    "%Y-%B",
    "%b-%Y",
    "%B-%Y",
    "%b %Y",
    "%B %Y",
    "%Y",
)


class ValueCaster:
    """Casts raw values to target types based on dictionary definitions."""

    def __init__(self, dictionary_repository: DictionaryPort) -> None:
        self.dictionary_repo = dictionary_repository

    def cast(  # noqa: C901, PLR0911, PLR0912
        self,
        observation: MappedObservation | NormalizedObservation,
    ) -> IngestedValue:
        """
        Cast the value of an observation to the target data type.

        Complexity ignored for this method as it's a central dispatch for types.
        """
        variable_id = observation.variable_id
        definition = self.dictionary_repo.get_variable(variable_id)
        if not definition:
            # If no definition, return as is (or maybe str?)
            return observation.value

        value = observation.value
        target_type = definition.data_type

        try:
            if target_type == "INTEGER":
                return int(float(value)) if value is not None else None  # type: ignore[arg-type]
            if target_type == "FLOAT":
                return float(value) if value is not None else None  # type: ignore[arg-type]
            if target_type == "BOOLEAN":
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes", "t")
                return bool(value)
            if target_type == "STRING":
                return str(value) if value is not None else None
            if target_type == "DATE":
                return self._cast_date_value(value)
            if target_type == "DATETIME":
                if isinstance(value, datetime):
                    return value
                return datetime.fromisoformat(str(value))
            if target_type == "CODED":
                return str(value)  # Coded values are usually strings

            return value  # noqa: TRY300, PLR1711
        except (ValueError, TypeError, json.JSONDecodeError):
            # Casting failed

            # We could return None, raise an error, or keep original
            # For now, let's log/raise or return None to indicate failure
            # returning None might be safest for pipeline
            return None

    @staticmethod
    def _cast_date_value(value: object) -> date | None:
        if value is None:
            return None

        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value

        year_date = ValueCaster._coerce_year_date(value)
        if year_date is not None:
            return year_date

        normalized = ValueCaster._normalize_date_text(value)
        if normalized is None:
            return None
        return ValueCaster._parse_date_text(normalized)

    @staticmethod
    def _coerce_year_date(value: object) -> date | None:
        if not isinstance(value, int | float) or isinstance(value, bool):
            return None
        year = int(value)
        if _MIN_YEAR <= year <= _MAX_YEAR:
            return date(year, 1, 1)
        return None

    @staticmethod
    def _normalize_date_text(value: object) -> str | None:
        raw_value = str(value).strip()
        if not raw_value:
            return None
        normalized = raw_value.replace("/", "-").replace(".", "-").replace(",", " ")
        return " ".join(normalized.split())

    @staticmethod
    def _parse_date_text(normalized: str) -> date | None:
        iso_candidate = (
            f"{normalized[:-1]}+00:00" if normalized.endswith("Z") else normalized
        )
        try:
            return datetime.fromisoformat(iso_candidate).date()
        except ValueError:
            return ValueCaster._parse_date_with_formats(normalized)

    @staticmethod
    def _parse_date_with_formats(normalized: str) -> date | None:
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(normalized, fmt).replace(tzinfo=UTC).date()
            except ValueError:
                continue
        return None
