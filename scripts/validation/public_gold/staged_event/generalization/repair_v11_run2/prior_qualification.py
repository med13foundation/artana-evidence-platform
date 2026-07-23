"""Seal rejected qualification v1 and its recovered record-only usage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    write_json_atomic,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.config import (
    DEFAULT_PATHS,
    V11Run2Paths,
)

_PREREGISTRATION_SHA256 = (
    "63c7cdde30c26a845b9901aa93811df49612783ed34fd91537ca1610022ffc15"
)
_ATTEMPT_SHA256 = (
    "cae87a7beca842c60f7cf9b34295d00a2ec23adf331bbea82d75a6ddd7afb95e"
)
_RESULT_SHA256 = (
    "84a8af97b92fbfca95c991518acb09b2739d073ef8055b18ac3dec2ea5521263"
)
_RESPONSE_ID = "resp_04e41854e026a9cb006a62315dcc7481999537dce276482960"
_V2_PREREGISTRATION_SHA256 = (
    "cad8378b5a869cab21c230dd84aac50d3587603111ec1335addd11c61e81b4aa"
)
_V2_ATTEMPT_SHA256 = (
    "bb1ebae7eee41ba9ebe89bfd952b12ed528f5540c40fbfd2a25d97ed83c5d26e"
)
_V2_RESULT_SHA256 = (
    "057e546253066f4d426017e8208107a1157456c454e714a01eab7b48ecf38db9"
)
_V2_RESPONSE_ID = "resp_066d3cf239bde6c7006a6233276d84819b96e7d31389334b8d"


class PriorQualificationError(RuntimeError):
    """Rejected qualification evidence changed or lost usage."""


def usage_addendum() -> dict[str, object]:
    """Return the frozen read-only usage observation for qualification v1."""

    return {
        "schema_version": (
            "artana.staged_generalization."
            "v11_foreground_qualification_usage_addendum.v1"
        ),
        "experiment_id": (
            "staged-generalization-v11-foreground-qualification-v1"
        ),
        "decision": "INVALID_FOREGROUND_TRANSPORT_QUALIFICATION",
        "failure_stage": "RECEIPT_USAGE",
        "failure_interpretation": (
            "creation and confirmation full usage snapshots differed; "
            "scientific identity, input, schema, payload, and custody were not "
            "admitted by this qualification"
        ),
        "response_id": _RESPONSE_ID,
        "read_only_retrieval_at": "2026-07-23T15:22:02.767659+00:00",
        "provider_status": "completed",
        "provider_error": None,
        "provider_incomplete_details": None,
        "usage": {
            "input_tokens": 1358,
            "cached_input_tokens": 0,
            "output_tokens": 288,
            "reasoning_tokens": 79,
            "total_tokens": 1646,
            "latency_seconds": 6.5658,
            "cost_usd": 0.003086,
        },
        "provider_creation_calls": 1,
        "provider_retries": 0,
        "duplicate_creation_calls": 0,
        "scientific_credit": False,
        "scientific_case_calls": 0,
        "fresh_cases_consumed": 0,
        "graph_writes": 0,
        "sealed_sha256": {
            "preregistration": _PREREGISTRATION_SHA256,
            "attempt": _ATTEMPT_SHA256,
            "result": _RESULT_SHA256,
        },
    }


def write_usage_addendum(paths: V11Run2Paths = DEFAULT_PATHS) -> None:
    """Persist both forward-only telemetry addenda."""

    _verify_sealed_v1(paths)
    write_json_atomic(
        paths.prior_qualification_usage_addendum,
        usage_addendum(),
    )
    _verify_sealed_v2(paths)
    write_json_atomic(
        paths.prior_qualification_v2_usage_addendum,
        usage_addendum_v2(),
    )


def verify_prior_qualification(
    paths: V11Run2Paths = DEFAULT_PATHS,
) -> dict[str, object]:
    """Verify invalid v1 and its immutable usage addendum."""

    _verify_sealed_v1(paths)
    loaded = _object(
        json.loads(
            paths.prior_qualification_usage_addendum.read_text(
                encoding="utf-8"
            )
        )
    )
    if loaded != usage_addendum():
        raise PriorQualificationError("qualification v1 usage addendum changed")
    return loaded


def usage_addendum_v2() -> dict[str, object]:
    """Return qualification v2's observed rejected-call telemetry."""

    return {
        "schema_version": (
            "artana.staged_generalization."
            "v11_foreground_qualification_usage_addendum.v2"
        ),
        "experiment_id": (
            "staged-generalization-v11-foreground-qualification-v2"
        ),
        "decision": "INVALID_FOREGROUND_TRANSPORT_QUALIFICATION",
        "failure_stage": "RECEIPT_ENVELOPE",
        "failure_interpretation": (
            "creation included opaque encrypted reasoning transport content "
            "that confirmation retrieval omitted; the strict historical "
            "envelope policy rejected the non-scientific difference"
        ),
        "response_id": _V2_RESPONSE_ID,
        "provider_status": "completed",
        "provider_error": None,
        "provider_incomplete_details": None,
        "usage": {
            "input_tokens": 1358,
            "cached_input_tokens": 1355,
            "output_tokens": 250,
            "reasoning_tokens": 43,
            "total_tokens": 1608,
            "latency_seconds": 3.545299667006475,
            "cost_usd": 0.0016385,
        },
        "provider_creation_calls": 1,
        "provider_retries": 0,
        "duplicate_creation_calls": 0,
        "scientific_credit": False,
        "scientific_case_calls": 0,
        "fresh_cases_consumed": 0,
        "graph_writes": 0,
        "sealed_sha256": {
            "preregistration": _V2_PREREGISTRATION_SHA256,
            "attempt": _V2_ATTEMPT_SHA256,
            "result": _V2_RESULT_SHA256,
        },
    }


def verify_prior_qualifications(
    paths: V11Run2Paths = DEFAULT_PATHS,
) -> tuple[dict[str, object], dict[str, object]]:
    """Verify both rejected qualifications and cumulative usage evidence."""

    first = verify_prior_qualification(paths)
    _verify_sealed_v2(paths)
    second = _object(
        json.loads(
            paths.prior_qualification_v2_usage_addendum.read_text(
                encoding="utf-8"
            )
        )
    )
    if second != usage_addendum_v2():
        raise PriorQualificationError("qualification v2 usage addendum changed")
    return first, second


def _verify_sealed_v1(paths: V11Run2Paths) -> None:
    observed = {
        "preregistration": _sha256(paths.prior_qualification.preregistration),
        "attempt": _sha256(paths.prior_qualification.attempt),
        "result": _sha256(paths.prior_qualification.result),
    }
    expected = {
        "preregistration": _PREREGISTRATION_SHA256,
        "attempt": _ATTEMPT_SHA256,
        "result": _RESULT_SHA256,
    }
    if observed != expected:
        raise PriorQualificationError("qualification v1 artifacts changed")
    if paths.prior_qualification.bundle.exists():
        raise PriorQualificationError("invalid qualification v1 gained custody")
    if paths.prior_qualification.receipt.exists():
        raise PriorQualificationError("invalid qualification v1 gained a receipt")
    if paths.prior_qualification.raw_output.exists():
        raise PriorQualificationError("invalid qualification v1 gained raw output")


def _verify_sealed_v2(paths: V11Run2Paths) -> None:
    observed = {
        "preregistration": _sha256(
            paths.prior_qualification_v2.preregistration
        ),
        "attempt": _sha256(paths.prior_qualification_v2.attempt),
        "result": _sha256(paths.prior_qualification_v2.result),
    }
    expected = {
        "preregistration": _V2_PREREGISTRATION_SHA256,
        "attempt": _V2_ATTEMPT_SHA256,
        "result": _V2_RESULT_SHA256,
    }
    if observed != expected:
        raise PriorQualificationError("qualification v2 artifacts changed")
    if paths.prior_qualification_v2.bundle.exists():
        raise PriorQualificationError("invalid qualification v2 gained custody")
    if paths.prior_qualification_v2.receipt.exists():
        raise PriorQualificationError("invalid qualification v2 gained a receipt")
    if paths.prior_qualification_v2.raw_output.exists():
        raise PriorQualificationError("invalid qualification v2 gained raw output")


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PriorQualificationError("expected JSON object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "PriorQualificationError",
    "usage_addendum",
    "usage_addendum_v2",
    "verify_prior_qualification",
    "verify_prior_qualifications",
    "write_usage_addendum",
]
