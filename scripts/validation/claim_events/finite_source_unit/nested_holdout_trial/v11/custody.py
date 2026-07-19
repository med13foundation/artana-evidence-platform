"""Reconstruct V11 prompts, schemas, and chained step identities."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    bind_prompt_to_invocation,
    output_schema_json_sha256,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    fingerprinted_step_key,
)

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitExtractionOutput,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11 import (
    prompts as v11_prompts,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11.prompts import (
    V11_EXTRACTION_PROMPT_VERSION,
    V11_NORMALIZATION_PROMPT_VERSION,
    V11_NORMALIZED_REVIEW_PROMPT_VERSION,
    v11_normalization_prompt,
    v11_normalized_review_prompt,
    v11_source_unit_extraction_prompt,
)
from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    SourceUnitNormalizationOutput,
    SourceUnitNormalizedReviewOutput,
)
from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    bind_source_unit_normalization,
    canonical_json_sha256,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    bind_source_unit_extraction,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    FrozenSourceUnit,
)

V11_PROMPT_CONTENT_DIGESTS: Final[tuple[tuple[str, str], ...]] = (
    (
        "extraction_prompt_sha256",
        "8f3595602eea54021da42b2ca1cf0291ec5896c801a719b9fcc3be74adeebb15",
    ),
    (
        "v11_prompt_module_sha256",
        "8662a83f2aee248fb12d63a3dbcb038b36b487f6b588877ef8dc1b475db0aa5a",
    ),
)

_SCHEMAS: Final = (
    SourceUnitExtractionOutput,
    SourceUnitNormalizationOutput,
    SourceUnitNormalizedReviewOutput,
)
_ROLES: Final = ("primary", "structure_normalization", "normalized_review")
_NORMALIZATION_STAGE_COUNT: Final = 2
_REVIEW_STAGE_COUNT: Final = 3


def validate_v11_attempt_chain(
    report: dict[str, object],
    expected_evidence_unit_sha256: str,
) -> None:
    """Prove prompts, schemas, and step keys form one ordered dependency chain."""

    unit = _unit(report)
    outputs = _dict(report, "agent_outputs")
    if isinstance(outputs.get("error_type"), str):
        _validate_terminal_failure_chain(
            report=report,
            unit=unit,
            outputs=outputs,
            expected_evidence_unit_sha256=expected_evidence_unit_sha256,
        )
        return
    raw_outputs = _dict(report, "raw_agent_outputs")
    original_payload = _dict(outputs, "original_extraction")
    normalized_payload = _dict(outputs, "normalized_extraction")
    review_payload = _dict(outputs, "normalized_review")
    original_raw = _dict(raw_outputs, "original_extraction")
    normalized_raw = _dict(raw_outputs, "normalized_extraction")
    if canonical_json_sha256(original_payload) != canonical_json_sha256(original_raw):
        raise RuntimeError("V11 original raw output custody changed")
    if canonical_json_sha256(normalized_payload) != canonical_json_sha256(
        normalized_raw
    ):
        raise RuntimeError("V11 normalized raw output custody changed")

    original_output = SourceUnitExtractionOutput.model_validate(original_payload)
    original = bind_source_unit_extraction(original_output, unit=unit)
    normalized_output = SourceUnitNormalizationOutput.model_validate(normalized_payload)
    normalized = bind_source_unit_normalization(
        normalized_output,
        unit=unit,
        original=original,
    )
    SourceUnitNormalizedReviewOutput.model_validate(review_payload)
    prompts = (
        v11_source_unit_extraction_prompt(unit),
        v11_normalization_prompt(unit=unit, original=original),
        v11_normalized_review_prompt(
            unit=unit,
            original=original,
            normalized=normalized,
        ),
    )
    require_v11_prompt_preregistration(prompts[0])

    model_id = _string(report, "execution_model_id")
    step_keys = (
        fingerprinted_step_key(
            V11_EXTRACTION_PROMPT_VERSION,
            model_id,
            unit.input_sha256,
            expected_evidence_unit_sha256,
        ),
        fingerprinted_step_key(
            V11_NORMALIZATION_PROMPT_VERSION,
            model_id,
            unit.input_sha256,
            canonical_json_sha256(original_raw),
            expected_evidence_unit_sha256,
        ),
        fingerprinted_step_key(
            V11_NORMALIZED_REVIEW_PROMPT_VERSION,
            model_id,
            unit.input_sha256,
            canonical_json_sha256(original_raw),
            canonical_json_sha256(normalized_raw),
            expected_evidence_unit_sha256,
        ),
    )
    attempts = report.get("attempts")
    if not isinstance(attempts, list) or len(attempts) != len(_ROLES):
        raise RuntimeError("V11 chained custody requires exactly three attempts")
    schema_hashes = tuple(output_schema_json_sha256(schema) for schema in _SCHEMAS)
    receipts = _receipts_by_response_id(report)
    for attempt, role, prompt, step_key, schema, schema_sha256 in zip(
        attempts,
        _ROLES[: len(attempts)],
        prompts,
        step_keys,
        _SCHEMAS[: len(attempts)],
        schema_hashes[: len(attempts)],
        strict=True,
    ):
        if not isinstance(attempt, dict):
            raise TypeError("V11 attempt must be an object")
        invocation_id = _string(attempt, "invocation_id")
        bound_prompt = bind_prompt_to_invocation(
            prompt=prompt,
            invocation_id=invocation_id,
            source_sha256=unit.source_sha256,
            input_sha256=unit.input_sha256,
            evidence_unit_sha256=expected_evidence_unit_sha256,
            output_schema_sha256=schema_sha256,
        )
        expected_schema_identity = f"{schema.__module__}.{schema.__qualname__}"
        if (
            attempt.get("attempt_role") != role
            or attempt.get("step_key") != step_key
            or attempt.get("prompt_sha256") != _sha256_text(bound_prompt)
            or attempt.get("output_schema_identity") != expected_schema_identity
        ):
            raise RuntimeError(
                "V11 attempt prompt, schema, or dependency chain changed"
            )
        response_id = _string(attempt, "provider_response_id")
        receipt = receipts.get(response_id)
        if (
            receipt is None
            or receipt.get("expected_output_schema_sha256") != schema_sha256
            or receipt.get("retrieved_output_schema_sha256") != schema_sha256
        ):
            raise RuntimeError("V11 provider schema custody changed")


def _validate_terminal_failure_chain(  # noqa: PLR0914
    *,
    report: dict[str, object],
    unit: FrozenSourceUnit,
    outputs: dict[str, object],
    expected_evidence_unit_sha256: str,
) -> None:
    attempts = report.get("attempts")
    if not isinstance(attempts, list) or not 1 <= len(attempts) <= len(_ROLES):
        raise RuntimeError("V11 terminal chain requires one failed attempt prefix")
    raw_outputs = _dict(report, "raw_agent_outputs")
    prompts = [v11_source_unit_extraction_prompt(unit)]
    model_id = _string(report, "execution_model_id")
    step_keys = [
        fingerprinted_step_key(
            V11_EXTRACTION_PROMPT_VERSION,
            model_id,
            unit.input_sha256,
            expected_evidence_unit_sha256,
        )
    ]
    if len(attempts) >= _NORMALIZATION_STAGE_COUNT:
        original_payload = _dict(outputs, "original_extraction")
        original_raw = _dict(raw_outputs, "original_extraction")
        original = bind_source_unit_extraction(
            SourceUnitExtractionOutput.model_validate(original_payload),
            unit=unit,
        )
        prompts.append(v11_normalization_prompt(unit=unit, original=original))
        step_keys.append(
            fingerprinted_step_key(
                V11_NORMALIZATION_PROMPT_VERSION,
                model_id,
                unit.input_sha256,
                canonical_json_sha256(original_raw),
                expected_evidence_unit_sha256,
            )
        )
    if len(attempts) >= _REVIEW_STAGE_COUNT:
        normalized_payload = _dict(outputs, "normalized_extraction")
        normalized_raw = _dict(raw_outputs, "normalized_extraction")
        original_payload = _dict(outputs, "original_extraction")
        original = bind_source_unit_extraction(
            SourceUnitExtractionOutput.model_validate(original_payload),
            unit=unit,
        )
        normalized = bind_source_unit_normalization(
            SourceUnitNormalizationOutput.model_validate(normalized_payload),
            unit=unit,
            original=original,
        )
        prompts.append(
            v11_normalized_review_prompt(
                unit=unit,
                original=original,
                normalized=normalized,
            )
        )
        step_keys.append(
            fingerprinted_step_key(
                V11_NORMALIZED_REVIEW_PROMPT_VERSION,
                model_id,
                unit.input_sha256,
                canonical_json_sha256(_dict(raw_outputs, "original_extraction")),
                canonical_json_sha256(normalized_raw),
                expected_evidence_unit_sha256,
            )
        )
    require_v11_prompt_preregistration(prompts[0])
    receipts = _receipts_by_response_id(report)
    schema_hashes = tuple(output_schema_json_sha256(schema) for schema in _SCHEMAS)
    for attempt, role, prompt, step_key, schema, schema_sha256 in zip(
        attempts,
        _ROLES[: len(attempts)],
        prompts,
        step_keys,
        _SCHEMAS[: len(attempts)],
        schema_hashes[: len(attempts)],
        strict=True,
    ):
        if not isinstance(attempt, dict):
            raise TypeError("V11 attempt must be an object")
        bound_prompt = bind_prompt_to_invocation(
            prompt=prompt,
            invocation_id=_string(attempt, "invocation_id"),
            source_sha256=unit.source_sha256,
            input_sha256=unit.input_sha256,
            evidence_unit_sha256=expected_evidence_unit_sha256,
            output_schema_sha256=schema_sha256,
        )
        if (
            attempt.get("attempt_role") != role
            or attempt.get("step_key") != step_key
            or attempt.get("prompt_sha256") != _sha256_text(bound_prompt)
            or attempt.get("output_schema_identity")
            != f"{schema.__module__}.{schema.__qualname__}"
        ):
            raise RuntimeError("V11 terminal prompt or dependency chain changed")
        response_id = attempt.get("provider_response_id")
        if response_id is None:
            continue
        if not isinstance(response_id, str):
            raise TypeError("V11 provider response identity must be a string")
        receipt = receipts.get(response_id)
        if (
            receipt is None
            or receipt.get("expected_output_schema_sha256") != schema_sha256
            or receipt.get("retrieved_output_schema_sha256") != schema_sha256
        ):
            raise RuntimeError("V11 terminal provider schema custody changed")


def require_v11_prompt_preregistration(extraction_prompt: str) -> None:
    """Require the exact extraction prompt and complete V11 prompt module."""

    observed = (
        ("extraction_prompt_sha256", _sha256_text(extraction_prompt)),
        (
            "v11_prompt_module_sha256",
            hashlib.sha256(Path(v11_prompts.__file__).read_bytes()).hexdigest(),
        ),
    )
    if observed != V11_PROMPT_CONTENT_DIGESTS:
        raise RuntimeError("V11 prompt content differs from preregistration")


def _unit(report: dict[str, object]) -> FrozenSourceUnit:
    value = _dict(report, "unit")
    return FrozenSourceUnit(
        unit_id=_string(value, "unit_id"),
        index=_integer(value, "unit_index"),
        source_start=_integer(value, "source_start"),
        source_end=_integer(value, "source_end"),
        text=_string(value, "text"),
        source_sha256=_string(value, "source_sha256"),
    )


def _receipts_by_response_id(
    report: dict[str, object],
) -> dict[str, dict[str, object]]:
    provider_receipts = _dict(report, "provider_receipts")
    receipts = provider_receipts.get("receipts")
    if not isinstance(receipts, list):
        raise TypeError("V11 provider receipts must be a list")
    indexed: dict[str, dict[str, object]] = {}
    for receipt in receipts:
        if not isinstance(receipt, dict):
            raise TypeError("V11 provider receipt must be an object")
        response_id = _string(receipt, "response_id")
        indexed[response_id] = receipt
    return indexed


def _dict(value: dict[str, object], key: str) -> dict[str, object]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise TypeError(f"V11 {key} must be an object")
    return item


def _string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise TypeError(f"V11 {key} must be a string")
    return item


def _integer(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise TypeError(f"V11 {key} must be an integer")
    return item


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "V11_PROMPT_CONTENT_DIGESTS",
    "require_v11_prompt_preregistration",
    "validate_v11_attempt_chain",
]
