"""LLM relation extraction pass orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from artana_evidence_api.document_extraction_contracts import (
    ExtractedRelationCandidate,
)
from artana_evidence_api.document_extraction_relation_taxonomy import (
    LLM_VALID_RELATION_TYPES,
)
from artana_evidence_api.document_extraction_support.full_text_chunking import (
    RelationExtractionTextChunk,
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
_LLM_ZERO_CANDIDATE_RETRY_PROMPT_SUFFIX = "zero_candidate_retry.v1"
_LLM_SCHEMA_RETRY_PROMPT_SUFFIX = "schema_retry.v1"
_LLM_ZERO_CANDIDATE_RETRY_INSTRUCTION = """

ZERO-CANDIDATE RETRY:
A prior relation extraction attempt returned zero usable relations for this same text.
Re-read the text carefully. If the text states a direct biomedical relation, return the
specific relation. If the text truly contains no asserted relation, return an empty relation list.
Do not invent relations, and do not use deterministic fallback output.
"""
_LLM_SCHEMA_RETRY_INSTRUCTION = """

SCHEMA REPAIR RETRY:
A prior relation extraction attempt failed schema validation for this same text.
Return the same evidence only if it is directly asserted, but repair the JSON so it
passes the schema. Do not set proposed_relation_type when relation_type is already
one of the canonical allowed relation types. Only use proposed_relation_type when
relation_type is UNKNOWN_RELATION_TYPE.
"""


@dataclass(slots=True)
class LLMRelationExtractionAttempt:
    candidates: list[ExtractedRelationCandidate]
    unknown_relation_types: set[str]
    raw_relation_count: int


def _should_retry_zero_candidate_agent_extraction(normalized_text: str) -> bool:
    return normalized_text.strip() != ""


def _has_usable_relation_candidate(
    candidates: list[ExtractedRelationCandidate],
) -> bool:
    return any(
        candidate.relation_type in LLM_VALID_RELATION_TYPES for candidate in candidates
    )


def _prompt_with_retry_instruction(prompt: str, retry_prompt_instruction: str) -> str:
    return f"{prompt}{retry_prompt_instruction}"


async def _run_llm_relation_extraction_attempt(
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
    retry_prompt_suffix: str | None = None,
    retry_prompt_instruction: str = "",
) -> LLMRelationExtractionAttempt:
    candidates: list[ExtractedRelationCandidate] = []
    unknown_relation_types: set[str] = set()
    raw_relation_count = 0
    for chunk in chunks:
        extraction_passes = (
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
        for prompt_version, prompt, pass_output_schema, force_review_only_reason_codes in (
            extraction_passes
        ):
            effective_prompt = (
                prompt
                if retry_prompt_suffix is None
                else _prompt_with_retry_instruction(prompt, retry_prompt_instruction)
            )
            effective_prompt_version = (
                prompt_version
                if retry_prompt_suffix is None
                else f"{prompt_version}.{retry_prompt_suffix}"
            )
            effective_step_key = llm_extraction_step_key(
                text=chunk.text,
                max_relations=max_relations,
                model_id=model_id,
                prompt_version=effective_prompt_version,
                chunk_index=chunk.index,
                total_chunks=len(chunks),
                document_fingerprint=document_fingerprint,
            )
            schema_retry_prompt_version = (
                f"{effective_prompt_version}.{_LLM_SCHEMA_RETRY_PROMPT_SUFFIX}"
            )
            schema_retry_step_key = llm_extraction_step_key(
                text=chunk.text,
                max_relations=max_relations,
                model_id=model_id,
                prompt_version=schema_retry_prompt_version,
                chunk_index=chunk.index,
                total_chunks=len(chunks),
                document_fingerprint=document_fingerprint,
            )
            chunk_candidates, chunk_unknown_relation_types, chunk_raw_count = (
                await _run_llm_relation_extraction_pass_with_schema_retry(
                    step_runner=step_runner,
                    client=client,
                    tenant=tenant,
                    model_id=model_id,
                    prompt=effective_prompt,
                    output_schema=pass_output_schema,
                    step_key=effective_step_key,
                    schema_retry_prompt=_prompt_with_retry_instruction(
                        effective_prompt,
                        _LLM_SCHEMA_RETRY_INSTRUCTION,
                    ),
                    schema_retry_step_key=schema_retry_step_key,
                    force_review_only_reason_codes=force_review_only_reason_codes,
                )
            )
            raw_relation_count += chunk_raw_count
            candidates.extend(chunk_candidates)
            unknown_relation_types.update(chunk_unknown_relation_types)
    return LLMRelationExtractionAttempt(
        candidates=candidates,
        unknown_relation_types=unknown_relation_types,
        raw_relation_count=raw_relation_count,
    )


async def _run_llm_relation_extraction_pass_with_schema_retry(
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
) -> tuple[list[ExtractedRelationCandidate], set[str], int]:
    try:
        return await run_llm_relation_extraction_pass(
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
        return await run_llm_relation_extraction_pass(
            step_runner=step_runner,
            client=client,
            tenant=tenant,
            model_id=model_id,
            prompt=schema_retry_prompt,
            output_schema=output_schema,
            step_key=schema_retry_step_key,
            force_review_only_reason_codes=force_review_only_reason_codes,
        )


async def run_llm_relation_extraction_with_zero_retry(
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
) -> LLMRelationExtractionAttempt:
    extraction_attempt = await _run_llm_relation_extraction_attempt(
        chunks=chunks,
        max_relations=max_relations,
        document_fingerprint=document_fingerprint,
        output_schema=output_schema,
        weak_review_output_schema=weak_review_output_schema,
        client=client,
        tenant=tenant,
        model_id=model_id,
        step_runner=step_runner,
    )
    if (
        _has_usable_relation_candidate(extraction_attempt.candidates)
        or not _should_retry_zero_candidate_agent_extraction(normalized_text)
    ):
        return extraction_attempt

    retry_attempt = await _run_llm_relation_extraction_attempt(
        chunks=chunks,
        max_relations=max_relations,
        document_fingerprint=document_fingerprint,
        output_schema=output_schema,
        weak_review_output_schema=weak_review_output_schema,
        client=client,
        tenant=tenant,
        model_id=model_id,
        step_runner=step_runner,
        retry_prompt_suffix=_LLM_ZERO_CANDIDATE_RETRY_PROMPT_SUFFIX,
        retry_prompt_instruction=_LLM_ZERO_CANDIDATE_RETRY_INSTRUCTION,
    )
    return LLMRelationExtractionAttempt(
        candidates=retry_attempt.candidates,
        unknown_relation_types=retry_attempt.unknown_relation_types,
        raw_relation_count=(
            extraction_attempt.raw_relation_count + retry_attempt.raw_relation_count
        ),
    )


__all__ = [
    "LLMRelationExtractionAttempt",
    "run_llm_relation_extraction_with_zero_retry",
]
