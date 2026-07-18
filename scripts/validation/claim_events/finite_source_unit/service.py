"""Audited extraction and verification for finite TG-04 source units."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

from artana_evidence_api.document_extraction_support.claim_frames import (
    BoundClaimInventoryItem,
    ClaimInventoryBindingRejection,
    bind_claim_inventory_items,
)
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

from scripts.validation.claim_events.finite_source_unit.contracts import (
    CandidateVerification,
    EntailmentDecision,
    SourceUnitCoverageDecision,
    SourceUnitExtractionOutput,
    SourceUnitVerificationOutput,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )

_EXTRACTION_PROMPT_VERSION = "tg04.finite_source_unit.extraction.v9"
_VERIFICATION_PROMPT_VERSION = "tg04.finite_source_unit.verification.v8"
_SCIENTIFIC_EVENT_ELIGIBILITY_POLICY = """SCIENTIFIC EVENT ELIGIBILITY POLICY
Classify source meaning, never section labels, keywords, or perceived importance.
Return exactly one eligibility_category:
- FINDING: an asserted biological relationship or result;
- HYPOTHESIS: an explicitly proposed biological explanation or mechanism;
- NULL_RESULT: an explicit no-effect, no-association, or threshold-failing result;
- PROCEDURE: sample handling, preparation, intervention application, assay setup,
  instrument use, or another action without a reported biological result;
- MEASUREMENT_ONLY: an outcome is measured but no value, direction, comparison,
  or conclusion is reported;
- NO_EVENT: none of the categories above is explicit;
- ABSTAIN: the source cannot safely resolve the category.

Only FINDING, HYPOTHESIS, and NULL_RESULT are scientific events. PROCEDURE and
MEASUREMENT_ONLY remain visible categorical findings but are excluded from the
scientific-event inventory. A methods sentence is scientific only when it
reports a biological result or explicitly proposes a mechanism."""


class FiniteSourceUnitModelClient(Protocol):
    """Model-client surface required by the sealed diagnostic."""

    async def step(  # noqa: PLR0913
        self,
        *,
        run_id: str,
        tenant: object,
        model: str,
        prompt: str,
        output_schema: type[BaseModel],
        step_key: str,
        replay_policy: str,
    ) -> ModelStepResult: ...


@dataclass(frozen=True, slots=True)
class SourceUnitExtractionResult:
    """Schema-valid categorical output plus item-level source binding."""

    output: SourceUnitExtractionOutput
    accepted: tuple[BoundClaimInventoryItem, ...]
    rejected: tuple[ClaimInventoryBindingRejection, ...]


@dataclass(frozen=True, slots=True)
class VerifiedEventCandidate:
    """A bound event and its independent categorical source verification."""

    claim: BoundClaimInventoryItem
    verification: CandidateVerification


def bind_source_unit_extraction(
    output: SourceUnitExtractionOutput,
    *,
    unit: FrozenSourceUnit,
) -> SourceUnitExtractionResult:
    """Bind every event independently and preserve rejected siblings."""

    binding = bind_claim_inventory_items(
        output.events,
        source_text=unit.text,
        source_sha256=unit.source_sha256,
        chunk_index=unit.index,
        source_start_offset=unit.source_start,
    )
    return SourceUnitExtractionResult(
        output=output,
        accepted=binding.accepted,
        rejected=binding.rejected,
    )


def bind_source_unit_verification(
    output: SourceUnitVerificationOutput,
    *,
    unit: FrozenSourceUnit,
    candidates: tuple[BoundClaimInventoryItem, ...],
) -> tuple[VerifiedEventCandidate, ...]:
    """Require one source-bound categorical decision per supplied candidate."""

    if any(
        candidate.source_sha256 != unit.source_sha256
        or candidate.chunk_index != unit.index
        or candidate.source_start < unit.source_start
        or candidate.source_end > unit.source_end
        for candidate in candidates
    ):
        raise StructuredModelSemanticError(
            "verification candidate source identity mismatch",
        )
    if len(output.decisions) != len(candidates):
        raise StructuredModelSemanticError(
            "ordered verification decisions must cover supplied candidates exactly",
        )
    if (
        not candidates
        and output.coverage_decision is SourceUnitCoverageDecision.CANDIDATES_COMPLETE
    ):
        raise StructuredModelSemanticError(
            "CANDIDATES_COMPLETE requires supplied candidates",
        )

    verified: list[VerifiedEventCandidate] = []
    for candidate, decision in zip(candidates, output.decisions, strict=True):
        claim_text = candidate.item.exact_span
        if len(decision.argument_semantic_decisions) != len(candidate.item.arguments):
            raise StructuredModelSemanticError(
                "ordered argument semantic decisions must cover candidate arguments exactly",
            )
        if any(span not in claim_text for span in decision.evidence_spans):
            raise StructuredModelSemanticError(
                "verification evidence must occur inside the candidate claim",
            )
        if decision.decision is EntailmentDecision.ENTAILED:
            required_spans = (
                candidate.item.relation_cue_span,
                *(argument.exact_span for argument in candidate.item.arguments),
            )
            if any(
                not any(required in evidence for evidence in decision.evidence_spans)
                for required in required_spans
            ):
                raise StructuredModelSemanticError(
                    "ENTAILED evidence must cover the trigger and every argument",
                )
        verified.append(
            VerifiedEventCandidate(claim=candidate, verification=decision),
        )
    return tuple(verified)


async def extract_source_unit(
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
) -> AuditedStructuredStepResult[
    SourceUnitExtractionOutput,
    SourceUnitExtractionResult,
]:
    """Run one categorical event decision through Artana's audited agent path."""

    prompt = _extraction_prompt(unit)
    step_key = fingerprinted_step_key(
        _EXTRACTION_PROMPT_VERSION,
        model_id,
        unit.input_sha256,
        execution_namespace,
    )

    async def invoke(invocation_id: str, provider_prompt: str) -> ModelStepResult:
        return await client.step(
            run_id=kernel_run_id_for_invocation(invocation_id),
            tenant=tenant,
            model=model_id,
            prompt=provider_prompt,
            output_schema=SourceUnitExtractionOutput,
            step_key=step_key,
            replay_policy="fork_on_drift",
        )

    return await run_audited_structured_step(
        invoke_model=invoke,
        model_id=model_id,
        prompt=prompt,
        output_schema=SourceUnitExtractionOutput,
        step_key=step_key,
        audit_context=ModelAttemptAuditContext(
            attempt_role="primary",
            pass_role="primary",  # noqa: S106 - categorical audit role
            retry_context=None,
            source_sha256=unit.source_sha256,
            input_sha256=unit.input_sha256,
            semantic_unit_id=unit.unit_id,
        ),
        validate_semantics=lambda output: bind_source_unit_extraction(
            output,
            unit=unit,
        ),
    )


async def verify_source_unit_candidates(  # noqa: PLR0913
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
    candidates: tuple[BoundClaimInventoryItem, ...],
) -> AuditedStructuredStepResult[
    SourceUnitVerificationOutput,
    tuple[VerifiedEventCandidate, ...],
]:
    """Independently verify every accepted candidate using only its source unit."""

    prompt = _verification_prompt(unit=unit, candidates=candidates)
    candidate_identity = "\n".join(candidate.inventory_id for candidate in candidates)
    step_key = fingerprinted_step_key(
        _VERIFICATION_PROMPT_VERSION,
        model_id,
        unit.input_sha256,
        candidate_identity,
        execution_namespace,
    )

    async def invoke(invocation_id: str, provider_prompt: str) -> ModelStepResult:
        return await client.step(
            run_id=kernel_run_id_for_invocation(invocation_id),
            tenant=tenant,
            model=model_id,
            prompt=provider_prompt,
            output_schema=SourceUnitVerificationOutput,
            step_key=step_key,
            replay_policy="fork_on_drift",
        )

    return await run_audited_structured_step(
        invoke_model=invoke,
        model_id=model_id,
        prompt=prompt,
        output_schema=SourceUnitVerificationOutput,
        step_key=step_key,
        audit_context=ModelAttemptAuditContext(
            attempt_role="weak_review",
            pass_role="weak_review",  # noqa: S106 - categorical audit role
            retry_context=None,
            source_sha256=unit.source_sha256,
            input_sha256=unit.input_sha256,
            semantic_unit_id=unit.unit_id,
        ),
        validate_semantics=lambda output: bind_source_unit_verification(
            output,
            unit=unit,
            candidates=candidates,
        ),
    )


def _extraction_prompt(unit: FrozenSourceUnit) -> str:
    return f"""You are the event-extraction agent in a sealed biomedical diagnostic.

Use only the frozen source unit below. Do not use outside knowledge.

{_SCIENTIFIC_EVENT_ELIGIBILITY_POLICY}

Map FINDING, HYPOTHESIS, and NULL_RESULT to EXPLICIT_EVENT and return every
distinct explicit event with a trigger and at least two material typed
arguments. Map PROCEDURE, MEASUREMENT_ONLY, and NO_EVENT to NO_EVENT with no
events. Map ABSTAIN to ABSTAIN with no events.

For each event, copy exact_span, relation_cue_span, and every argument span
verbatim. Use normalized_extraction_text as source_locator. Keep claim_kind,
event_type, polarity, and epistemic_status independent. Do not invent missing
participants, normalize surface text, merge events, or return numeric scores.
For every argument, at least one mention_anchor mention_span must exactly equal
that argument's exact_span. Do not include a determiner or modifier in the
argument exact_span when its canonical anchor omits it. When an argument span
appears more than once anywhere in the frozen source unit, every intended anchor
must include enough adjacent left_context and/or right_context to identify one
occurrence exactly, even when the competing occurrence lies outside exact_span.
Anchor context may extend immediately outside exact_span.
Do not return source-unit identifiers or input hashes. The audited orchestrator
binds transport identity outside the scientific output.

CONTROLLED-EVENT DECOMPOSITION:
When one source cue positively or negatively regulates another biological event,
represent the outer event as POSITIVE_REGULATION, NEGATIVE_REGULATION, or
REGULATION rather than collapsing it into the controlled event type. The outer
event owns its outer CAUSE, the controlled BIOLOGICAL_PROCESS as THEME, and its
outer context. When the controlled event is itself explicitly asserted,
including an event nominalization such as "TGF-beta induction of Foxp3," return
it as a separate sibling event whose own arguments carry the inner event roles.
Do not duplicate an inner participant on the outer event unless the source
independently assigns it an outer role. Deterministic source binding links a
unique outer process span to its sibling event after extraction. Do not invent an inner event
when the text only names an assay, planned measurement, or hypothetical process.
A phrase such as "enhanced nuclear translocation of NF-kappa B" must
not become only a LOCALIZATION event that leaves "enhanced" unstructured. A
process span such as "expression of MCP-1 and TNF-alpha" is BIOLOGICAL_PROCESS;
the named genes or proteins are separate GENE_OR_PROTEIN arguments. Do not label
a process as GENE_OR_PROTEIN merely because its span contains gene names.

COMPOSITE EVIDENCE SPANS:
An event exact_span must be the smallest contiguous source span containing every
clause needed to justify its event type, direction, causal interpretation, and
material arguments. When an earlier or later coordinated clause supplies the
direction for a causal conclusion, include both clauses. Never assign positive
or negative regulation from a neutral cue such as "affects" when exact_span
omits the directional language. When an observed increase or decrease is
explicitly linked to a concluding causal clause, encode the outer event with
that direction and use a complete exact_span covering both clauses. Do not emit
a generic REGULATION duplicate for the same directionally resolved outer event.

CAUSAL EVENT AND ENTITY SEMANTICS:
- Use POSITIVE_REGULATION or NEGATIVE_REGULATION when the source names a cause
  that induces, up-regulates, enhances, inhibits, down-regulates, or otherwise
  controls a theme or process. Use INCREASE or DECREASE only for a directional
  change with no explicit causal regulator.
- For a regulation event, type the regulator as CAUSE and the regulated entity
  or process as THEME. AGENT is not a substitute for CAUSE merely because a
  regulator grammatically performs the action.
- Cytokines, growth factors, transcription factors, receptors, enzymes, and
  named gene products are GENE_OR_PROTEIN. CHEMICAL_OR_DRUG is for small
  molecules, compounds, formulations, or explicitly pharmacological treatments;
  it is not a generic label for an experimentally administered protein.
- Preserve source-explicit population and context arguments in addition to the
  causal core; never trade away CAUSE or THEME to include context.

prompt_version: {_EXTRACTION_PROMPT_VERSION}

--- FROZEN SOURCE UNIT ---
{unit.text}
--- END SOURCE UNIT ---
"""


def _verification_prompt(
    *,
    unit: FrozenSourceUnit,
    candidates: tuple[BoundClaimInventoryItem, ...],
) -> str:
    payload = [_blinded_candidate(candidate) for candidate in candidates]
    return f"""You are an independent source-only biomedical verifier.

Use only the frozen source unit.

{_SCIENTIFIC_EVENT_ELIGIBILITY_POLICY}

First return your own eligibility_category, without using extractor reasoning.
For FINDING, HYPOTHESIS, or NULL_RESULT, return CANDIDATES_COMPLETE when supplied
candidates cover every scientific event or MISSING_EVENT otherwise. For
PROCEDURE, MEASUREMENT_ONLY, or NO_EVENT, return NO_EVENT_CONFIRMED because those
categories are not scientific events. Map ABSTAIN to ABSTAIN. Review the unit
even when no candidates were supplied. A false extracted candidate may be
rejected while the unit is NO_EVENT_CONFIRMED.

An explicitly asserted controlled event is a distinct event even when an outer
regulation also carries that process as a THEME. The inner event owns its
participants and their inner roles; the outer event owns its outer cause,
process theme, and context. Do not require inner participants to be duplicated
on the outer event unless the source independently assigns them an outer role.
Return MISSING_EVENT when the inner event or the outer event is absent. A directional causal candidate is
complete only when its exact_span contains every coordinated clause needed to
justify the direction; a neutral cue such as "affects" is insufficient when the
directional language lies outside that span.

For every supplied candidate, return exactly one categorical decision:
ENTAILED, CONTRADICTED, INSUFFICIENT, or ABSTAIN.
Return decisions in exactly the same order as the supplied candidate list.
ENTAILED requires the complete event, its direction, polarity, epistemic status,
trigger, and all material arguments to be explicit in the source. Copy literal
evidence spans from inside that candidate's exact_span. The evidence must cover
the trigger and every material argument. Provide concise reasoning and a
condition that would falsify your decision. Do not repair candidates, import
outside mechanistic or causal claims, compare against benchmark labels, or
return numeric scores. Standard biomedical entity-class knowledge is allowed
only for categorical argument typing.
Do not return source-unit identifiers, candidate identifiers, or input hashes.
The audited orchestrator binds transport identity outside scientific output.

For every candidate, independently return these additional categorical findings:
- structure_decision: COMPLETE only when the event type, event-local cause or
  theme, direction, and every material event-local participant are structurally preserved;
  LOSSY when the text is entailed but material structure survives only in a cue
  or bundled span; INVALID for a wrong or contradictory structure; ABSTAIN when
  the source cannot resolve it;
- direction_encoding: STRUCTURED when a material increase/decrease/regulation is
  encoded by event_type, SOURCE_ONLY when it appears only in source wording,
  CONFLICT when the structured direction disagrees, NOT_APPLICABLE when the
  source event has no material direction, or ABSTAIN;
- event_type_decision: VALID, INVALID, or ABSTAIN. A named causal regulator plus
  an induced/up-regulated/enhanced/inhibited/down-regulated theme is regulation;
  INCREASE or DECREASE is valid only when no explicit causal regulator is named;
- one argument_semantic_decision in candidate argument order, each containing
  type_decision and event_role_decision as VALID, INVALID, or ABSTAIN, with one
  reasoning. A regulator is CAUSE, not merely AGENT. Cytokines, growth factors,
  transcription factors, receptors, enzymes, and named gene products are
  GENE_OR_PROTEIN, not CHEMICAL_OR_DRUG merely because they were administered.
  A biological process is not GENE_OR_PROTEIN merely because its span contains
  gene names. You may use standard biomedical entity-class knowledge for these
  type judgments, but no outside mechanistic claim may substitute for the source;
- projection_eligibility: ELIGIBLE only for an ENTAILED, COMPLETE candidate with
  STRUCTURED or NOT_APPLICABLE direction, a VALID event type, and all argument
  types and event roles VALID;
  REVIEW_ONLY for an entailed but lossy or unresolved candidate; REJECT for a
  contradiction, invalid event structure, direction conflict, or invalid
  argument type; ABSTAIN only when a categorical judgment is unresolved.
  Specifically, INSUFFICIENT must use REJECT, never REVIEW_ONLY; REVIEW_ONLY
  requires ENTAILED plus a non-invalid structural trust blocker.

prompt_version: {_VERIFICATION_PROMPT_VERSION}

--- FROZEN SOURCE UNIT ---
{unit.text}
--- END SOURCE UNIT ---

--- CANDIDATES ---
{json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)}
--- END CANDIDATES ---
"""


def _blinded_candidate(candidate: BoundClaimInventoryItem) -> dict[str, object]:
    """Remove extractor reasoning and mention choices from verifier input."""

    item = candidate.item
    return {
        "exact_span": item.exact_span,
        "relation_cue_span": item.relation_cue_span,
        "source_locator": item.source_locator,
        "claim_kind": item.claim_kind.value,
        "event_type": item.event_type.value,
        "polarity": item.polarity.value,
        "epistemic_status": item.epistemic_status.value,
        "arguments": [
            {
                "role": argument.role.value,
                "event_role": argument.event_role.value,
                "exact_span": argument.exact_span,
            }
            for argument in item.arguments
        ],
    }


def as_model_client(client: object) -> FiniteSourceUnitModelClient:
    """Narrow the runtime's dynamic model client at one checked boundary."""

    if not callable(getattr(client, "step", None)):
        raise TypeError("finite source-unit runtime client lacks step()")
    return cast("FiniteSourceUnitModelClient", client)


__all__ = [
    "SourceUnitExtractionResult",
    "VerifiedEventCandidate",
    "as_model_client",
    "bind_source_unit_extraction",
    "bind_source_unit_verification",
    "extract_source_unit",
    "verify_source_unit_candidates",
]
