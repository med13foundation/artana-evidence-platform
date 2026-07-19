"""Deterministic V14 mapping derivation and canonical semantic binding."""

from __future__ import annotations

from collections import Counter
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

from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    NormalizationFamily,
    NormalizationOperation,
)
from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    SourceUnitNormalizationResult,
    bind_source_unit_normalization,
    canonical_json_sha256,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_contracts import (
    SourceUnitNormalizationOutputV13,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v14_contracts import (
    SourceUnitNormalizationProposalV14,
)

if TYPE_CHECKING:
    from scripts.validation.claim_events.finite_source_unit.service import (
        FiniteSourceUnitModelClient,
        SourceUnitExtractionResult,
    )
    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )

V14_MAPPING_DERIVATION_VERSION = "tg04.finite_source_unit.deterministic_mapping.v1"


@dataclass(frozen=True, slots=True)
class V14NormalizationEnvelope:
    """Raw provider proposal and its deterministic canonical representation."""

    proposal: SourceUnitNormalizationProposalV14
    canonical_result: SourceUnitNormalizationResult
    derived_operations: tuple[NormalizationOperation, ...]
    envelope_sha256: str

    def require_canonical_envelope(
        self,
        *,
        unit: FrozenSourceUnit,
        original: SourceUnitExtractionResult,
    ) -> None:
        """Rebuild every derived field and reject detached evidence."""

        try:
            type(self.proposal).model_validate(
                self.proposal.model_dump(mode="python", warnings=False),
                strict=True,
            )
        except ValueError as exc:
            raise StructuredModelSemanticError(
                "V14 proposal contains unvalidated categorical values"
            ) from exc
        expected = bind_source_unit_normalization_v14(
            self.proposal,
            unit=unit,
            original=original,
        )
        if self != expected:
            raise StructuredModelSemanticError(
                "V14 normalization envelope is not canonical"
            )


def bind_source_unit_normalization_v14(
    proposal: SourceUnitNormalizationProposalV14,
    *,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
) -> V14NormalizationEnvelope:
    """Derive procedural labels and bind the unchanged scientific proposal."""

    _require_literal_mention_anchors(proposal)
    operations = derive_v14_mapping_operations(
        proposal=proposal,
        unit=unit,
        original=original,
    )
    canonical_payload = proposal.model_dump(mode="json")
    raw_mappings = canonical_payload.get("mappings")
    if not isinstance(raw_mappings, list) or len(raw_mappings) != len(operations):
        raise StructuredModelSemanticError("V14 mapping payload is not canonical")
    for raw_mapping, operation in zip(raw_mappings, operations, strict=True):
        if not isinstance(raw_mapping, dict):
            raise StructuredModelSemanticError("V14 mapping payload is not canonical")
        raw_mapping["operation"] = operation.value
    canonical_output = SourceUnitNormalizationOutputV13.model_validate(
        canonical_payload
    )
    canonical_result = bind_source_unit_normalization(
        canonical_output,
        unit=unit,
        original=original,
    )
    return V14NormalizationEnvelope(
        proposal=proposal,
        canonical_result=canonical_result,
        derived_operations=operations,
        envelope_sha256=canonical_json_sha256(
            {
                "derivation_version": V14_MAPPING_DERIVATION_VERSION,
                "source_unit_input_sha256": unit.input_sha256,
                "original_envelope_sha256": original.envelope_sha256,
                "provider_proposal": proposal.model_dump(mode="json"),
                "derived_operations": [operation.value for operation in operations],
                "canonical_binding_envelope_sha256": (canonical_result.envelope_sha256),
            }
        ),
    )


def _require_literal_mention_anchors(
    proposal: SourceUnitNormalizationProposalV14,
) -> None:
    """Keep V14 occurrence anchors distinct from semantic referent anchors."""

    for event in proposal.events:
        for argument in event.arguments:
            if any(
                anchor.mention_span != argument.exact_span
                for anchor in argument.mention_anchors
            ):
                raise StructuredModelSemanticError(
                    "V14 mention anchors must repeat the argument exact_span; "
                    "aliases and anaphora require referent anchors"
                )


def derive_v14_mapping_operations(
    *,
    proposal: SourceUnitNormalizationProposalV14,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
) -> tuple[NormalizationOperation, ...]:
    """Derive labels only from mapping cardinality and canonical equality."""

    original.require_canonical_envelope(unit=unit)
    if proposal.family is NormalizationFamily.ABSTAIN:
        return ()
    source_event_count = len(original.output.events)
    mapped_positions = tuple(
        position
        for mapping in proposal.mappings
        for position in mapping.source_event_positions
    )
    if any(position >= source_event_count for position in mapped_positions):
        raise StructuredModelSemanticError(
            "normalization mapping references unknown event"
        )
    if set(mapped_positions) != set(range(source_event_count)):
        raise StructuredModelSemanticError(
            "normalization mappings must cover every source event"
        )
    source_use_counts = Counter(mapped_positions)
    operations: list[NormalizationOperation] = []
    for mapping in proposal.mappings:
        if len(mapping.source_event_positions) > 1:
            if any(
                source_use_counts[position] > 1
                for position in mapping.source_event_positions
            ):
                raise StructuredModelSemanticError(
                    "many-to-many normalization mapping is ambiguous"
                )
            operations.append(NormalizationOperation.MERGE)
            continue
        source_position = mapping.source_event_positions[0]
        if source_use_counts[source_position] > 1:
            operations.append(NormalizationOperation.SPLIT)
            continue
        source_event = original.output.events[source_position]
        normalized_event = proposal.events[mapping.normalized_event_position]
        operations.append(
            NormalizationOperation.UNCHANGED
            if source_event.model_dump(mode="json")
            == normalized_event.model_dump(mode="json")
            else NormalizationOperation.REFRAME
        )
    return tuple(operations)


async def normalize_source_unit_proposal_v14(  # noqa: PLR0913
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
    original_raw_output: dict[str, object],
    prompt: str,
    prompt_version: str,
) -> AuditedStructuredStepResult[
    SourceUnitNormalizationProposalV14,
    V14NormalizationEnvelope,
]:
    """Run one V14 proposal call and bind deterministic mapping custody."""

    original_raw_sha256 = canonical_json_sha256(original_raw_output)
    step_key = fingerprinted_step_key(
        prompt_version,
        model_id,
        unit.input_sha256,
        original_raw_sha256,
        V14_MAPPING_DERIVATION_VERSION,
        execution_namespace,
    )

    async def invoke(invocation_id: str, provider_prompt: str) -> ModelStepResult:
        return await client.step(
            run_id=kernel_run_id_for_invocation(invocation_id),
            tenant=tenant,
            model=model_id,
            prompt=provider_prompt,
            output_schema=SourceUnitNormalizationProposalV14,
            step_key=step_key,
            replay_policy="fork_on_drift",
        )

    return await run_audited_structured_step(
        invoke_model=invoke,
        model_id=model_id,
        prompt=prompt,
        output_schema=SourceUnitNormalizationProposalV14,
        step_key=step_key,
        audit_context=ModelAttemptAuditContext(
            attempt_role="structure_normalization",
            pass_role="structure_normalization",  # noqa: S106 - audit role
            retry_context=None,
            source_sha256=unit.source_sha256,
            input_sha256=unit.input_sha256,
            semantic_unit_id=unit.unit_id,
        ),
        validate_semantics=lambda proposal: bind_source_unit_normalization_v14(
            proposal,
            unit=unit,
            original=original,
        ),
    )


__all__ = [
    "V14_MAPPING_DERIVATION_VERSION",
    "V14NormalizationEnvelope",
    "bind_source_unit_normalization_v14",
    "derive_v14_mapping_operations",
    "normalize_source_unit_proposal_v14",
]
