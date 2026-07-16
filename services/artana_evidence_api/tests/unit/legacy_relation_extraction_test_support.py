"""Test-only harness for pre-Q1 relation-output unit cases.

The production runner never imports this module. It lets older tests continue
to exercise downstream filtering, CURIE handling, store cleanup, and legacy
retry edge cases without restoring the removed multi-relation production path.
"""

from __future__ import annotations

from artana_evidence_api.document_extraction_contracts import (
    ExtractedRelationCandidate,
)
from artana_evidence_api.document_extraction_relation_taxonomy import (
    LLM_VALID_RELATION_TYPES,
)
from artana_evidence_api.document_extraction_support.full_text_chunking import (
    RelationExtractionTextChunk,
)
from artana_evidence_api.document_extraction_support.llm_extraction.runner import (
    LLMRelationExtractionAttempt,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    LLM_EXTRACTION_PROMPT_VERSION,
    LLM_WEAK_REVIEW_EXTRACTION_PROMPT_VERSION,
    ModelStepRunner,
    build_llm_extraction_prompt,
    build_llm_weak_review_extraction_prompt,
    llm_extraction_step_key,
    run_llm_relation_extraction_pass,
)
from pydantic import BaseModel, ValidationError

_WEAK_REVIEW_AGENT_PASS_REASON = "weak_review_agent_pass"
_ZERO_RETRY_SUFFIX = "zero_candidate_retry.v1"
_SCHEMA_RETRY_SUFFIX = "schema_retry.v1"
_ZERO_RETRY_INSTRUCTION = """

ZERO-CANDIDATE RETRY:
A prior relation extraction attempt returned zero usable relations for this same text.
Re-read the text carefully. If the text states a direct biomedical relation, return the
specific relation. If the text truly contains no asserted relation, return an empty relation list.
Do not invent relations, and do not use deterministic fallback output.
"""
_SCHEMA_RETRY_INSTRUCTION = """

SCHEMA REPAIR RETRY:
A prior relation extraction attempt failed schema validation for this same text.
Return the same evidence only if it is directly asserted, but repair the JSON so it
passes the schema. Do not set proposed_relation_type when relation_type is already
one of the canonical allowed relation types. Only use proposed_relation_type when
relation_type is UNKNOWN_RELATION_TYPE.
"""


def _has_usable_candidate(attempt: LLMRelationExtractionAttempt) -> bool:
    return any(
        candidate.relation_type in LLM_VALID_RELATION_TYPES
        for candidate in attempt.candidates
    )


async def _run_pass_with_schema_retry(
    *,
    step_runner: ModelStepRunner,
    client: object,
    tenant: object,
    model_id: str,
    prompt: str,
    output_schema: type[BaseModel],
    step_key: str,
    schema_retry_prompt: str,
    schema_retry_step_key: str,
    force_review_only_reason_codes: tuple[str, ...],
) -> tuple[
    list[ExtractedRelationCandidate],
    set[str],
    int,
    tuple[dict[str, object], ...],
]:
    try:
        (
            candidates,
            unknown,
            raw_count,
            raw_output,
        ) = await run_llm_relation_extraction_pass(
            step_runner=step_runner,
            client=client,
            tenant=tenant,
            model_id=model_id,
            prompt=prompt,
            output_schema=output_schema,
            step_key=step_key,
            force_review_only_reason_codes=force_review_only_reason_codes,
        )
    except ValidationError:
        (
            candidates,
            unknown,
            raw_count,
            raw_output,
        ) = await run_llm_relation_extraction_pass(
            step_runner=step_runner,
            client=client,
            tenant=tenant,
            model_id=model_id,
            prompt=schema_retry_prompt,
            output_schema=output_schema,
            step_key=schema_retry_step_key,
            force_review_only_reason_codes=force_review_only_reason_codes,
        )
    return candidates, unknown, raw_count, (raw_output,)


async def _run_attempt(
    *,
    chunks: tuple[RelationExtractionTextChunk, ...],
    max_relations: int,
    document_fingerprint: str,
    output_schema: type[BaseModel],
    weak_review_output_schema: type[BaseModel],
    client: object,
    tenant: object,
    model_id: str,
    step_runner: ModelStepRunner,
    execution_namespace: str,
    retry_suffix: str | None = None,
) -> LLMRelationExtractionAttempt:
    candidates: list[ExtractedRelationCandidate] = []
    unknown_relation_types: set[str] = set()
    raw_relation_count = 0
    raw_agent_outputs: list[dict[str, object]] = []
    for chunk in chunks:
        primary_candidates: list[ExtractedRelationCandidate] = []
        passes = (
            (
                LLM_EXTRACTION_PROMPT_VERSION,
                build_llm_extraction_prompt(
                    chunk=chunk,
                    total_chunks=len(chunks),
                    document_fingerprint=document_fingerprint,
                ),
                output_schema,
                (),
            ),
            (
                LLM_WEAK_REVIEW_EXTRACTION_PROMPT_VERSION,
                build_llm_weak_review_extraction_prompt(
                    chunk=chunk,
                    total_chunks=len(chunks),
                    document_fingerprint=document_fingerprint,
                ),
                weak_review_output_schema,
                (_WEAK_REVIEW_AGENT_PASS_REASON,),
            ),
        )
        for prompt_version, prompt, schema, forced_reasons in passes:
            weak_pass = bool(forced_reasons)
            if weak_pass and any(
                item.relation_type in LLM_VALID_RELATION_TYPES
                for item in primary_candidates
            ):
                continue
            effective_prompt = (
                prompt if retry_suffix is None else f"{prompt}{_ZERO_RETRY_INSTRUCTION}"
            )
            effective_version = (
                prompt_version
                if retry_suffix is None
                else f"{prompt_version}.{retry_suffix}"
            )
            step_key = llm_extraction_step_key(
                text=chunk.text,
                max_relations=max_relations,
                model_id=model_id,
                prompt_version=effective_version,
                chunk_index=chunk.index,
                total_chunks=len(chunks),
                document_fingerprint=document_fingerprint,
                execution_namespace=execution_namespace,
            )
            schema_retry_step_key = llm_extraction_step_key(
                text=chunk.text,
                max_relations=max_relations,
                model_id=model_id,
                prompt_version=f"{effective_version}.{_SCHEMA_RETRY_SUFFIX}",
                chunk_index=chunk.index,
                total_chunks=len(chunks),
                document_fingerprint=document_fingerprint,
                execution_namespace=execution_namespace,
            )
            try:
                (
                    chunk_candidates,
                    chunk_unknown,
                    chunk_count,
                    raw_outputs,
                ) = await _run_pass_with_schema_retry(
                    step_runner=step_runner,
                    client=client,
                    tenant=tenant,
                    model_id=model_id,
                    prompt=effective_prompt,
                    output_schema=schema,
                    step_key=step_key,
                    schema_retry_prompt=f"{effective_prompt}{_SCHEMA_RETRY_INSTRUCTION}",
                    schema_retry_step_key=schema_retry_step_key,
                    force_review_only_reason_codes=forced_reasons,
                )
            except Exception:  # noqa: BLE001
                if weak_pass:
                    continue
                raise
            candidates.extend(chunk_candidates)
            unknown_relation_types.update(chunk_unknown)
            raw_relation_count += chunk_count
            raw_agent_outputs.extend(raw_outputs)
            if not weak_pass:
                primary_candidates = chunk_candidates
    return LLMRelationExtractionAttempt(
        candidates=candidates,
        unknown_relation_types=unknown_relation_types,
        raw_relation_count=raw_relation_count,
        processed_chunk_count=len(chunks),
        raw_agent_outputs=tuple(raw_agent_outputs),
    )


async def run_legacy_relation_extraction_for_tests(
    *,
    normalized_text: str,
    chunks: tuple[RelationExtractionTextChunk, ...],
    max_relations: int,
    document_fingerprint: str,
    output_schema: type[BaseModel],
    weak_review_output_schema: type[BaseModel],
    client: object,
    tenant: object,
    model_id: str,
    step_runner: ModelStepRunner,
    execution_namespace: str = "",
) -> LLMRelationExtractionAttempt:
    """Run the removed relation-list contract for old downstream unit tests only."""

    first = await _run_attempt(
        chunks=chunks,
        max_relations=max_relations,
        document_fingerprint=document_fingerprint,
        output_schema=output_schema,
        weak_review_output_schema=weak_review_output_schema,
        client=client,
        tenant=tenant,
        model_id=model_id,
        step_runner=step_runner,
        execution_namespace=execution_namespace,
    )
    if _has_usable_candidate(first) or not normalized_text.strip():
        return first
    retry = await _run_attempt(
        chunks=chunks,
        max_relations=max_relations,
        document_fingerprint=document_fingerprint,
        output_schema=output_schema,
        weak_review_output_schema=weak_review_output_schema,
        client=client,
        tenant=tenant,
        model_id=model_id,
        step_runner=step_runner,
        execution_namespace=execution_namespace,
        retry_suffix=_ZERO_RETRY_SUFFIX,
    )
    return LLMRelationExtractionAttempt(
        candidates=[*first.candidates, *retry.candidates],
        unknown_relation_types=(
            first.unknown_relation_types | retry.unknown_relation_types
        ),
        raw_relation_count=first.raw_relation_count + retry.raw_relation_count,
        processed_chunk_count=len(chunks),
        raw_agent_outputs=(*first.raw_agent_outputs, *retry.raw_agent_outputs),
    )


__all__ = ["run_legacy_relation_extraction_for_tests"]
