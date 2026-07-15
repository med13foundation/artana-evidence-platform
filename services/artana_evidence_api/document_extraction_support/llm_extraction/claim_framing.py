"""One-inventoried-claim-at-a-time agent framing stage."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Protocol, cast

from artana_evidence_api.document_extraction_contracts import (
    ExtractedRelationCandidate,
    LLMRelationLike,
)
from artana_evidence_api.document_extraction_prompting import (
    SINGLE_CLAIM_FRAMING_SYSTEM_PROMPT,
)
from artana_evidence_api.document_extraction_support.claim_frames import (
    BoundClaimInventoryItem,
    ClaimArgumentRole,
    ClaimFramingDecision,
    ClaimInventoryBindingError,
    ClaimLocalSourceRegion,
    QualifierState,
    derive_claim_local_source_region,
    normalize_claim_frame,
)
from artana_evidence_api.document_extraction_support.llm_extraction.prompt_versions import (
    CLAIM_FRAMING_PROMPT_VERSION,
)
from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    AuditedStructuredStepResult,
    StructuredModelSemanticError,
    run_audited_structured_step,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    ModelAttemptAuditContext,
    ModelAttemptAuditRecord,
    ModelStepResult,
    ModelStepRunner,
    current_model_attempt_audit,
    fingerprinted_step_key,
    llm_relation_to_candidate,
    record_skipped_model_attempt,
)
from pydantic import BaseModel, ValidationError

_SCHEMA_RETRY_SUFFIX = "schema_retry.v1"
_SCHEMA_RETRY_INSTRUCTION = """

SCHEMA AND SOURCE-BINDING RETRY:
The previous framing output failed the strict schema or contradicted the frozen
inventory/source boundary. Frame only the supplied claim. Copy candidate
endpoints only from the typed arguments and copy exact_span verbatim. For each
candidate, set a qualifier to NOT_APPLICABLE when its argument is already the
subject or object; every non-endpoint role with a matching qualifier must remain
PRESENT. Preserve polarity and epistemic_status and do not borrow qualifiers
from another claim. When distinct intervention-to-condition and
intervention-to-outcome projections are both source-supported, return both as
MULTIPLE_VALID_FRAMES. ABSTAIN rather than guessing.
"""


class SingleClaimFramingResultLike(Protocol):
    """Typed view of the dynamic one-claim framing output schema."""

    decision: ClaimFramingDecision
    relations: list[LLMRelationLike]
    decision_rationale: str


@dataclass(frozen=True, slots=True)
class FramedClaimResult:
    """Validated result of one claim-specific model call."""

    candidates: tuple[ExtractedRelationCandidate, ...]
    unknown_relation_types: tuple[str, ...]
    decision: ClaimFramingDecision
    decision_rationale: str

    @property
    def abstained(self) -> bool:
        return self.decision is ClaimFramingDecision.ABSTAIN


@dataclass(frozen=True, slots=True)
class ClaimFramingStageResult:
    """One validated claim result plus its immutable accepted raw output."""

    framed_claim: FramedClaimResult
    source_region: ClaimLocalSourceRegion
    attempt_record: ModelAttemptAuditRecord
    raw_agent_outputs: tuple[dict[str, object], ...]


def build_single_claim_framing_prompt(
    *,
    inventory_claim: BoundClaimInventoryItem,
    source_region: ClaimLocalSourceRegion | None = None,
) -> str:
    """Build a prompt containing only one bound claim and its exact source span."""

    source_region = source_region or derive_claim_local_source_region(inventory_claim)
    _require_exact_inventory_source_region(
        inventory_claim=inventory_claim,
        source_region=source_region,
    )

    claim_local_item = inventory_claim.item.model_dump(mode="json")
    item_json = json.dumps(
        claim_local_item,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return (
        f"{SINGLE_CLAIM_FRAMING_SYSTEM_PROMPT}\n\n"
        "MODEL CONTRACT\n"
        f"- prompt_version: {CLAIM_FRAMING_PROMPT_VERSION}\n"
        f"- document_sha256: {inventory_claim.source_sha256}\n"
        f"- inventory_id: {inventory_claim.inventory_id}\n"
        f"- chunk_index: {inventory_claim.chunk_index + 1}\n"
        f"- source_char_range: {source_region.source_start}-"
        f"{source_region.source_end}\n"
        "- source_locator: normalized_extraction_text\n\n"
        "---\nBOUND INVENTORY ITEM\n---\n"
        f"{item_json}\n"
        "---\nCLAIM-LOCAL FROZEN SOURCE REGION\n---\n"
        f"{source_region.text}\n"
        "---\n"
    )


async def run_single_claim_framing_stage(
    *,
    inventory_claim: BoundClaimInventoryItem,
    output_schema: type[BaseModel],
    client: object,
    tenant: object,
    model_id: str,
    step_runner: ModelStepRunner,
    execution_namespace: str,
) -> ClaimFramingStageResult:
    """Frame one inventory claim, with one audited agent schema repair."""

    source_region = derive_claim_local_source_region(inventory_claim)
    prompt = build_single_claim_framing_prompt(
        inventory_claim=inventory_claim,
        source_region=source_region,
    )
    step_key = _claim_framing_step_key(
        prompt_version=CLAIM_FRAMING_PROMPT_VERSION,
        inventory_claim=inventory_claim,
        model_id=model_id,
        execution_namespace=execution_namespace,
    )
    audit_context = _claim_framing_audit_context(
        inventory_claim=inventory_claim,
        schema_retry=False,
    )
    schema_retry_prompt = f"{prompt}{_SCHEMA_RETRY_INSTRUCTION}"
    schema_retry_step_key = _claim_framing_step_key(
        prompt_version=f"{CLAIM_FRAMING_PROMPT_VERSION}.{_SCHEMA_RETRY_SUFFIX}",
        inventory_claim=inventory_claim,
        model_id=model_id,
        execution_namespace=execution_namespace,
    )
    schema_retry_context = _claim_framing_audit_context(
        inventory_claim=inventory_claim,
        schema_retry=True,
    )

    try:
        result = await _run_claim_framing_step(
            inventory_claim=inventory_claim,
            source_region=source_region,
            output_schema=output_schema,
            client=client,
            tenant=tenant,
            model_id=model_id,
            step_runner=step_runner,
            prompt=prompt,
            step_key=step_key,
            audit_context=audit_context,
        )
    except (ValidationError, StructuredModelSemanticError):
        retry_result = await _run_claim_framing_step(
            inventory_claim=inventory_claim,
            source_region=source_region,
            output_schema=output_schema,
            client=client,
            tenant=tenant,
            model_id=model_id,
            step_runner=step_runner,
            prompt=schema_retry_prompt,
            step_key=schema_retry_step_key,
            audit_context=schema_retry_context,
        )
        return ClaimFramingStageResult(
            framed_claim=retry_result.value,
            source_region=source_region,
            attempt_record=_accepted_framing_attempt_record(),
            raw_agent_outputs=(retry_result.raw_output,),
        )

    record_skipped_model_attempt(
        model_id=model_id,
        prompt=schema_retry_prompt,
        output_schema=output_schema,
        step_key=schema_retry_step_key,
        audit_context=schema_retry_context,
    )
    return ClaimFramingStageResult(
        framed_claim=result.value,
        source_region=source_region,
        attempt_record=_accepted_framing_attempt_record(),
        raw_agent_outputs=(result.raw_output,),
    )


async def _run_claim_framing_step(
    *,
    inventory_claim: BoundClaimInventoryItem,
    source_region: ClaimLocalSourceRegion,
    output_schema: type[BaseModel],
    client: object,
    tenant: object,
    model_id: str,
    step_runner: ModelStepRunner,
    prompt: str,
    step_key: str,
    audit_context: ModelAttemptAuditContext,
) -> AuditedStructuredStepResult[BaseModel, FramedClaimResult]:
    def _validate(parsed: BaseModel) -> FramedClaimResult:
        output = cast("SingleClaimFramingResultLike", parsed)
        if output.decision is ClaimFramingDecision.ABSTAIN:
            return FramedClaimResult(
                candidates=(),
                unknown_relation_types=(),
                decision=output.decision,
                decision_rationale=output.decision_rationale,
            )
        candidates: list[ExtractedRelationCandidate] = []
        unknown_relation_types: list[str] = []
        for relation in output.relations:
            _require_inventory_consistency(
                relation=relation,
                inventory_claim=inventory_claim,
                source_region=source_region,
            )
            try:
                candidate, unknown_relation_type = llm_relation_to_candidate(
                    relation,
                    source_text=source_region.text,
                    source_hash=inventory_claim.source_sha256,
                )
            except ValueError as exc:
                raise StructuredModelSemanticError(str(exc)) from exc
            if candidate is None or candidate.claim_frame is None:
                raise StructuredModelSemanticError(
                    "framed relation failed qualified claim source validation",
                )
            frame = candidate.claim_frame.model_copy(
                update={"assertion_arguments": inventory_claim.item.arguments},
            )
            try:
                frame = normalize_claim_frame(
                    frame,
                    source_region.text,
                    expected_source_hash=inventory_claim.source_sha256,
                )
            except ValueError as exc:
                raise StructuredModelSemanticError(str(exc)) from exc
            candidate = replace(candidate, claim_frame=frame)
            candidates.append(candidate)
            if unknown_relation_type is not None:
                unknown_relation_types.append(unknown_relation_type)
        return FramedClaimResult(
            candidates=tuple(candidates),
            unknown_relation_types=tuple(unknown_relation_types),
            decision=output.decision,
            decision_rationale=output.decision_rationale,
        )

    async def _invoke_model(
        invocation_id: str,
        provider_prompt: str,
    ) -> ModelStepResult:
        return await step_runner(
            client,
            run_id=f"research-init-extraction:{invocation_id}",
            tenant=tenant,
            model=model_id,
            prompt=provider_prompt,
            output_schema=output_schema,
            schema_id="document_extraction.claim_framing.v2",
            step_key=step_key,
            replay_policy="fork_on_drift",
        )

    return await run_audited_structured_step(
        invoke_model=_invoke_model,
        model_id=model_id,
        prompt=prompt,
        output_schema=output_schema,
        step_key=step_key,
        audit_context=audit_context,
        validate_semantics=_validate,
    )


def _require_inventory_consistency(
    *,
    relation: LLMRelationLike,
    inventory_claim: BoundClaimInventoryItem,
    source_region: ClaimLocalSourceRegion,
) -> None:
    item = inventory_claim.item
    _require_exact_inventory_source_region(
        inventory_claim=inventory_claim,
        source_region=source_region,
    )
    if relation.sentence != item.exact_span:
        raise StructuredModelSemanticError(
            "framed relation sentence must equal the inventory exact_span",
        )
    if relation.polarity is not item.polarity:
        raise StructuredModelSemanticError(
            "framed relation changed the inventoried polarity",
        )
    if relation.epistemic_status is not item.epistemic_status:
        raise StructuredModelSemanticError(
            "framed relation changed the inventoried epistemic_status",
        )
    argument_spans = {argument.exact_span for argument in item.arguments}
    if relation.subject not in argument_spans or relation.object not in argument_spans:
        raise StructuredModelSemanticError(
            "framed relation endpoints must come from typed inventory arguments",
        )
    _require_role_retention(relation=relation, inventory_claim=inventory_claim)


_ROLE_QUALIFIER_FIELDS: dict[ClaimArgumentRole, str] = {
    ClaimArgumentRole.INTERVENTION: "intervention",
    ClaimArgumentRole.POPULATION: "population",
    ClaimArgumentRole.VARIANT: "biological_or_variant_state",
    ClaimArgumentRole.OUTCOME: "outcome",
    ClaimArgumentRole.COMPARATOR: "comparator",
    ClaimArgumentRole.TIMEFRAME: "timeframe",
    ClaimArgumentRole.STUDY_DESIGN: "study_design",
    ClaimArgumentRole.TREATMENT_SETTING: "treatment_setting",
    ClaimArgumentRole.CONDITION: "condition",
}


def _require_role_retention(
    *,
    relation: LLMRelationLike,
    inventory_claim: BoundClaimInventoryItem,
) -> None:
    endpoints = {relation.subject, relation.object}
    for argument in inventory_claim.item.arguments:
        if argument.exact_span in endpoints:
            continue
        qualifier_field = _ROLE_QUALIFIER_FIELDS.get(argument.role)
        if qualifier_field is None:
            continue
        qualifier = getattr(relation, qualifier_field)
        if (
            qualifier.state is not QualifierState.PRESENT
            or qualifier.exact_span != argument.exact_span
        ):
            raise StructuredModelSemanticError(
                f"framed relation dropped {argument.role.value} argument "
                f"{argument.exact_span!r}",
            )


def _require_exact_inventory_source_region(
    *,
    inventory_claim: BoundClaimInventoryItem,
    source_region: ClaimLocalSourceRegion,
) -> None:
    if (
        source_region.text != inventory_claim.item.exact_span
        or source_region.source_start != inventory_claim.source_start
        or source_region.source_end != inventory_claim.source_end
    ):
        raise ClaimInventoryBindingError(
            "claim framing source region must equal the bound inventory exact_span",
        )


def _claim_framing_step_key(
    *,
    prompt_version: str,
    inventory_claim: BoundClaimInventoryItem,
    model_id: str,
    execution_namespace: str,
) -> str:
    return fingerprinted_step_key(
        "research_init.claim_framing.v2",
        prompt_version,
        model_id,
        inventory_claim.source_sha256,
        str(inventory_claim.chunk_index),
        inventory_claim.inventory_id,
        execution_namespace,
    )


def _claim_framing_audit_context(
    *,
    inventory_claim: BoundClaimInventoryItem,
    schema_retry: bool,
) -> ModelAttemptAuditContext:
    return ModelAttemptAuditContext(
        attempt_role="schema_retry" if schema_retry else "claim_framing",
        pass_role="claim_framing",
        retry_context=None,
        source_sha256=inventory_claim.source_sha256,
        input_sha256=_claim_input_sha256(inventory_claim),
        semantic_unit_id=inventory_claim.inventory_id,
    )


def _accepted_framing_attempt_record() -> ModelAttemptAuditRecord:
    audit_session = current_model_attempt_audit()
    if audit_session is None:
        raise AssertionError("claim framing requires an active model-attempt audit")
    for record in reversed(audit_session.records):
        if (
            record.pass_role == "claim_framing"
            and record.validation_outcome == "accepted"
        ):
            return record
    raise AssertionError("claim framing accepted without an audit record")


def _claim_input_sha256(inventory_claim: BoundClaimInventoryItem) -> str:
    payload = json.dumps(
        {
            "inventory_id": inventory_claim.inventory_id,
            "item": inventory_claim.item.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "CLAIM_FRAMING_PROMPT_VERSION",
    "ClaimFramingStageResult",
    "FramedClaimResult",
    "build_single_claim_framing_prompt",
    "run_single_claim_framing_stage",
]
