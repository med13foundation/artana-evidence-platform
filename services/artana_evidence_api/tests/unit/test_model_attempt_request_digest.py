"""Reproducibility tests for the model-attempt request digest.

`prompt_sha256` is taken over the bound provider prompt, which embeds a fresh
`invocation_id` on every call.  It is therefore non-reproducible by design.
`request_digest` is taken over content only, so two runs of the same formal
request agree.  These tests pin that distinction.
"""

from __future__ import annotations

from artana_evidence_api.document_extraction_support.llm_extraction.attempt_audit import (
    model_attempt_request_digest,
)
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    bind_prompt_to_invocation,
)

_SOURCE = "a" * 64
_INPUT = "b" * 64
_EVIDENCE = "c" * 64
_SCHEMA = "d" * 64

_BASE = {
    "model_id": "openai:gpt-5.4-mini",
    "step_key": "research_init.claim_inventory.v3:abcd1234",
    "content_prompt_sha256": "e" * 64,
    "source_sha256": _SOURCE,
    "input_sha256": _INPUT,
    "evidence_unit_sha256": _EVIDENCE,
    "output_schema_sha256": _SCHEMA,
    "attempt_role": "claim_inventory",
    "pass_role": "primary",
    "retry_context": None,
    "semantic_unit_id": None,
}


def test_identical_requests_produce_an_identical_digest() -> None:
    assert model_attempt_request_digest(**_BASE) == model_attempt_request_digest(
        **_BASE
    )


def test_digest_is_a_lowercase_sha256() -> None:
    digest = model_attempt_request_digest(**_BASE)

    assert len(digest) == 64
    assert all(character in "0123456789abcdef" for character in digest)


def test_digest_survives_a_changing_invocation_binding() -> None:
    """The whole point: a fresh invocation id must not perturb the digest.

    Two calls with identical content produce different bound prompts, so their
    `prompt_sha256` differ.  The request digest must not.
    """

    prompt = "Extract claims from the following passage."
    first = bind_prompt_to_invocation(
        prompt=prompt,
        invocation_id="11111111-1111-4111-8111-111111111111",
        source_sha256=_SOURCE,
        input_sha256=_INPUT,
        evidence_unit_sha256=_EVIDENCE,
        output_schema_sha256=_SCHEMA,
    )
    second = bind_prompt_to_invocation(
        prompt=prompt,
        invocation_id="22222222-2222-4222-8222-222222222222",
        source_sha256=_SOURCE,
        input_sha256=_INPUT,
        evidence_unit_sha256=_EVIDENCE,
        output_schema_sha256=_SCHEMA,
    )

    assert first != second, "binding must vary with the invocation id"
    assert model_attempt_request_digest(**_BASE) == model_attempt_request_digest(
        **_BASE
    )


def test_each_content_field_changes_the_digest() -> None:
    """No identity-bearing input may be silently ignored by the hash."""

    baseline = model_attempt_request_digest(**_BASE)
    changed = {
        "model_id": "openai:gpt-5.6-luna",
        "step_key": "research_init.claim_inventory.v3:ffff0000",
        "content_prompt_sha256": "f" * 64,
        "source_sha256": "1" * 64,
        "input_sha256": "2" * 64,
        "evidence_unit_sha256": "3" * 64,
        "output_schema_sha256": "4" * 64,
        "attempt_role": "claim_verification",
        "pass_role": "retry",
        "retry_context": "zero_candidate_retry",
        "semantic_unit_id": "unit-7",
    }
    for field, value in changed.items():
        assert (
            model_attempt_request_digest(**{**_BASE, field: value}) != baseline
        ), f"{field} must change the request digest"


def test_absent_optional_fields_are_not_confusable_with_present_ones() -> None:
    """`None` must not collide with a value that stringifies the same way."""

    empty_semantic_unit = model_attempt_request_digest(
        **{**_BASE, "semantic_unit_id": ""}
    )
    absent_semantic_unit = model_attempt_request_digest(
        **{**_BASE, "semantic_unit_id": None}
    )

    assert empty_semantic_unit == absent_semantic_unit

    shifted = model_attempt_request_digest(
        **{**_BASE, "retry_context": None, "semantic_unit_id": "zero_candidate_retry"}
    )
    unshifted = model_attempt_request_digest(
        **{**_BASE, "retry_context": "zero_candidate_retry", "semantic_unit_id": None}
    )

    assert shifted != unshifted, "field boundaries must not be ambiguous"
