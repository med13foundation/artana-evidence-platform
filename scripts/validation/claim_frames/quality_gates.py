"""Evaluate deterministic TG-03 quality-readiness gate policy."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from scripts.validation.claim_frames.provider_receipts import (
        ProviderReceiptVerification,
    )

JsonObject = dict[str, object]
_STABILITY_MINIMUM: Final = 0.95


def single_run_gates(*, metrics: Mapping[str, object]) -> JsonObject:
    """Build readiness gates for one run, before stability can be evaluated."""

    gates = _quality_readiness_gates(metrics=metrics, scope="")
    gates["stability"] = {"passed": False, "status": "not_evaluated"}
    return gates


def comparison_gates(
    *,
    metrics: Mapping[str, object],
    provider_receipts: ProviderReceiptVerification,
) -> JsonObject:
    """Build readiness gates for a three-run comparison."""

    gates = _quality_readiness_gates(metrics=metrics, scope=" across all runs")
    gates["provider_execution_receipts"] = _gate(
        passed=provider_receipts.gate_passed,
        rule=(
            "every model attempt has a unique, completed, standalone OpenAI receipt "
            "with matching model, exact user prompt, canonical output, and payload"
        ),
    )
    gates["stability"] = _gate(
        passed=_float(metrics.get("canonical_semantic_frame_stability_rate"))
        >= _STABILITY_MINIMUM,
        rule="canonical semantic-frame stability is at least 95%",
    )
    return gates


def _quality_readiness_gates(
    *,
    metrics: Mapping[str, object],
    scope: str,
) -> JsonObject:
    return {
        "composed_pipeline": _gate(
            passed=_float(metrics.get("composed_pipeline_completion_rate")) == 1.0,
            rule=f"all cases use claim_inventory then one claim_framing per item{scope}",
        ),
        "agent_invocation_completion": _gate(
            passed=_float(metrics.get("agent_invocation_completion_rate")) == 1.0,
            rule=f"all strict cases completed a real agent invocation{scope}",
        ),
        "strict_usable_extraction_completion": _gate(
            passed=_float(metrics.get("strict_usable_extraction_completion_rate"))
            == 1.0,
            rule=f"all strict live cases produced usable extraction{scope}",
        ),
        "polarity": _gate(
            passed=_float(metrics.get("explicit_polarity_concordance_rate")) == 1.0,
            rule=f"explicit polarity concordance is 100%{scope}",
        ),
        "epistemic_status": _gate(
            passed=_float(metrics.get("epistemic_status_concordance_rate")) == 1.0,
            rule=f"explicit epistemic-status concordance is 100%{scope}",
        ),
        "qualifier_presence": _gate(
            passed=_float(metrics.get("required_qualifier_completeness_rate")) == 1.0,
            rule=f"required qualifier presence is 100%{scope}",
        ),
        "qualifier_concordance": _gate(
            passed=_float(metrics.get("qualifier_concordance_rate")) == 1.0,
            rule=f"all qualifier categories are gold-concordant{scope}",
        ),
        "endpoint_source_match_precision": _gate(
            passed=_float(metrics.get("endpoint_source_match_precision")) == 1.0,
            rule=f"endpoint/source match precision is 100%{scope}",
        ),
        "endpoint_source_match_recall": _gate(
            passed=_float(metrics.get("endpoint_source_match_recall")) == 1.0,
            rule=f"endpoint/source match recall is 100%{scope}",
        ),
        "full_frame_precision": _gate(
            passed=_float(metrics.get("full_frame_precision")) == 1.0,
            rule=f"full-frame precision is 100%{scope}",
        ),
        "full_frame_recall": _gate(
            passed=_float(metrics.get("full_frame_recall")) == 1.0,
            rule=f"full-frame recall is 100%{scope}",
        ),
        "inventory_boundary_precision": _gate(
            passed=_float(metrics.get("inventory_boundary_precision")) == 1.0,
            rule=f"inventory claim-boundary precision is 100%{scope}",
        ),
        "inventory_boundary_recall": _gate(
            passed=_float(metrics.get("inventory_boundary_recall")) == 1.0,
            rule=f"inventory claim-boundary recall is 100%{scope}",
        ),
        "inventory_full_precision": _gate(
            passed=_float(metrics.get("inventory_full_precision")) == 1.0,
            rule=f"inventory polarity/status precision is 100%{scope}",
        ),
        "inventory_full_recall": _gate(
            passed=_float(metrics.get("inventory_full_recall")) == 1.0,
            rule=f"inventory polarity/status recall is 100%{scope}",
        ),
        "unmatched_inventory_claims": _gate(
            passed=_integer(metrics.get("unmatched_inventory_claim_count")) == 0,
            rule=f"unsupported inventory claims are zero{scope}",
        ),
        "source_measurement_precision": _gate(
            passed=_float(metrics.get("source_measurement_precision")) == 1.0,
            rule=f"source-measurement precision is 100%{scope}",
        ),
        "source_measurement_recall": _gate(
            passed=_float(metrics.get("source_measurement_recall")) == 1.0,
            rule=f"source-measurement recall is 100%{scope}",
        ),
        "unmatched_outputs": _gate(
            passed=_integer(metrics.get("unmatched_output_count")) == 0,
            rule=f"unmatched output frames are zero{scope}",
        ),
        "unsupported_positive_outputs": _gate(
            passed=_integer(metrics.get("unsupported_positive_output_count")) == 0,
            rule=f"unsupported positive output frames are zero{scope}",
        ),
        "unsafe_assertive_upgrades": _gate(
            passed=_integer(metrics.get("unsafe_assertive_upgrade_count")) == 0,
            rule=f"non-assertive gold claims are never upgraded to ASSERTED{scope}",
        ),
        "positive_on_negative_or_null": _gate(
            passed=_integer(metrics.get("positive_on_negative_or_null_count")) == 0,
            rule=f"positive output on negative/null cases is zero{scope}",
        ),
        "agent_numeric_values": _gate(
            passed=_integer(metrics.get("agent_authored_numeric_value_count")) == 0,
            rule=f"agent-authored numeric values are rejected{scope}",
        ),
        "no_fallback": _gate(
            passed=_integer(metrics.get("fallback_output_count")) == 0,
            rule=f"strict reports contain no fallback output{scope}",
        ),
        "measurement_spans": _gate(
            passed=_integer(metrics.get("source_measurement_without_span_count")) == 0,
            rule=f"source measurements all have exact spans{scope}",
        ),
    }


def _gate(*, passed: bool, rule: str) -> JsonObject:
    return {"passed": passed, "rule": rule}


def _integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("required deterministic integer metric is missing or invalid")
    return value


def _float(value: object) -> float:
    if not isinstance(value, float | int) or isinstance(value, bool):
        raise TypeError("required deterministic rate metric is missing or invalid")
    return float(value)


__all__ = ["comparison_gates", "single_run_gates"]
