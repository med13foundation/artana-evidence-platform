"""JSON, CLI, and scalar normalization helpers for the live canary."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.full_ai_real_space_canary.constants import (
    _REPO_ROOT,
    _SAFE_FILENAME_RE,
    ReportMode,
)

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject


def _normalize_space_ids(
    *,
    explicit_space_ids: list[str],
    csv_space_ids: str,
) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    raw_values = [*explicit_space_ids]
    if csv_space_ids.strip():
        raw_values.extend(part.strip() for part in csv_space_ids.split(","))
    for raw in raw_values:
        value = raw.strip()
        if value == "":
            continue
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    if not normalized:
        raise SystemExit("At least one non-empty --space-id is required.")
    return tuple(normalized)


def _normalize_seed_terms(
    *,
    explicit_terms: list[str],
    csv_terms: str,
) -> tuple[str, ...]:
    raw_values = [*explicit_terms]
    if csv_terms.strip():
        raw_values.extend(part.strip() for part in csv_terms.split(","))
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        trimmed = raw.strip()
        if trimmed == "" or trimmed in seen:
            continue
        seen.add(trimmed)
        normalized.append(trimmed)
    return tuple(normalized)


def _load_sources_preferences(raw_value: str) -> dict[str, bool] | None:
    normalized = _maybe_string(raw_value)
    if normalized is None:
        return None
    source_text = normalized
    if not normalized.startswith("{"):
        candidate_path = _resolve_path(Path(normalized))
        if not candidate_path.is_file():
            raise SystemExit(
                f"--sources-json must be inline JSON or an existing file path: {normalized}",
            )
        source_text = candidate_path.read_text(encoding="utf-8")
    try:
        payload = json.loads(source_text)
    except ValueError as exc:
        raise SystemExit(f"Unable to parse --sources-json: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("--sources-json must resolve to a JSON object.")
    normalized_sources: dict[str, bool] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, bool):
            raise SystemExit(
                "--sources-json keys must be strings and values must be booleans.",
            )
        normalized_sources[key] = value
    return normalized_sources


def _normalize_report_mode(value: object) -> ReportMode:
    if value in {"standard", "canary"}:
        return value
    raise SystemExit(f"Unsupported report mode: {value!r}")


def _normalize_expected_run_count(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and value > 0:
        return value
    raise SystemExit("--expected-run-count must be a positive integer.")


def _normalize_positive_int(value: object, *, name: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    raise SystemExit(f"{name} must be a positive integer.")


def _normalize_positive_float(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise SystemExit(f"{name} must be a positive number.")
    if isinstance(value, int | float) and float(value) > 0:
        return float(value)
    raise SystemExit(f"{name} must be a positive number.")


def _resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else _REPO_ROOT / path


def _required_string(payload: JSONObject, key: str, label: str) -> str:
    value = _maybe_string(payload.get(key))
    if value is None:
        raise RuntimeError(f"{label} is missing required field '{key}'")
    return value


def _dict_value(value: object) -> JSONObject:
    return dict(value) if isinstance(value, dict) else {}


def _list_of_dicts(value: object) -> list[JSONObject]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip() != ""]


def _maybe_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if stripped != "" else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _int_value(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def _is_int_value(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _round_float(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)


def _display_float(value: object) -> str:
    number = _optional_float(value)
    if number is None:
        return "n/a"
    return f"{number:.3f}"


def _safe_filename(value: str) -> str:
    normalized = _SAFE_FILENAME_RE.sub("_", value).strip("._")
    return normalized[:180]


__all__ = [
    "_dict_value",
    "_display_float",
    "_int_value",
    "_is_int_value",
    "_list_of_dicts",
    "_load_sources_preferences",
    "_maybe_string",
    "_normalize_expected_run_count",
    "_normalize_positive_float",
    "_normalize_positive_int",
    "_normalize_report_mode",
    "_normalize_seed_terms",
    "_normalize_space_ids",
    "_optional_float",
    "_parse_datetime",
    "_required_string",
    "_resolve_path",
    "_round_float",
    "_safe_filename",
    "_string_list",
]
