"""Freeze the evaluator-only experiment identity before execution."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from scripts.validation.source_general_claim_verification.contracts import (
    SHA256_PATTERN,
    CorpusArtifact,
    FrozenPacketSet,
    StrictModel,
)
from scripts.validation.source_general_claim_verification.corpus import (
    validate_reference_set,
)
from scripts.validation.source_general_claim_verification.hashing import (
    canonical_sha256,
)

MAXIMUM_UNRESOLVED_RATE = 0.2


class AdjudicatorRegistration(StrictModel):
    role: Literal["FIRST", "SECOND", "TIEBREAKER"]
    model_id: str = Field(min_length=1)
    prompt_id: str = Field(min_length=1)
    prompt_sha256: str = Field(pattern=SHA256_PATTERN)


class PreregistrationDraft(StrictModel):
    schema_version: Literal["source_general_claim_verification.preregistration.v1"]
    corpus_sha256: str = Field(pattern=SHA256_PATTERN)
    packet_set_sha256: str = Field(pattern=SHA256_PATTERN)
    adjudicators: tuple[AdjudicatorRegistration, ...] = Field(min_length=2)
    framing_prompt_sha256: str = Field(pattern=SHA256_PATTERN)
    verification_prompt_sha256: str = Field(pattern=SHA256_PATTERN)
    repair_prompt_sha256: str = Field(pattern=SHA256_PATTERN)
    reverification_prompt_sha256: str = Field(pattern=SHA256_PATTERN)
    metric_contract_version: Literal["source_general_claim_verification.metrics.v1"]
    maximum_unresolved_rate: float = Field(
        default=MAXIMUM_UNRESOLVED_RATE,
        ge=0.0,
        le=1.0,
    )
    maximum_repairs_per_claim: Literal[1]
    agent_numeric_scores_allowed: Literal[False]
    exposed_sources_only: Literal[True]
    untouched_sources_allowed: Literal[False]
    graph_promotion_allowed: Literal[False]


class ExperimentPreregistration(PreregistrationDraft):
    preregistration_sha256: str = Field(pattern=SHA256_PATTERN)


def freeze_preregistration(
    draft: PreregistrationDraft,
    *,
    packet_set: FrozenPacketSet,
    corpus: CorpusArtifact,
) -> ExperimentPreregistration:
    """Authorize only a corpus-bound, validated packet set and complete prompts."""

    validate_reference_set(packet_set, corpus)
    if draft.corpus_sha256 != packet_set.corpus_sha256:
        raise ValueError("preregistration corpus hash does not match packet set")
    if draft.packet_set_sha256 != packet_set.packet_set_sha256:
        raise ValueError("preregistration packet-set hash does not match validated set")
    if draft.maximum_unresolved_rate != MAXIMUM_UNRESOLVED_RATE:
        raise ValueError(
            "preregistration must retain the 20 percent reliability ceiling"
        )
    roles = tuple(registration.role for registration in draft.adjudicators)
    if roles.count("FIRST") != 1 or roles.count("SECOND") != 1:
        raise ValueError(
            "preregistration requires exactly one FIRST and one SECOND adjudicator"
        )
    if roles.count("TIEBREAKER") > 1 or len(set(roles)) != len(roles):
        raise ValueError("adjudicator roles must be unique")
    payload = draft.model_dump(mode="json")
    return ExperimentPreregistration(
        **payload,
        preregistration_sha256=canonical_sha256(payload),
    )


__all__ = [
    "AdjudicatorRegistration",
    "ExperimentPreregistration",
    "PreregistrationDraft",
    "freeze_preregistration",
]
