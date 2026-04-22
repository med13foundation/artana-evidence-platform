"""Claim-first workflow metrics and alert helpers.

This module keeps lightweight in-process counters and emits structured logs for:
- claim creation volume
- claim polarity volume
- claim evidence-row creation volume
- non-persistable claim volume
- draft relation creation volume
- relation-claim queue volume
- relation conflict detection volume
- graph trust preset usage
"""

from __future__ import annotations

import json
import logging
from threading import Lock
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from artana_evidence_db.common_types import ResearchSpaceSettings

MetricName = Literal[
    "claims_created_total",
    "claims_by_polarity_total",
    "claim_evidence_rows_created_total",
    "claims_non_persistable_total",
    "relations_draft_created_total",
    "curation_queue_relation_claim_total",
    "relations_conflict_detected_total",
    "graph_filter_preset_usage",
    "hypotheses_manual_created_total",
    "hypotheses_auto_generated_total",
    "hypotheses_deduped_total",
    "hypotheses_generation_failed_total",
    "claim_participants_backfilled_total",
    "claim_participants_backfill_unresolved_total",
]
GraphTrustPreset = Literal[
    "ALL",
    "APPROVED_ONLY",
    "PENDING_REVIEW",
    "REJECTED",
    "CUSTOM",
]

_METRIC_NAMES: tuple[MetricName, ...] = (
    "claims_created_total",
    "claims_by_polarity_total",
    "claim_evidence_rows_created_total",
    "claims_non_persistable_total",
    "relations_draft_created_total",
    "curation_queue_relation_claim_total",
    "relations_conflict_detected_total",
    "graph_filter_preset_usage",
    "hypotheses_manual_created_total",
    "hypotheses_auto_generated_total",
    "hypotheses_deduped_total",
    "hypotheses_generation_failed_total",
    "claim_participants_backfilled_total",
    "claim_participants_backfill_unresolved_total",
)

_logger = logging.getLogger("artana.metrics.claim_first")
_alert_logger = logging.getLogger("artana.alerts.claim_first")
_counter_lock = Lock()
_counters: dict[MetricName, int] = dict.fromkeys(_METRIC_NAMES, 0)


def increment_metric(
    name: MetricName,
    *,
    delta: int = 1,
    tags: dict[str, str] | None = None,
) -> int:
    """Increment one claim-first counter and emit a structured metric log."""
    if delta <= 0:
        return _counters[name]
    with _counter_lock:
        _counters[name] = _counters[name] + delta
        current_value = _counters[name]

    payload: dict[str, object] = {
        "metric_type": "counter",
        "metric_name": name,
        "delta": delta,
        "value": current_value,
    }
    if tags:
        payload["tags"] = {str(key): str(value) for key, value in tags.items()}
    _logger.info(json.dumps(payload, sort_keys=True))
    return current_value


def emit_claim_first_extraction_metrics(  # noqa: PLR0913
    *,
    research_space_id: str,
    source_document_id: str,
    claims_created: int,
    claims_non_persistable: int,
    relations_draft_created: int,
    relation_claims_queued_for_review: int,
    claim_evidence_rows_created: int = 0,
    research_space_settings: ResearchSpaceSettings | None,
) -> None:
    """Emit claim-first extraction counters and non-persistable ratio alerts."""
    common_tags = {
        "research_space_id": research_space_id,
        "source_document_id": source_document_id,
    }
    if claims_created > 0:
        increment_metric(
            "claims_created_total",
            delta=claims_created,
            tags=common_tags,
        )
    if claims_non_persistable > 0:
        increment_metric(
            "claims_non_persistable_total",
            delta=claims_non_persistable,
            tags=common_tags,
        )
    if relations_draft_created > 0:
        increment_metric(
            "relations_draft_created_total",
            delta=relations_draft_created,
            tags=common_tags,
        )
    if relation_claims_queued_for_review > 0:
        increment_metric(
            "curation_queue_relation_claim_total",
            delta=relation_claims_queued_for_review,
            tags=common_tags,
        )
    if claim_evidence_rows_created > 0:
        increment_metric(
            "claim_evidence_rows_created_total",
            delta=claim_evidence_rows_created,
            tags=common_tags,
        )

    _emit_non_persistable_ratio_alert(
        research_space_id=research_space_id,
        source_document_id=source_document_id,
        claims_created=claims_created,
        claims_non_persistable=claims_non_persistable,
        research_space_settings=research_space_settings,
    )


def emit_graph_filter_preset_usage(
    *,
    endpoint: Literal["subgraph", "graph_search", "graph_document"],
    curation_statuses: list[str] | None,
) -> None:
    """Emit graph trust-preset usage counter from backend requests."""
    preset = infer_graph_trust_preset(curation_statuses)
    increment_metric(
        "graph_filter_preset_usage",
        tags={
            "endpoint": endpoint,
            "preset": preset,
        },
    )


def infer_graph_trust_preset(curation_statuses: list[str] | None) -> GraphTrustPreset:
    """Infer the active trust preset from curation status filters."""
    if curation_statuses is None:
        return "ALL"
    normalized = {value.strip().upper() for value in curation_statuses if value.strip()}
    if not normalized:
        return "ALL"
    if normalized == {"APPROVED"}:
        return "APPROVED_ONLY"
    if normalized == {"DRAFT", "UNDER_REVIEW"}:
        return "PENDING_REVIEW"
    if normalized == {"REJECTED", "RETRACTED"}:
        return "REJECTED"
    return "CUSTOM"


def get_metric_counters_snapshot() -> dict[MetricName, int]:
    """Expose in-process metric counters for diagnostics and tests."""
    with _counter_lock:
        return dict(_counters)


def reset_metric_counters_for_tests() -> None:
    """Reset in-process counters. Intended for test use only."""
    with _counter_lock:
        for metric_name in _METRIC_NAMES:
            _counters[metric_name] = 0


def _emit_non_persistable_ratio_alert(
    *,
    research_space_id: str,
    source_document_id: str,
    claims_created: int,
    claims_non_persistable: int,
    research_space_settings: ResearchSpaceSettings | None,
) -> None:
    if claims_created <= 0:
        return
    ratio = max(0.0, min(1.0, claims_non_persistable / claims_created))
    baseline = _resolve_float_setting(
        research_space_settings,
        key="claim_non_persistable_baseline_ratio",
        default=0.25,
    )
    alert_threshold = _resolve_float_setting(
        research_space_settings,
        key="claim_non_persistable_alert_ratio",
        default=min(1.0, baseline + 0.2),
    )
    if ratio <= alert_threshold:
        return

    payload = {
        "alert_type": "claim_non_persistable_ratio_spike",
        "research_space_id": research_space_id,
        "source_document_id": source_document_id,
        "claims_created": claims_created,
        "claims_non_persistable": claims_non_persistable,
        "ratio": ratio,
        "baseline_ratio": baseline,
        "alert_threshold": alert_threshold,
    }
    _alert_logger.warning(json.dumps(payload, sort_keys=True))


def _resolve_float_setting(
    settings: ResearchSpaceSettings | None,
    *,
    key: str,
    default: float,
) -> float:
    if settings is None:
        return default
    settings_map = dict(settings)
    value = settings_map.get(key)
    if not isinstance(value, int | float):
        return default
    return max(0.0, min(1.0, float(value)))


__all__ = [
    "emit_claim_first_extraction_metrics",
    "emit_graph_filter_preset_usage",
    "get_metric_counters_snapshot",
    "increment_metric",
    "infer_graph_trust_preset",
    "reset_metric_counters_for_tests",
]
