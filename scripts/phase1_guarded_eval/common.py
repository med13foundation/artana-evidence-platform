"""Shared helpers for the Phase 1 guarded-evaluation script."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject

Phase1GuardedCompareMode = Literal["shared_baseline_replay", "dual_live_guarded"]
Phase1GuardedReportMode = Literal["standard", "canary"]

_GUARDED_SOURCE_CHASE_PROFILE = "guarded_source_chase"
_GUARDED_SOURCE_STRATEGY = "prioritized_structured_sequence"
_GUARDED_CHASE_STRATEGY = "chase_selection"
_GUARDED_TERMINAL_STRATEGY = "terminal_control_flow"
_LIVE_EVIDENCE_SOURCE_KEYS = frozenset(
    {
        "pubmed",
        "clinvar",
        "drugbank",
        "alphafold",
        "clinical_trials",
        "mgi",
        "zfin",
        "marrvel",
    },
)
_CONTEXT_ONLY_SOURCE_KEYS = frozenset({"pdf", "text"})
_GROUNDING_SOURCE_KEYS = frozenset({"mondo"})
_RESERVED_SOURCE_KEYS = frozenset({"uniprot", "hgnc"})
_ACTION_DEFAULT_SOURCE_KEYS: dict[str, str] = {
    "QUERY_PUBMED": "pubmed",
    "INGEST_AND_EXTRACT_PUBMED": "pubmed",
    "REVIEW_PDF_WORKSET": "pdf",
    "REVIEW_TEXT_WORKSET": "text",
    "LOAD_MONDO_GROUNDING": "mondo",
    "RUN_UNIPROT_GROUNDING": "uniprot",
    "RUN_HGNC_GROUNDING": "hgnc",
}
_ROLLBACK_REQUIRED_CANARY_GATES = frozenset(
    {
        "no_fixture_failures",
        "no_timeouts",
        "proof_receipts_present_and_verified",
        "no_invalid_outputs",
        "no_fallback_outputs",
        "no_budget_violations",
        "no_disabled_source_violations",
        "no_reserved_source_violations",
        "no_context_only_source_violations",
        "no_grounding_source_violations",
        "qualitative_rationale_present_everywhere",
    },
)


def _dict_value(value: object) -> JSONObject:
    return dict(value) if isinstance(value, dict) else {}


def _list_of_dicts(value: object) -> list[JSONObject]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _dict_of_ints(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        key: count
        for key, count in value.items()
        if isinstance(key, str) and isinstance(count, int)
    }


def _maybe_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if stripped != "" else None


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _int_value(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _list_count(value: object) -> int | None:
    if isinstance(value, list):
        return len(value)
    return None


def _excerpt_text(value: str | None, *, max_chars: int) -> str | None:
    if value is None:
        return None
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def _fixture_list_text(value: object) -> str:
    if not isinstance(value, list):
        return "none"
    fixture_names = [item for item in value if isinstance(item, str) and item != ""]
    if not fixture_names:
        return "none"
    return ", ".join(fixture_names)


def _gate_label(value: object) -> str:
    return "PASS" if value is True else "FAIL"


def _optional_gate_label(value: object) -> str:
    if value is None:
        return "n/a"
    return _gate_label(value)


def _proof_recommended_source_key(proof: JSONObject) -> str | None:
    for key in ("recommended_source_key", "applied_source_key"):
        source_key = _maybe_string(proof.get(key))
        if source_key is not None:
            return source_key
    for key in ("recommended_action_type", "applied_action_type"):
        action_type = _maybe_string(proof.get(key))
        if action_type is None:
            continue
        default_source_key = _ACTION_DEFAULT_SOURCE_KEYS.get(action_type)
        if default_source_key is not None:
            return default_source_key
    return None


def _proof_source_policy_violation_category(
    proof: JSONObject,
) -> Literal["disabled", "reserved", "context_only", "grounding"] | None:
    if proof.get("disabled_source_violation") is True:
        return "disabled"
    source_key = _proof_recommended_source_key(proof)
    if source_key in _RESERVED_SOURCE_KEYS:
        return "reserved"
    if source_key in _CONTEXT_ONLY_SOURCE_KEYS:
        return "context_only"
    if source_key in _GROUNDING_SOURCE_KEYS:
        return "grounding"
    if source_key in _LIVE_EVIDENCE_SOURCE_KEYS:
        return None
    validation_error = _maybe_string(proof.get("validation_error")) or ""
    lowered_error = validation_error.casefold()
    if "reserved" in lowered_error:
        return "reserved"
    if "context_only" in lowered_error or "context-only" in lowered_error:
        return "context_only"
    if "grounding" in lowered_error:
        return "grounding"
    return None


def _round_runtime_seconds(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)


def _display_float(value: object) -> str:
    number = _optional_float(value)
    if number is None:
        return "n/a"
    return f"{number:.3f}"


def _base_fixture_name(value: str) -> str:
    head, _separator, _tail = value.partition("__repeat_")
    return head


def _canary_verdict_label(value: object) -> str:
    verdict = _maybe_string(value)
    if verdict is None:
        return "n/a"
    if verdict == "rollback_required":
        return "ROLLBACK REQUIRED"
    if verdict == "hold":
        return "HOLD"
    if verdict == "pass":
        return "PASS"
    return verdict
