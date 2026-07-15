"""Strict one-pass execution of the production relation extractor."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final
from uuid import uuid4

from scripts.validation.claim_frames.evidence import (
    REQUIRED_MODEL_ID,
    collect_repository_evidence,
)
from scripts.validation.claim_frames.inventory_scoring import evaluate_inventory
from scripts.validation.claim_frames.metrics import build_run_report, evaluate_case

if TYPE_CHECKING:
    from scripts.validation.claim_frames.fixture import BenchmarkFixture

_SPACE_CONTEXT: Final = "TG-03 frozen ClaimFrame qualifier benchmark."
_REPO_ROOT: Final = Path(__file__).resolve().parents[3]
_REQUIRED_MODEL_ID: Final = REQUIRED_MODEL_ID


@dataclass(frozen=True, slots=True)
class _RunConfiguration:
    run_id: str
    model_id: str
    prompt_version: str
    generated_at: datetime
    repository_evidence: Mapping[str, object]


def run_live_benchmark(
    *,
    fixture: BenchmarkFixture,
    run_id: str,
    model_id: str,
    prompt_version: str,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """Run each frozen case once through the strict production extractor."""

    repository_evidence = collect_repository_evidence(_REPO_ROOT)
    if repository_evidence["clean"] is not True:
        raise RuntimeError(
            "TG-03 live benchmark requires a clean tracked worktree; "
            "offline JSON cannot authenticate a dirty-tree run",
        )

    return asyncio.run(
        _run_live_benchmark(
            fixture=fixture,
            configuration=_RunConfiguration(
                run_id=run_id,
                model_id=model_id,
                prompt_version=prompt_version,
                generated_at=generated_at or datetime.now(UTC),
                repository_evidence=repository_evidence,
            ),
        ),
    )


async def _run_live_benchmark(
    *,
    fixture: BenchmarkFixture,
    configuration: _RunConfiguration,
) -> dict[str, object]:
    from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
        start_model_attempt_audit,
        stop_model_attempt_audit,
    )
    from artana_evidence_api.document_extraction_support.strict_relation_discovery import (
        discover_relation_candidates_strict,
    )

    case_results: list[dict[str, object]] = []
    for case in fixture.cases:
        invocation_id = f"tg03-invocation-{uuid4().hex}"
        audit_session = start_model_attempt_audit()
        try:
            raw_output: dict[str, object]
            candidates, diagnostics = await discover_relation_candidates_strict(
                case.source_text,
                max_relations=10,
                space_context=_SPACE_CONTEXT,
                execution_namespace=invocation_id,
            )
            frame_payloads = tuple(
                candidate.claim_frame.model_dump(mode="json")
                for candidate in candidates
                if candidate.claim_frame is not None
            )
            postprocessed_output = {
                "relations": [
                    _candidate_payload(candidate) for candidate in candidates
                ],
            }
            raw_output = {
                "attempts": [record.as_json() for record in audit_session.records],
                "accepted_pass_payloads": list(
                    getattr(candidates, "raw_agent_outputs", ()),
                ),
            }
            diagnostic_payload: dict[str, object] = {
                "llm_candidate_status": diagnostics.llm_candidate_status,
                "llm_candidate_count": diagnostics.llm_candidate_count,
                "fallback_candidate_count": diagnostics.fallback_candidate_count,
                "pruned_generic_relation_count": (
                    diagnostics.pruned_generic_relation_count
                ),
                "quality_filtered_candidate_count": (
                    diagnostics.quality_filtered_candidate_count
                ),
                "llm_extraction_chunk_count": diagnostics.llm_extraction_chunk_count,
                "llm_extraction_text_char_count": (
                    diagnostics.llm_extraction_text_char_count
                ),
                "claim_extraction_routing_status": (
                    diagnostics.claim_extraction_routing_status
                ),
                "candidate_overflow_count": diagnostics.candidate_overflow_count,
            }
            agent_invocation_completed = diagnostics.llm_candidate_status in {
                "completed",
                "llm_empty",
            }
            strict_usable_extraction_completed = (
                diagnostics.llm_candidate_status == "completed"
                and diagnostics.claim_extraction_routing_status == "complete"
                and diagnostics.candidate_overflow_count == 0
            )
        except Exception as exc:  # noqa: BLE001 - report a fail-closed run result.
            frame_payloads = ()
            raw_output = {
                "attempts": [record.as_json() for record in audit_session.records],
                "accepted_pass_payloads": [],
                "strict_error_type": type(exc).__name__,
            }
            postprocessed_output = {"relations": []}
            diagnostic_payload = {
                "llm_candidate_status": "unavailable",
                "llm_candidate_count": 0,
                "fallback_candidate_count": 0,
                "pruned_generic_relation_count": 0,
                "quality_filtered_candidate_count": 0,
                "llm_extraction_chunk_count": 0,
                "llm_extraction_text_char_count": 0,
                "claim_extraction_routing_status": "semantic_incomplete",
                "candidate_overflow_count": 0,
                "strict_error": "live extraction did not complete",
            }
            agent_invocation_completed = False
            strict_usable_extraction_completed = False
        finally:
            stop_model_attempt_audit(audit_session)
        model_attempt_invocation_ids = _model_attempt_invocation_ids(
            raw_output,
            require_nonempty=agent_invocation_completed,
        )
        evaluated = evaluate_case(case, frame_payloads)
        evaluated.update(evaluate_inventory(case, raw_output))
        evaluated.update(
            {
                "invocation_id": invocation_id,
                "invocation_namespace": invocation_id,
                "model_attempt_invocation_ids": list(model_attempt_invocation_ids),
                "frames": list(frame_payloads),
                "raw_agent_output": raw_output,
                "postprocessed_candidate_output": postprocessed_output,
                "diagnostics": diagnostic_payload,
                "agent_invocation_completed": agent_invocation_completed,
                "strict_usable_extraction_completed": (
                    strict_usable_extraction_completed
                ),
                "fallback_output_count": int(
                    _is_positive_int(
                        diagnostic_payload.get("fallback_candidate_count"),
                    )
                    or diagnostic_payload.get("llm_candidate_status")
                    in {"fallback", "fallback_error", "unavailable"}
                ),
                "output_sha256": _sha256_json(raw_output),
                "postprocessed_output_sha256": _sha256_json(
                    postprocessed_output,
                ),
            },
        )
        case_results.append(evaluated)

    final_repository_evidence = collect_repository_evidence(_REPO_ROOT)
    if final_repository_evidence != configuration.repository_evidence:
        raise RuntimeError(
            "TG-03 repository state changed during the live benchmark",
        )

    return build_run_report(
        fixture=fixture,
        run_id=configuration.run_id,
        generated_at=configuration.generated_at,
        model_id=configuration.model_id,
        prompt_version=configuration.prompt_version,
        case_results=case_results,
        repository_evidence=configuration.repository_evidence,
    )


def configured_model_id() -> str:
    """Read the configured evidence-extraction model identifier."""

    from artana_evidence_api.runtime import ModelCapability, get_model_registry

    model = get_model_registry().get_default_model(ModelCapability.EVIDENCE_EXTRACTION)
    model_id = model.model_id
    if model_id != _REQUIRED_MODEL_ID:
        raise RuntimeError(
            "TG-03 live audit requires "
            f"{_REQUIRED_MODEL_ID}; configured model is {model_id}.",
        )
    return model_id


def _candidate_payload(candidate: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "subject": getattr(candidate, "subject_label", ""),
        "relation_type": getattr(candidate, "relation_type", ""),
        "object": getattr(candidate, "object_label", ""),
        "sentence": getattr(candidate, "sentence", ""),
        "review_status": getattr(candidate, "review_status", ""),
        "review_reason_codes": list(
            getattr(candidate, "review_reason_codes", ()),
        ),
    }
    frame = getattr(candidate, "claim_frame", None)
    if frame is not None:
        payload["claim_frame"] = frame.model_dump(mode="json")
    return payload


def _sha256_json(value: Mapping[str, object]) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _model_attempt_invocation_ids(
    raw_output: Mapping[str, object],
    *,
    require_nonempty: bool,
) -> tuple[str, ...]:
    attempts = raw_output.get("attempts")
    if not isinstance(attempts, list):
        raise TypeError("strict extraction model-attempt records must be a list")
    if require_nonempty and not attempts:
        raise RuntimeError("strict extraction produced no model-attempt audit records")
    invocation_ids: list[str] = []
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise TypeError("model-attempt audit record must be an object")
        if attempt.get("validation_outcome") == "intentionally_skipped":
            continue
        invocation_id = attempt.get("invocation_id")
        if not isinstance(invocation_id, str) or not invocation_id:
            raise ValueError("model-attempt audit record lacks invocation_id")
        invocation_ids.append(invocation_id)
    if len(invocation_ids) != len(set(invocation_ids)):
        raise ValueError("model-attempt invocation IDs must be unique per case")
    return tuple(invocation_ids)


__all__ = ["configured_model_id", "run_live_benchmark"]
