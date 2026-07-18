"""Audited agent comparison of a sealed expert event and extracted candidate."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    kernel_run_id_for_invocation,
)
from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    AuditedStructuredStepResult,
    StructuredModelSemanticError,
    run_audited_structured_step,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    ModelAttemptAuditContext,
    ModelStepResult,
    fingerprinted_step_key,
)

from scripts.validation.claim_events.finite_source_unit.representation_contracts import (
    RepresentationAdjudicationOutput,
)

if TYPE_CHECKING:
    from scripts.validation.claim_events.contracts import NaryClaimEvent
    from scripts.validation.claim_events.finite_source_unit.service import (
        FiniteSourceUnitModelClient,
    )

_PROMPT_VERSION = "tg04.representation_equivalence.v1"


@dataclass(frozen=True, slots=True)
class RepresentationAdjudicationRequest:
    """Immutable scientific context for one adjudicator invocation."""

    execution_namespace: str
    unit_id: str
    source_sha256: str
    source_text: str
    expert_event: NaryClaimEvent
    candidate_event: Mapping[str, object]


async def adjudicate_representation(
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    request: RepresentationAdjudicationRequest,
) -> AuditedStructuredStepResult[
    RepresentationAdjudicationOutput,
    RepresentationAdjudicationOutput,
]:
    """Run one categorical adjudicator after extraction has been frozen."""

    comparison_payload = _comparison_payload(
        expert_event=request.expert_event,
        candidate_event=request.candidate_event,
    )
    input_sha256 = _sha256_json(
        {"source": request.source_text, "comparison": comparison_payload},
    )
    prompt = _representation_prompt(
        unit_id=request.unit_id,
        source_text=request.source_text,
        comparison_payload=comparison_payload,
    )
    step_key = fingerprinted_step_key(
        _PROMPT_VERSION,
        model_id,
        input_sha256,
        request.execution_namespace,
    )

    async def invoke(invocation_id: str, provider_prompt: str) -> ModelStepResult:
        return await client.step(
            run_id=kernel_run_id_for_invocation(invocation_id),
            tenant=tenant,
            model=model_id,
            prompt=provider_prompt,
            output_schema=RepresentationAdjudicationOutput,
            step_key=step_key,
            replay_policy="fork_on_drift",
        )

    return await run_audited_structured_step(
        invoke_model=invoke,
        model_id=model_id,
        prompt=prompt,
        output_schema=RepresentationAdjudicationOutput,
        step_key=step_key,
        audit_context=ModelAttemptAuditContext(
            attempt_role="representation_adjudication",
            pass_role="representation_adjudication",  # noqa: S106
            retry_context=None,
            source_sha256=request.source_sha256,
            input_sha256=input_sha256,
            semantic_unit_id=request.unit_id,
        ),
        validate_semantics=lambda output: validate_representation_adjudication(
            output,
            source_text=request.source_text,
            expert_event=request.expert_event,
            candidate_event=request.candidate_event,
        ),
    )


def validate_representation_adjudication(
    output: RepresentationAdjudicationOutput,
    *,
    source_text: str,
    expert_event: NaryClaimEvent,
    candidate_event: Mapping[str, object],
) -> RepresentationAdjudicationOutput:
    """Require exact citations covering both full representations."""

    if any(span not in source_text for span in output.evidence_spans):
        raise StructuredModelSemanticError(
            "representation evidence must be exact frozen source text",
        )
    required_surfaces = (
        expert_event.trigger_span,
        *(argument.exact_span for argument in expert_event.arguments),
        _required_text(candidate_event, "trigger_span"),
        *(
            _required_text(argument, "exact_span")
            for argument in _candidate_arguments(candidate_event)
        ),
    )
    uncovered = tuple(
        surface
        for surface in required_surfaces
        if not any(surface in evidence for evidence in output.evidence_spans)
    )
    if uncovered:
        raise StructuredModelSemanticError(
            f"representation evidence does not cover material surfaces: {uncovered}",
        )
    return output


def _representation_prompt(
    *,
    unit_id: str,
    source_text: str,
    comparison_payload: dict[str, object],
) -> str:
    return f"""You are an independent biomedical representation adjudicator.

The extraction and exact benchmark scoring are already frozen. You cannot
change either. Use only the supplied source and compare the two representations.
Do not use outside knowledge. Do not return confidence, probability, quality,
importance, or any numeric score.

Return exactly one decision:
- ACCEPTABLE_ALTERNATE: both representations are fully source-entailed and
  preserve the same material scientific assertion despite compatible boundary,
  granularity, or ontology differences;
- PARTIAL: both are source-entailed but one loses or changes a material element;
- CONTRADICTS: they conflict in direction, polarity, or source support;
- UNRELATED: they describe different participants or scientific assertions;
- ABSTAIN: the relationship cannot be resolved safely.

Independently classify source support for the expert and candidate. Then answer
six hard questions categorically: trigger, direction, participants, causal role,
polarity, and epistemic status. For each axis use PRESERVED,
COMPATIBLE_REFINEMENT, MATERIAL_MISMATCH, or ABSTAIN. Demoting a material cause
to incidental context is a mismatch; retaining the same cause inside a more
specific treated-population phrase can be a compatible refinement. A gene and
its measured mRNA are compatible only when the source makes that measurement
explicit and the scientific direction is unchanged.

Copy exact source evidence spans that jointly cover both triggers and all
material participants. Explain the hardest possible objection to your decision
and state what source change would falsify it. The prior verifier decision is
intentionally omitted.

prompt_version: {_PROMPT_VERSION}
unit_id: {unit_id}

--- FROZEN SOURCE UNIT ---
{source_text}
--- END SOURCE UNIT ---

--- SEALED REPRESENTATIONS ---
{json.dumps(comparison_payload, indent=2, sort_keys=True, ensure_ascii=True)}
--- END REPRESENTATIONS ---
"""


def _comparison_payload(
    *,
    expert_event: NaryClaimEvent,
    candidate_event: Mapping[str, object],
) -> dict[str, object]:
    return {
        "expert_event": {
            "event_type": expert_event.event_type.value,
            "trigger_span": expert_event.trigger_span,
            "polarity": expert_event.polarity.value,
            "epistemic_status": expert_event.epistemic_status.value,
            "arguments": [
                {
                    "event_role": argument.event_role.value,
                    "participant_role": argument.participant_role.value,
                    "exact_span": argument.exact_span,
                }
                for argument in sorted(
                    expert_event.arguments,
                    key=lambda argument: argument.source_start,
                )
            ],
        },
        "candidate_event": {
            "event_type": _required_text(candidate_event, "event_type"),
            "trigger_span": _required_text(candidate_event, "trigger_span"),
            "polarity": _required_text(candidate_event, "polarity"),
            "epistemic_status": _required_text(
                candidate_event,
                "epistemic_status",
            ),
            "arguments": [
                {
                    "event_role": _required_text(argument, "event_role"),
                    "participant_role": _required_text(argument, "role"),
                    "exact_span": _required_text(argument, "exact_span"),
                }
                for argument in _candidate_arguments(candidate_event)
            ],
        },
    }


def _candidate_arguments(
    candidate_event: Mapping[str, object],
) -> tuple[Mapping[str, object], ...]:
    raw_arguments = candidate_event.get("arguments")
    if not isinstance(raw_arguments, list) or not raw_arguments:
        raise ValueError("candidate event requires arguments")
    if not all(isinstance(argument, dict) for argument in raw_arguments):
        raise TypeError("candidate event arguments must be objects")
    return tuple(argument for argument in raw_arguments if isinstance(argument, dict))


def _required_text(value: Mapping[str, object], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item:
        raise ValueError(f"representation field {field} must be text")
    return item


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8"),
    ).hexdigest()


__all__ = [
    "RepresentationAdjudicationRequest",
    "adjudicate_representation",
    "validate_representation_adjudication",
]
