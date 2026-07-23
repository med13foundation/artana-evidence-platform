"""Immutable operational diagnosis and run-1 report correction artifacts."""

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

RUN1_SEALED_SHA256 = {
    "preregistration": (
        "1beb0e30c5fa26c429259bcf7d72c8629b534488200b14808a34cc93df28bf5b"
    ),
    "result": (
        "07dafb681ec7fd597f01a619eddfb12e27aadc959136cdecf83db1632f7b8e3d"
    ),
    "report": (
        "48036e762a548840746a3c788404ecf0115e9d3f2e445f4a7c3b63fa4766b655"
    ),
    "seal": (
        "e7063b1e4eb0a88ebc4c618f227358ac1c7ab60757dd06e6269a492bcd9184c4"
    ),
    "attempt": (
        "f2cc4adc252a0e0d25e3e6690cd760f955a70487758bad8bb6283cd1d4ec78f4"
    ),
    "late_status": (
        "4b762538ce06ef7250c271055cd5b1dc6da4c723459dda3e575c1ad07da13fd1"
    ),
}
_ROOT_CAUSE = "SEMANTIC_EVIDENCE_PROMPT_CONTRACT_GAP"
_SCIENTIFIC_CHANGE = "UNIQUE_COMPLETE_SEMANTIC_EVIDENCE_GROUNDING"
_RUN1_RESPONSE_ID = "resp_0ea84656be41ad54006a61b0916e4c8199bec1041422465f06"


class V11Run2ArtifactError(RuntimeError):
    """An operational artifact conflicts with the sealed V11 history."""


def operational_diagnosis() -> dict[str, object]:
    """Return the frozen, evidence-limited run-1 queue diagnosis."""

    return {
        "schema_version": (
            "artana.staged_generalization.v11_run1_queue_diagnosis.v1"
        ),
        "experiment_id": "staged-generalization-v11-exposed-run-v1",
        "classification": "PROVIDER_QUEUE_STALL",
        "internal_provider_root_cause": "UNKNOWN",
        "scientific_disposition": "INVALID_UNSCORED_DIAGNOSTIC_ONLY",
        "evidence": {
            "response_id": _RUN1_RESPONSE_ID,
            "attempt_state": "ACKNOWLEDGED",
            "creation_calls": 1,
            "provider_retries": 0,
            "duplicate_creation_calls": 0,
            "polling_retrieval_requests": 170,
            "polling_seconds": 900.0100377080016,
            "terminal_failure_stage": "BACKGROUND_POLLING_TIMEOUT",
            "sealed_late_status": "queued",
            "sealed_late_status_retrieval_at": "2026-07-23T06:27:21Z",
            "current_read_only_status": "queued",
            "current_read_only_retrieval_at": (
                "2026-07-23T15:07:25.825693+00:00"
            ),
            "current_usage_available": False,
            "current_provider_error": None,
            "current_incomplete_details": None,
        },
        "provider_contract_interpretation": {
            "installed_openai_python_version": "2.44.0",
            "official_documentation": (
                "https://developers.openai.com/api/docs/guides/background"
            ),
            "documented_background_behavior": (
                "background=true is asynchronous and clients retrieve while "
                "status is queued or in_progress"
            ),
            "local_poller_conformed_to_documented_states": True,
            "provider_internal_cause_claimed": False,
        },
        "transport_decision": {
            "smallest_change": (
                "DIRECT_OPENAI_FOREGROUND_RESPONSES_WITH_SYNTHETIC_QUALIFICATION"
            ),
            "scientific_contract_changed": False,
            "background": False,
            "model": "openai:gpt-5.6-luna",
            "reasoning_effort": "high",
            "provider_retries": 0,
            "fallback": False,
            "one_creation_call": True,
            "response_id_custody": True,
            "confirmation_retrieval": True,
            "input_item_retrieval": True,
            "application_max_output_tokens": None,
            "application_max_total_tokens": None,
        },
        "run1_invariants": {
            "late_output_scientifically_admissible": False,
            "late_output_rescore_authorized": False,
            "sealed_result_rewrite_authorized": False,
            "sealed_sha256": RUN1_SEALED_SHA256,
        },
    }


def report_correction() -> str:
    """Return the append-only correction for the immutable run-1 report."""

    return (
        "# V11 Exposed Run 1 Final-Report Correction\n\n"
        "The sealed final report rendered `None` for both the root-cause "
        "classification and the single V11 scientific change. This was a "
        "report-generation defect: the invalid-terminal result omitted fields "
        "that the renderer expected, even though both values were frozen in "
        "the preregistration and repeated in the seal report.\n\n"
        "The correct preregistered root-cause classification is "
        f"`{_ROOT_CAUSE}`.\n\n"
        "The correct frozen V11 scientific change is "
        f"`{_SCIENTIFIC_CHANGE}`.\n\n"
        "V11 exposed run 1 was operationally invalid before any provider output "
        "was scientifically admitted. Therefore neither the root-cause "
        "hypothesis nor the V11 change was scientifically validated by run 1. "
        "This correction supplies missing report context only; it does not "
        "change, rescore, reinterpret, or replace the sealed run-1 result.\n\n"
        "The original run-1 preregistration, result, final report, seal report, "
        "attempt receipt, and late-status receipt remain byte-identical. Their "
        "frozen SHA-256 values are recorded in the run-2 operational diagnosis "
        "and preregistration.\n"
    )


def write_operational_artifacts(paths: V11Run2Paths = DEFAULT_PATHS) -> None:
    """Write forward-only diagnosis and correction artifacts."""

    write_json_atomic(paths.operational_diagnosis, operational_diagnosis())
    paths.report_correction.parent.mkdir(parents=True, exist_ok=True)
    paths.report_correction.write_text(report_correction(), encoding="utf-8")


def verify_operational_artifacts(
    paths: V11Run2Paths = DEFAULT_PATHS,
) -> None:
    """Verify new evidence and every sealed run-1 byte boundary."""

    sealed_paths = {
        "preregistration": paths.run1_preregistration,
        "result": paths.run1_result,
        "report": paths.run1_report,
        "seal": paths.run1_seal,
        "attempt": paths.run1_attempt,
        "late_status": paths.run1_late_status,
    }
    observed = {name: _sha256(path) for name, path in sealed_paths.items()}
    if observed != RUN1_SEALED_SHA256:
        raise V11Run2ArtifactError("sealed V11 run-1 artifacts changed")
    diagnosis = json.loads(paths.operational_diagnosis.read_text(encoding="utf-8"))
    if diagnosis != operational_diagnosis():
        raise V11Run2ArtifactError("run-1 operational diagnosis changed")
    if paths.report_correction.read_text(encoding="utf-8") != report_correction():
        raise V11Run2ArtifactError("run-1 report correction changed")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "RUN1_SEALED_SHA256",
    "V11Run2ArtifactError",
    "operational_diagnosis",
    "report_correction",
    "verify_operational_artifacts",
    "write_operational_artifacts",
]
