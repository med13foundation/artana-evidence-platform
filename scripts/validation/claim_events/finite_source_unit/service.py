"""Audited extraction and verification for finite TG-04 source units."""

from __future__ import annotations

import hashlib
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
from scripts.validation.claim_events.finite_source_unit.source_validation.binding_repair import (
    require_minimal_exact_span_repairs,
    require_source_binding_repair_invariant,
)
from scripts.validation.claim_events.finite_source_unit.source_validation.structural_invariants import (
    trusted_structure_violation,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )

_EXTRACTION_PROMPT_VERSION = "tg04.finite_source_unit.extraction.v20"
_VERIFICATION_PROMPT_VERSION = "tg04.finite_source_unit.verification.v19"
_BINDING_REPAIR_PROMPT_VERSION = (
    "tg04.finite_source_unit.source_validation.binding_repair.v2"
)
_SCIENTIFIC_EVENT_ELIGIBILITY_POLICY = """SCIENTIFIC EVENT ELIGIBILITY POLICY
Classify source meaning, never section labels, keywords, or perceived importance.
Return exactly one eligibility_category:
- FINDING: an asserted biological relationship or result;
- HYPOTHESIS: an explicitly proposed biological explanation or mechanism;
- NULL_RESULT: an explicit no-effect, no-association, or threshold-failing result;
- MIXED_SCIENTIFIC: the unit contains explicit events from more than one of
  FINDING, HYPOTHESIS, and NULL_RESULT;
- PROCEDURE: sample handling, preparation, intervention application, assay setup,
  instrument use, or another action without a reported biological result;
- MEASUREMENT_ONLY: an outcome is measured but no value, direction, comparison,
  or conclusion is reported;
- NO_EVENT: none of the categories above is explicit;
- ABSTAIN: the source cannot safely resolve the category.

FINDING, HYPOTHESIS, NULL_RESULT, and MIXED_SCIENTIFIC are scientific. PROCEDURE and
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


class ExtractionPromptBuilder(Protocol):
    def __call__(self, unit: FrozenSourceUnit) -> str: ...


class VerificationPromptBuilder(Protocol):
    def __call__(
        self,
        *,
        unit: FrozenSourceUnit,
        candidates: tuple[BoundClaimInventoryItem, ...],
    ) -> str: ...


@dataclass(frozen=True, slots=True)
class SourceUnitPromptPolicy:
    """Versioned prompt builders injected into the shared audited executor."""

    extraction_version: str
    verification_version: str
    extraction_prompt: ExtractionPromptBuilder
    verification_prompt: VerificationPromptBuilder


@dataclass(frozen=True, slots=True)
class SourceUnitExtractionResult:
    """Schema-valid categorical output plus item-level source binding."""

    output: SourceUnitExtractionOutput
    accepted: tuple[BoundClaimInventoryItem, ...]
    rejected: tuple[ClaimInventoryBindingRejection, ...]
    envelope_sha256: str

    def require_canonical_envelope(self, *, unit: FrozenSourceUnit) -> None:
        """Replay source binding so copied accepted/rejected fields fail closed."""

        try:
            type(self.output).model_validate(
                self.output.model_dump(mode="python", warnings=False),
                strict=True,
            )
        except ValueError as exc:
            raise StructuredModelSemanticError(
                "extraction result contains unvalidated categorical values"
            ) from exc
        expected = bind_source_unit_extraction(self.output, unit=unit)
        if self != expected:
            raise StructuredModelSemanticError(
                "extraction result does not match its canonical source envelope"
            )


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
        envelope_sha256=_canonical_extraction_envelope_sha256(
            output=output,
            unit=unit,
        ),
    )


def _canonical_extraction_envelope_sha256(
    *,
    output: SourceUnitExtractionOutput,
    unit: FrozenSourceUnit,
) -> str:
    payload = {
        "unit": {
            "unit_id": unit.unit_id,
            "index": unit.index,
            "source_start": unit.source_start,
            "source_end": unit.source_end,
            "source_sha256": unit.source_sha256,
            "input_sha256": unit.input_sha256,
        },
        "output": output.model_dump(mode="json"),
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
    ).hexdigest()


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
        if decision.trusted_projection_eligible:
            structural_violation = trusted_structure_violation(candidate)
            if structural_violation is not None:
                raise StructuredModelSemanticError(structural_violation)
        verified.append(
            VerifiedEventCandidate(claim=candidate, verification=decision),
        )
    return tuple(verified)


async def extract_source_unit(  # noqa: PLR0913
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
    prompt_policy: SourceUnitPromptPolicy | None = None,
    prepared_prompt: str | None = None,
) -> AuditedStructuredStepResult[
    SourceUnitExtractionOutput,
    SourceUnitExtractionResult,
]:
    """Run one categorical event decision through Artana's audited agent path."""

    policy = prompt_policy or default_source_unit_prompt_policy()
    prompt = (
        prepared_prompt
        if prepared_prompt is not None
        else policy.extraction_prompt(unit)
    )
    step_key = fingerprinted_step_key(
        policy.extraction_version,
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


async def repair_source_unit_extraction(  # noqa: PLR0913
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
    rejected_output: SourceUnitExtractionOutput,
    binding_errors: tuple[ClaimInventoryBindingRejection, ...],
) -> AuditedStructuredStepResult[
    SourceUnitExtractionOutput,
    SourceUnitExtractionResult,
]:
    """Ask the agent once to correct source binding without changing meaning."""

    if not binding_errors:
        raise ValueError("binding repair requires at least one rejection")
    prompt = canonical_source_unit_binding_repair_prompt(
        unit=unit,
        rejected_output=rejected_output,
        binding_errors=binding_errors,
    )
    repair_input_sha256 = hashlib.sha256(prompt.encode()).hexdigest()
    step_key = fingerprinted_step_key(
        _BINDING_REPAIR_PROMPT_VERSION,
        model_id,
        unit.input_sha256,
        repair_input_sha256,
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

    def validate_repair(
        output: SourceUnitExtractionOutput,
    ) -> SourceUnitExtractionResult:
        result = bind_source_unit_extraction(output, unit=unit)
        if result.rejected:
            raise StructuredModelSemanticError(
                "binding repair left unresolved source-binding rejections",
            )
        require_source_binding_repair_invariant(
            original=rejected_output,
            repaired=output,
            binding_errors=binding_errors,
        )
        require_minimal_exact_span_repairs(
            repaired=result.accepted,
            binding_errors=binding_errors,
        )
        return result

    return await run_audited_structured_step(
        invoke_model=invoke,
        model_id=model_id,
        prompt=prompt,
        output_schema=SourceUnitExtractionOutput,
        step_key=step_key,
        audit_context=ModelAttemptAuditContext(
            attempt_role="schema_retry",
            pass_role="primary",  # noqa: S106 - categorical audit role
            retry_context=None,
            source_sha256=unit.source_sha256,
            input_sha256=unit.input_sha256,
            semantic_unit_id=unit.unit_id,
        ),
        validate_semantics=validate_repair,
    )


async def verify_source_unit_candidates(  # noqa: PLR0913
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
    candidates: tuple[BoundClaimInventoryItem, ...],
    prompt_policy: SourceUnitPromptPolicy | None = None,
) -> AuditedStructuredStepResult[
    SourceUnitVerificationOutput,
    tuple[VerifiedEventCandidate, ...],
]:
    """Independently verify every accepted candidate using only its source unit."""

    policy = prompt_policy or default_source_unit_prompt_policy()
    prompt = policy.verification_prompt(unit=unit, candidates=candidates)
    candidate_identity = "\n".join(candidate.inventory_id for candidate in candidates)
    step_key = fingerprinted_step_key(
        policy.verification_version,
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
    return canonical_source_unit_extraction_prompt(unit)


def default_source_unit_prompt_policy() -> SourceUnitPromptPolicy:
    """Return the immutable prompt identity used by finalized V9 and earlier runs."""

    return SourceUnitPromptPolicy(
        extraction_version=_EXTRACTION_PROMPT_VERSION,
        verification_version=_VERIFICATION_PROMPT_VERSION,
        extraction_prompt=canonical_source_unit_extraction_prompt,
        verification_prompt=canonical_source_unit_verification_prompt,
    )


def canonical_source_unit_extraction_prompt(unit: FrozenSourceUnit) -> str:
    """Return the canonical blinded extraction prompt for one frozen unit."""

    return f"""You are the event-extraction agent in a sealed biomedical diagnostic.

Use only the frozen source unit below. Do not use outside knowledge.

{_SCIENTIFIC_EVENT_ELIGIBILITY_POLICY}

Map FINDING, HYPOTHESIS, NULL_RESULT, and MIXED_SCIENTIFIC to EXPLICIT_EVENT and return every
distinct explicit event with a trigger and at least two material typed
arguments when SOURCE_ASSERTED. A CONTROLLED_TARGET may have fewer, including
none, when the source names no explicit inner participant; never invent an
argument to satisfy a count. Map PROCEDURE, MEASUREMENT_ONLY, and NO_EVENT to NO_EVENT with no
events. Map ABSTAIN to ABSTAIN with no events.

For each event, copy exact_span, relation_cue_span, and every argument span
verbatim. Use normalized_extraction_text as source_locator. Keep claim_kind,
event_type, assertion_scope, polarity, and epistemic_status independent. Do not invent missing
participants, normalize surface text, merge events with different direction,
polarity, assertion scope, or process cues, or return numeric scores.
Leave mention_anchors empty when an argument exact_span occurs exactly once in
its claim. When an argument span appears more than once anywhere in the frozen
source unit, every intended anchor, including one whose mention_span exactly
equals the argument exact_span,
must include enough adjacent left_context and/or right_context to identify one
occurrence exactly, even when the competing occurrence lies outside exact_span.
Anchor context may extend immediately outside exact_span.
When an argument is an explicit anaphor or coreferential group such as "this
repression" or "the factors," keep that verbatim expression as exact_span and
use referent_anchors to identify every source-explicit antecedent mention. For
an anaphoric BIOLOGICAL_PROCESS theme, anchor the complete antecedent process
span containing its cue and material participants. For an entity group, anchor
every explicit member and assign the role from those antecedents. Never guess a
referent, replace exact_span with antecedent text, or return numeric positions.
Do not return source-unit identifiers or input hashes. The audited orchestrator
binds transport identity outside the scientific output.

CONTROLLED-EVENT DECOMPOSITION:
When one source cue positively or negatively regulates another biological event,
represent the outer event as POSITIVE_REGULATION, NEGATIVE_REGULATION, or
REGULATION rather than collapsing it into the referenced event type. Assign the
referenced BIOLOGICAL_PROCESS its source-explicit outer role: THEME when the
outer event controls it and CAUSE when that process causes the outer event.
Preserve other outer causes, themes, and context independently. When the
referenced event is itself explicitly asserted,
including an event nominalization such as "TGF-beta induction of Foxp3," return
it as a separate sibling event whose own arguments carry the inner event roles.
Use SOURCE_ASSERTED for an event that the source independently asserts. Use
CONTROLLED_TARGET when the source only names the event as the target of an outer
controller. A CONTROLLED_TARGET must use UNSCOPED polarity and UNASSERTED
epistemic_status; these values prevent a failed or uncertain outer controller
from becoming a false standalone assertion about the inner event. The outer
event alone carries the source's polarity and epistemic force.
When one coordinated process explicitly contains multiple referenced sibling
events with the same scope, either return each source-distinct inner event or one grouped inner event
with every explicit theme. Never drop a member or group events with different
direction, polarity, assertion scope, or process cues. Deterministic source
binding may link the outer process to each atomic sibling or the complete group.
The source may instead support source-valid direct atomic outer events sharing one
controller cue: preserve each gene as THEME and the shared production or
expression span as OUTCOME. In that atomic form do not invent a controlled
target; do not mix atomic and nested fragments in one representation.
When the referenced process is anaphoric, preserve its complete explicit
antecedent in referent_anchors so source binding can link the sibling events.
When multiple controlled siblings share one process trigger and source spans
cannot uniquely identify the intended target, give that target a unique
local_event_id and set controlled_event_ref on the BIOLOGICAL_PROCESS CAUSE or
THEME argument to the same identifier. Use it only for an explicit event-to-event
reference; deterministic binding still requires the referenced target's trigger
and every core participant inside the process span. Never use this identifier as a
score, ordering preference, or substitute for source evidence.
Do not duplicate an inner participant on the outer event unless the source
independently assigns it an outer role. Deterministic source binding links outer
process spans or agent-declared referent spans to source-distinct sibling events
after extraction. Do not invent an inner event
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
- For a symmetric physical BINDING or interaction event, assign every binding
  participant THEME. Do not invent AGENT or TARGET direction for an undirected
  interaction.
- Event direction describes the controller's effect on its immediate THEME. A
  factor that mediates, enables, or causes an inhibitory process positively
  regulates that process; do not copy the inner process's negative direction
  onto the outer event.
- Keep modality outside relation_cue_span when a narrower causal cue is explicit:
  for "could be mediated by", use "mediated" as the cue and encode uncertainty
  in claim_kind and epistemic_status.
- Scope epistemic status per event. A referenced nominalized finding can remain
  ASSERTED when only an outer proposed mechanism is HYPOTHESIS; do not propagate
  outer uncertainty inward unless the source makes the inner event uncertain.
- For a coordinated claim with a shared argument, exact_span must be one
  contiguous verbatim source span covering the shared argument, cue, and theme.
  Never insert "..." or omit intervening source words.
- For a statistically nonsignificant increase, decrease, or regulation, preserve
  the tested directional event_type and use NULL_RESULT polarity. Use NO_EFFECT
  only when the source states no effect and no more specific tested relationship
  is explicit. Preserve every coordinated outcome and source-explicit population
  or biological context as typed arguments.
- When the same source reports a directional trend and says the tested increase,
  decrease, or regulation was not statistically significant, return two sibling
  events. Preserve the trend as SUPPORT with PROVISIONAL epistemic status, and
  preserve the significance finding as NULL_RESULT with its source-explicit
  epistemic status. Both siblings retain every material cause, theme, population,
  intervention context, and the statistical significance language as a typed
  MEASUREMENT argument. The null sibling's relation cue must retain the complete
  negated significance phrase. Never rewrite nonsignificance as no change or no
  effect, and never invent a p-value, effect size, confidence interval, or numeric
  magnitude.
- Anchor the provisional trend to its source-explicit trend or tendency language.
  Never use a positive fragment taken from inside the sibling's negated
  significance predicate as the trend cue. Keep direction in event_type and keep
  the statistical-significance qualifier, without the direction word, as the
  MEASUREMENT when the source supports that separation.
- When an experimental manipulation phrase contains a named molecular cargo that
  is separately represented as the biological CAUSE, keep the whole manipulation
  as INTERVENTION/CONTEXT. Do not assign both the manipulation and its molecular
  cargo independent CAUSE roles unless the source explicitly gives each a
  distinct causal action.
- Temporal or experimental context such as "after treatment", "before or during
  treatment", "following exposure", "upon administration", or "prior to treatment"
  does not by itself assert causation. When a source reports a directional change
  in that context without a causal verb,
  use INCREASE or DECREASE, keep the treatment as INTERVENTION, EXPOSURE, or
  another source-valid CONTEXT argument, and preserve the complete temporal phrase
  including its intervention or exposure as a TIMEFRAME/CONTEXT argument. Preserve
  the changed process in the cue or a
  typed BIOLOGICAL_PROCESS, OUTCOME, or MEASUREMENT argument.
- An elliptical contrast such as "but not in activated cells" inherits the
  complete tested predicate from its coordinated antecedent. When its local cue
  is only "not", preserve the inherited process as a typed BIOLOGICAL_PROCESS,
  OUTCOME, or MEASUREMENT argument with a source-bound antecedent span. The entity
  alone is not a complete outcome.

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
    return canonical_source_unit_verification_prompt(unit=unit, candidates=candidates)


def canonical_source_unit_verification_prompt(
    *,
    unit: FrozenSourceUnit,
    candidates: tuple[BoundClaimInventoryItem, ...],
) -> str:
    """Return the canonical blinded verification prompt for rebound candidates."""

    payload = [_blinded_candidate(candidate) for candidate in candidates]
    return f"""You are an independent source-only biomedical verifier.

Use only the frozen source unit.

{_SCIENTIFIC_EVENT_ELIGIBILITY_POLICY}

First return your own eligibility_category, without using extractor reasoning.
For FINDING, HYPOTHESIS, NULL_RESULT, or MIXED_SCIENTIFIC, return CANDIDATES_COMPLETE when supplied
candidates cover every scientific event or MISSING_EVENT otherwise. For
PROCEDURE, MEASUREMENT_ONLY, or NO_EVENT, return NO_EVENT_CONFIRMED because those
categories are not scientific events. Map ABSTAIN to ABSTAIN. Review the unit
even when no candidates were supplied. A false extracted candidate may be
rejected while the unit is NO_EVENT_CONFIRMED.

An explicitly asserted referenced event is distinct even when an outer
regulation carries that process as a THEME or CAUSE. The inner event owns its
participants and their inner roles; the outer event preserves the process's
source-explicit role plus its other cause, theme, and context. Do not require inner participants to be duplicated
on the outer event unless the source independently assigns them an outer role.
When one coordinated process explicitly contains multiple source-distinct inner
events with the same scope, accept either all atomic siblings or one grouped event that preserves
every explicit theme. Also accept complete source-valid direct atomic outer
events that preserve each gene theme, the shared process outcome, and source
polarity. In that direct form, no separate inner event is required. In a nested
form, every outer event must reference its corresponding inner event; use
controlled_event_ref to resolve shared-trigger siblings. Reject partial
mixtures, missing members, or grouping across different
direction, polarity, assertion scope, or process cues.
Return MISSING_EVENT when the inner event or the outer event is absent from a
nested pair. A directional causal candidate is
complete only when its exact_span contains every coordinated clause needed to
justify the direction; a neutral cue such as "affects" is insufficient when the
directional language lies outside that span.
Resolve explicit pronouns and coreferential groups from the frozen source when
checking semantic types and event roles. An anaphoric expression may be a valid
GENE_OR_PROTEIN or BIOLOGICAL_PROCESS argument when the source itself resolves
that antecedent; reject it when the source does not.

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
For CONTROLLED_TARGET, ENTAILED means the source explicitly names the event as
the target of a source-explicit outer controller. UNSCOPED and UNASSERTED are
structural non-assertion categories, not claims that the source literally uses
those words. Reject a CONTROLLED_TARGET that is not linked by source meaning to
an outer controller, and reject SOURCE_ASSERTED when the event exists only as a
controlled target. CANDIDATES_COMPLETE requires both the source-asserted outer
event and every material controlled target.
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
- for a symmetric physical BINDING or interaction event, every binding participant must use THEME.
  AGENT or TARGET is invalid unless the source
  explicitly states a distinct directional role beyond the interaction;
- an outer event that mediates, enables, or causes an inhibitory process is
  POSITIVE_REGULATION of that process, not NEGATIVE_REGULATION copied from the
  inner event;
- a relation cue excludes modal auxiliaries when the causal cue remains explicit,
  and epistemic status is scoped independently for each inner and outer event;
- projection_eligibility: ELIGIBLE only for an ENTAILED, COMPLETE candidate with
  STRUCTURED or NOT_APPLICABLE direction, a VALID event type, and all argument
  types and event roles VALID;
  REVIEW_ONLY for an entailed but lossy or unresolved candidate; REJECT for a
  contradiction, invalid event structure, direction conflict, or invalid
  argument type; ABSTAIN only when a categorical judgment is unresolved.
  Specifically, INSUFFICIENT must use REJECT, never REVIEW_ONLY; REVIEW_ONLY
  requires ENTAILED plus a non-invalid structural trust blocker.
- A statistically nonsignificant directional result keeps its tested event type
  with NULL_RESULT polarity; NO_EFFECT is valid only when no more specific tested
  relationship is explicit. Every coordinated outcome and source-explicit
  population or biological context must remain structurally represented.
- When the source also reports a directional trend, CANDIDATES_COMPLETE requires
  two sibling events: the trend as SUPPORT plus PROVISIONAL, and the
  statistical-significance finding as NULL_RESULT with its source-explicit
  epistemic status. Both must preserve every material cause, theme, population,
  intervention context, and the statistical significance MEASUREMENT argument.
  The null cue must retain the complete negated significance phrase. Return
  MISSING_EVENT when either sibling is absent, nonsignificance is broadened to no
  effect or no change, or a p-value, effect size, confidence interval, or numeric
  magnitude is invented.
- Mark the inventory incomplete or structurally lossy when a trend cue is copied
  from inside the sibling's negated-significance predicate, when a direction word
  is incorrectly bundled into a separable statistical-significance MEASUREMENT,
  or when a manipulation and its molecular cargo duplicate the same CAUSE role.
- "After treatment", "following exposure", and similar temporal or experimental
  context do not establish CAUSE without causal source language. INCREASE or
  DECREASE with a typed intervention/exposure CONTEXT is valid only when the
  temporal phrase is preserved as TIMEFRAME and the changed process and every
  population-specific outcome remain explicit. An elliptical null contrast with
  cue "not" is incomplete unless a typed argument preserves its inherited tested
  process.

prompt_version: {_VERIFICATION_PROMPT_VERSION}

--- FROZEN SOURCE UNIT ---
{unit.text}
--- END SOURCE UNIT ---

--- CANDIDATES ---
{json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)}
--- END CANDIDATES ---
"""


def canonical_source_unit_binding_repair_prompt(
    *,
    unit: FrozenSourceUnit,
    rejected_output: SourceUnitExtractionOutput,
    binding_errors: tuple[ClaimInventoryBindingRejection, ...],
) -> str:
    errors = [error.as_json() for error in binding_errors]
    return f"""You are repairing one source-binding failure in a sealed biomedical event inventory.

Use only the frozen source unit. Return the complete corrected extraction output,
including every event from the previous output in the same order. For an
EXACT_SPAN_MISSING error only, replace that event exact_span with the minimal
contiguous verbatim source span containing its unchanged relation cue and every
unchanged argument exact_span; never use an ellipsis. Otherwise change only
left_context or right_context on an existing mention anchor. Preserve every
event and argument count, relation_cue_span, argument exact_span, anchor
mention_span, referent mention_span, categorical field, role, rationale, and
source-explicit referent exactly. Never invent or delete an event, change
scientific meaning, use outside knowledge, or return numeric scores.
Deterministic validation rejects every other mutation.

prompt_version: {_BINDING_REPAIR_PROMPT_VERSION}

--- FROZEN SOURCE UNIT ---
{unit.text}
--- END SOURCE UNIT ---

--- PREVIOUS EXTRACTION OUTPUT ---
{json.dumps(rejected_output.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=True)}
--- END PREVIOUS EXTRACTION OUTPUT ---

--- SOURCE-BINDING ERRORS ---
{json.dumps(errors, indent=2, sort_keys=True, ensure_ascii=True)}
--- END SOURCE-BINDING ERRORS ---
"""


def _binding_repair_prompt(
    *,
    unit: FrozenSourceUnit,
    rejected_output: SourceUnitExtractionOutput,
    binding_errors: tuple[ClaimInventoryBindingRejection, ...],
) -> str:
    """Compatibility wrapper for existing focused prompt tests."""

    return canonical_source_unit_binding_repair_prompt(
        unit=unit,
        rejected_output=rejected_output,
        binding_errors=binding_errors,
    )


def _blinded_candidate(candidate: BoundClaimInventoryItem) -> dict[str, object]:
    """Remove extractor reasoning and mention choices from verifier input."""

    item = candidate.item
    return {
        "exact_span": item.exact_span,
        "relation_cue_span": item.relation_cue_span,
        "source_locator": item.source_locator,
        "claim_kind": item.claim_kind.value,
        "event_type": item.event_type.value,
        "local_event_id": item.local_event_id,
        "assertion_scope": item.assertion_scope.value,
        "polarity": item.polarity.value,
        "epistemic_status": item.epistemic_status.value,
        "arguments": [
            {
                "role": argument.role.value,
                "event_role": argument.event_role.value,
                "exact_span": argument.exact_span,
                "controlled_event_ref": argument.controlled_event_ref,
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
    "SourceUnitPromptPolicy",
    "SourceUnitExtractionResult",
    "VerifiedEventCandidate",
    "as_model_client",
    "bind_source_unit_extraction",
    "bind_source_unit_verification",
    "canonical_source_unit_binding_repair_prompt",
    "canonical_source_unit_extraction_prompt",
    "canonical_source_unit_verification_prompt",
    "default_source_unit_prompt_policy",
    "extract_source_unit",
    "repair_source_unit_extraction",
    "verify_source_unit_candidates",
]
