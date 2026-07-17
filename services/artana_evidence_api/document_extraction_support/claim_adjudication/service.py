"""Independent categorical adjudication for canonicalized document claims."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import replace
from typing import Protocol, cast
from uuid import uuid4

from artana_evidence_api.document_extraction_support.claim_adjudication.contracts import (
    ClaimAdjudicationDecision,
    ClaimAdjudicationDiagnostics,
    ClaimAdjudicationOutput,
)
from artana_evidence_api.document_extraction_support.claim_adjudication.metrics import (
    claim_adjudication_metrics,
)
from artana_evidence_api.document_store import HarnessDocumentRecord
from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.types.common import JSONObject, json_value
from pydantic import ValidationError

_SCHEMA_ID = "document_extraction.claim_adjudication.v1"
_PROMPT_ID = "document_extraction.claim_adjudication.v1"
_RELATIONAL_DECISIONS = frozenset(
    {"SAME_AS", "REFINES", "GENERALIZES", "CONTRADICTS"},
)
_MAX_CLAIMS_PER_ADJUDICATION_BATCH = 12
_MAX_PRIOR_CLAIMS_IN_PROMPT = 24

CLAIM_ADJUDICATION_SYSTEM_PROMPT = """You independently adjudicate extracted biomedical claims against their frozen source excerpts.

For every claim reference, return exactly one categorical decision. Never return confidence, probability, quality, importance, or any other numeric score.

Atomicity:
- ATOMIC: one scientific assertion with one predicate and one endpoint pair.
- BUNDLED: multiple assertions or predicates have been combined.
- ABSTAIN: atomicity cannot be determined from the supplied source.

Source support:
- ENTAILED: the exact source explicitly supports the complete claim.
- CONTRADICTED: the source explicitly conflicts with the claim.
- INSUFFICIENT: the source does not establish the complete claim.
- ABSTAIN: support cannot be determined safely.

Relationship:
- CANONICAL: retain this as the first independent representation.
- SAME_AS: equivalent to an earlier claim despite wording differences.
- REFINES: adds source-supported context or specificity to an earlier claim.
- GENERALIZES: removes material context from an earlier claim.
- CONTRADICTS: conflicts with an earlier claim.
- ABSTAIN: no safe relationship decision, including bundled claims.

Only target an earlier claim reference. Preserve negative, null, uncertain, provisional, and hypothesis semantics. A hypothesis is not an asserted finding. Copy exact source evidence spans for ENTAILED claims. Explain what source change would falsify each judgment. Do not use outside knowledge."""


class ClaimAdjudicationAgent(Protocol):
    """Injectable agent boundary used by focused tests and alternate runtimes."""

    model_id: str

    async def adjudicate(self, *, prompt: str) -> ClaimAdjudicationOutput:
        """Return categorical decisions for the supplied claims."""


async def adjudicate_document_claims(
    *,
    document: HarnessDocumentRecord,
    drafts: tuple[HarnessProposalDraft, ...],
    agent: ClaimAdjudicationAgent | None = None,
) -> tuple[tuple[HarnessProposalDraft, ...], ClaimAdjudicationDiagnostics]:
    """Adjudicate claims and apply deterministic review-only safety floors."""

    claim_drafts = tuple(
        draft for draft in drafts if draft.proposal_type == "candidate_claim"
    )
    if not claim_drafts:
        return drafts, ClaimAdjudicationDiagnostics(status="not_needed")

    claim_refs = _claim_refs(claim_drafts)
    model_id = agent.model_id if agent is not None else ""
    collected_decisions: list[ClaimAdjudicationDecision] = []
    try:
        for batch_start in range(
            0,
            len(claim_drafts),
            _MAX_CLAIMS_PER_ADJUDICATION_BATCH,
        ):
            batch_end = min(
                batch_start + _MAX_CLAIMS_PER_ADJUDICATION_BATCH,
                len(claim_drafts),
            )
            batch_refs = claim_refs[batch_start:batch_end]
            batch_drafts = claim_drafts[batch_start:batch_end]
            prior_start = max(0, batch_start - _MAX_PRIOR_CLAIMS_IN_PROMPT)
            prompt = _build_prompt(
                claim_refs=batch_refs,
                drafts=batch_drafts,
                prior_claim_refs=claim_refs[prior_start:batch_start],
                prior_drafts=claim_drafts[prior_start:batch_start],
            )
            if agent is not None:
                output = await agent.adjudicate(prompt=prompt)
            else:
                output, model_id = await _run_kernel_agent(
                    document=document,
                    prompt=prompt,
                    output_schema=ClaimAdjudicationOutput,
                    schema_id="document_extraction.claim_adjudication.v1",
                )
            collected_decisions.extend(
                _validated_decisions(
                    output=output,
                    claim_refs=batch_refs,
                    drafts=batch_drafts,
                    ordered_document_claim_refs=claim_refs,
                    visible_claim_refs=(
                        *claim_refs[prior_start:batch_start],
                        *batch_refs,
                    ),
                    source_text=document.text_content,
                ),
            )
    except (RuntimeError, TimeoutError, ValidationError, ValueError) as exc:
        return (
            _mark_adjudication_unavailable(drafts),
            ClaimAdjudicationDiagnostics(
                status="unavailable",
                model_id=getattr(agent, "model_id", None),
                error=str(exc),
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return (
            _mark_adjudication_unavailable(drafts),
            ClaimAdjudicationDiagnostics(
                status="failed",
                model_id=getattr(agent, "model_id", None),
                error=str(exc),
            ),
        )

    decisions = tuple(collected_decisions)
    decisions_by_ref = {decision.claim_ref: decision for decision in decisions}
    drafts_by_ref = dict(zip(claim_refs, claim_drafts, strict=True))
    updated_claims: dict[int, HarnessProposalDraft] = {}
    for claim_ref, draft in zip(claim_refs, claim_drafts, strict=True):
        decision = decisions_by_ref[claim_ref]
        target_ref = decision.target_claim_ref
        updated_claims[id(draft)] = _apply_decision(
            draft=draft,
            decision=decision,
            model_id=model_id,
            target_draft=(
                drafts_by_ref.get(target_ref) if target_ref is not None else None
            ),
        )
    return (
        tuple(updated_claims.get(id(draft), draft) for draft in drafts),
        ClaimAdjudicationDiagnostics(
            status="completed",
            model_id=model_id,
            decision_count=len(decisions),
            metrics=claim_adjudication_metrics(decisions),
        ),
    )


def _claim_refs(drafts: Sequence[HarnessProposalDraft]) -> tuple[str, ...]:
    return tuple(f"claim-{index:04d}" for index in range(1, len(drafts) + 1))


def _build_prompt(
    *,
    claim_refs: Sequence[str],
    drafts: Sequence[HarnessProposalDraft],
    prior_claim_refs: Sequence[str] = (),
    prior_drafts: Sequence[HarnessProposalDraft] = (),
) -> str:
    blocks = [
        _claim_prompt_block(claim_ref=claim_ref, draft=draft)
        for claim_ref, draft in zip(claim_refs, drafts, strict=True)
    ]
    prior_blocks = [
        "\n".join(
            (
                f"Prior claim reference: {claim_ref}",
                f"- subject: {_draft_label(draft, 'subject')}",
                f"- relation: {draft.payload.get('proposed_claim_type')}",
                f"- object: {_draft_label(draft, 'object')}",
                f"- exact source excerpt: {draft.summary}",
            ),
        )
        for claim_ref, draft in zip(prior_claim_refs, prior_drafts, strict=True)
    ]
    prior_section = (
        "PRIOR CLAIMS AVAILABLE ONLY AS RELATION TARGETS\n"
        f"{'\n\n'.join(prior_blocks)}\n\n"
        if prior_blocks
        else ""
    )
    return (
        f"Prompt identity: {_PROMPT_ID}\n\n"
        f"{CLAIM_ADJUDICATION_SYSTEM_PROMPT}\n\n"
        f"{prior_section}CLAIMS TO ADJUDICATE IN SOURCE ORDER\n"
        f"{'\n\n'.join(blocks)}\n\n"
        "Return one decision for every claim reference exactly once."
    )


def _claim_prompt_block(
    *,
    claim_ref: str,
    draft: HarnessProposalDraft,
) -> str:
    frame = draft.payload.get("claim_frame")
    frame_payload = frame if isinstance(frame, Mapping) else {}
    return "\n".join(
        (
            f"Claim reference: {claim_ref}",
            f"- subject: {_draft_label(draft, 'subject')}",
            f"- relation: {draft.payload.get('proposed_claim_type')}",
            f"- object: {_draft_label(draft, 'object')}",
            f"- polarity: {frame_payload.get('polarity')}",
            f"- epistemic_status: {frame_payload.get('epistemic_status')}",
            f"- exact source excerpt: {draft.summary}",
        ),
    )


def _draft_label(draft: HarnessProposalDraft, endpoint: str) -> object:
    return draft.metadata.get(f"resolved_{endpoint}_label") or draft.metadata.get(
        f"{endpoint}_label",
    )


async def _run_kernel_agent(
    *,
    document: HarnessDocumentRecord,
    prompt: str,
    output_schema: type[ClaimAdjudicationOutput],
    schema_id: str,
) -> tuple[ClaimAdjudicationOutput, str]:
    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
    from artana.ports.model import LiteLLMAdapter
    from artana_evidence_api.runtime import (
        ModelCapability,
        create_artana_postgres_store,
        get_model_registry,
        has_configured_openai_api_key,
        normalize_litellm_model_id,
    )
    from artana_evidence_api.step_helpers import run_single_step_with_policy

    if not has_configured_openai_api_key():
        raise RuntimeError("OPENAI_API_KEY not configured")
    if output_schema is not ClaimAdjudicationOutput or schema_id != _SCHEMA_ID:
        raise RuntimeError("claim adjudication schema binding is invalid")

    model_spec = get_model_registry().get_default_model(ModelCapability.JUDGE)
    model_id = normalize_litellm_model_id(model_spec.model_id)
    step_key = f"{_SCHEMA_ID}:{hashlib.sha256(prompt.encode('utf-8')).hexdigest()}"
    store = create_artana_postgres_store()
    kernel = ArtanaKernel(
        store=store,
        model_port=LiteLLMAdapter(timeout_seconds=model_spec.timeout_seconds),
    )
    try:
        result = await asyncio.wait_for(
            run_single_step_with_policy(
                SingleStepModelClient(kernel=kernel),
                run_id=f"claim-adjudication:{uuid4()}",
                tenant=TenantContext(
                    tenant_id=f"claim-adjudication:{document.space_id}",
                    capabilities=frozenset(),
                    budget_usd_limit=1.0,
                ),
                model=model_id,
                prompt=prompt,
                output_schema=output_schema,
                schema_id="document_extraction.claim_adjudication.v1",
                step_key=step_key,
                replay_policy="fork_on_drift",
            ),
            timeout=model_spec.timeout_seconds,
        )
        output = (
            result.output
            if isinstance(result.output, ClaimAdjudicationOutput)
            else ClaimAdjudicationOutput.model_validate(result.output)
        )
        return output, model_spec.model_id
    finally:
        with suppress(Exception):
            await kernel.close()
        with suppress(Exception):
            await store.close()


def _validated_decisions(
    *,
    output: ClaimAdjudicationOutput,
    claim_refs: Sequence[str],
    drafts: Sequence[HarnessProposalDraft],
    ordered_document_claim_refs: Sequence[str],
    visible_claim_refs: Sequence[str],
    source_text: str,
) -> tuple[ClaimAdjudicationDecision, ...]:
    expected = tuple(claim_refs)
    actual = tuple(decision.claim_ref for decision in output.decisions)
    if len(set(actual)) != len(actual):
        raise ValueError("claim adjudication returned duplicate claim references")
    if set(actual) != set(expected):
        raise ValueError("claim adjudication must cover every claim exactly once")

    index_by_ref = {
        claim_ref: index for index, claim_ref in enumerate(ordered_document_claim_refs)
    }
    visible_refs = frozenset(visible_claim_refs)
    draft_by_ref = dict(zip(expected, drafts, strict=True))
    decisions_by_ref = {decision.claim_ref: decision for decision in output.decisions}
    ordered = tuple(decisions_by_ref[claim_ref] for claim_ref in expected)
    for decision in ordered:
        if decision.target_claim_ref is not None:
            target_index = index_by_ref.get(decision.target_claim_ref)
            if target_index is None:
                raise ValueError("claim relationship target is not in this document")
            if decision.target_claim_ref not in visible_refs:
                raise ValueError(
                    "claim relationship target is outside the adjudication context",
                )
            if target_index >= index_by_ref[decision.claim_ref]:
                raise ValueError("claim relationships must target an earlier claim")
        for span in decision.evidence_spans:
            if span.strip() == "" or span not in source_text:
                raise ValueError("claim evidence span is not exact frozen source text")
            if span not in draft_by_ref[decision.claim_ref].summary:
                raise ValueError(
                    "claim evidence span is outside the adjudicated claim excerpt",
                )
    return ordered


def _apply_decision(
    *,
    draft: HarnessProposalDraft,
    decision: ClaimAdjudicationDecision,
    model_id: str,
    target_draft: HarnessProposalDraft | None,
) -> HarnessProposalDraft:
    support = {
        "ENTAILED": "ENTAILS",
        "CONTRADICTED": "CONTRADICTS",
        "INSUFFICIENT": "NEUTRAL",
        "ABSTAIN": "NEUTRAL",
    }[decision.source_support]
    adjudication: JSONObject = cast(
        "JSONObject",
        json_value(decision.model_dump(mode="json")),
    )
    metadata: JSONObject = {
        **draft.metadata,
        "claim_semantic_adjudication": adjudication,
        "support_verification": {
            "support": support,
            "rationale": decision.reasoning,
            "model_id": model_id,
            "verification_method": "agent",
            "evidence_spans": list(decision.evidence_spans),
            "falsification": decision.falsification,
        },
    }
    if decision.relationship in _RELATIONAL_DECISIONS and target_draft is not None:
        metadata["claim_relation_proposal"] = {
            "relation_type": decision.relationship,
            "target_source_key": target_draft.source_key,
            "target_claim_fingerprint": target_draft.claim_fingerprint,
            "evidence_summary": decision.reasoning,
            "review_status": "PROPOSED",
        }
    reason = _review_only_reason(decision)
    if reason is not None:
        metadata = _with_review_only_reason(metadata=metadata, reason=reason)
    confidence, ranking_score = _deterministic_score_floors(
        draft=draft,
        source_support=decision.source_support,
    )
    return replace(
        draft,
        metadata=metadata,
        confidence=confidence,
        ranking_score=ranking_score,
    )


def _review_only_reason(decision: ClaimAdjudicationDecision) -> str | None:
    if decision.atomicity != "ATOMIC":
        return f"claim_atomicity_{decision.atomicity.casefold()}"
    if decision.source_support != "ENTAILED":
        return f"claim_support_{decision.source_support.casefold()}"
    if decision.relationship != "CANONICAL":
        return f"claim_relationship_{decision.relationship.casefold()}"
    return None


def _with_review_only_reason(*, metadata: JSONObject, reason: str) -> JSONObject:
    existing = metadata.get("review_reason_codes")
    reason_codes = (
        [item for item in existing if isinstance(item, str)]
        if isinstance(
            existing,
            list,
        )
        else []
    )
    return {
        **metadata,
        "review_status": "review_only",
        "review_reason_codes": list(dict.fromkeys((*reason_codes, reason))),
    }


def _deterministic_score_floors(
    *,
    draft: HarnessProposalDraft,
    source_support: str,
) -> tuple[float, float]:
    if source_support == "ENTAILED":
        return draft.confidence, draft.ranking_score
    ceiling = 0.05 if source_support == "CONTRADICTED" else 0.25
    return min(draft.confidence, ceiling), min(draft.ranking_score, ceiling)


def _mark_adjudication_unavailable(
    drafts: tuple[HarnessProposalDraft, ...],
) -> tuple[HarnessProposalDraft, ...]:
    updated: list[HarnessProposalDraft] = []
    for draft in drafts:
        if draft.proposal_type != "candidate_claim":
            updated.append(draft)
            continue
        metadata = _with_review_only_reason(
            metadata={
                **draft.metadata,
                "support_verification": {
                    "support": "NEUTRAL",
                    "rationale": "Independent agent adjudication was unavailable.",
                    "model_id": None,
                    "verification_method": "unavailable",
                    "evidence_spans": [],
                    "falsification": "Agent adjudication must complete.",
                },
            },
            reason="claim_adjudication_unavailable",
        )
        updated.append(
            replace(
                draft,
                metadata=metadata,
                confidence=min(draft.confidence, 0.25),
                ranking_score=min(draft.ranking_score, 0.25),
            ),
        )
    return tuple(updated)


__all__ = [
    "CLAIM_ADJUDICATION_SYSTEM_PROMPT",
    "ClaimAdjudicationAgent",
    "adjudicate_document_claims",
]
