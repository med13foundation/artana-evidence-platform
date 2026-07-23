"""Blinded replacement review and composition with seven sealed V1 judgments."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from pydantic import Field

from scripts.validation.public_gold.staged_event.contracts import StrictStageModel
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.agreement import (
    ReferenceBuildInputs,
    ReviewArtifactInput,
    build_two_lane_reference,
    load_reviewer_artifact,
    write_two_lane_reference,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.config import (
    DEFAULT_PATHS as V1_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.contracts import (
    Sha256,  # noqa: TC001 - Pydantic resolves this type at runtime.
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.review_contracts import (
    FreshCGCaseSemanticReview,
    FreshCGReviewCasePacket,
    FreshCGReviewerArtifact,
    FreshCGReviewPacket,
    RetrievedPrimarySource,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.review_packets import (
    build_review_packet,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.config import (
    REPLACEMENT_DOCUMENT_ID,
    ExperimentPaths,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.selection import (
    load_v2_selection,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.contracts import (
        FreshCGSelection,
    )
    from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.reference_contracts import (
        FreshCGTwoLaneReference,
    )
    from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.contracts import (
        FreshCGSelectionV2,
    )


class ReplacementReviewFragmentV2(StrictStageModel):
    """One reviewer's source-only judgment of the added reserve case."""

    schema_version: Literal[
        "artana.staged_generalization.fresh_cg_replacement_reviewer.v2"
    ] = "artana.staged_generalization.fresh_cg_replacement_reviewer.v2"
    reviewer_id: str = Field(min_length=1)
    reviewer_task_identity: str = Field(min_length=1)
    reviewer_model_identity: str = Field(min_length=1)
    review_prompt_sha256: Sha256
    review_packet_sha256: Sha256
    internet_enabled: Literal[True] = True
    model_output_blinded: Literal[True] = True
    other_reviewer_output_blinded: Literal[True] = True
    implementation_reference_blinded: Literal[True] = True
    retrieved_source: RetrievedPrimarySource
    case: FreshCGCaseSemanticReview
    independence_declaration: str = Field(min_length=1)


class ReplacementReviewTaskV2(StrictStageModel):
    """Source-only task material shared identically with all reviewers."""

    schema_version: Literal[
        "artana.staged_generalization.fresh_cg_replacement_review_task.v2"
    ] = "artana.staged_generalization.fresh_cg_replacement_review_task.v2"
    review_prompt_sha256: Sha256
    full_review_packet_sha256: Sha256
    case: FreshCGReviewCasePacket
    omitted_from_packet: tuple[str, ...]


def write_review_packet(paths: ExperimentPaths) -> None:
    selection = load_v2_selection(paths.selection)
    packet = build_review_packet(
        cast("FreshCGSelection", selection),
        selection_artifact_sha256=_file_sha256(paths.selection),
    )
    paths.review_packet.parent.mkdir(parents=True, exist_ok=True)
    paths.review_packet.write_text(
        json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    task = ReplacementReviewTaskV2(
        review_prompt_sha256=_file_sha256(paths.review_prompt),
        full_review_packet_sha256=_file_sha256(paths.review_packet),
        case=packet.cases[-1],
        omitted_from_packet=packet.omitted_from_packet,
    )
    paths.replacement_review_packet.write_text(
        json.dumps(task.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths.replacement_review_schema.write_text(
        json.dumps(
            ReplacementReviewFragmentV2.model_json_schema(),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def compose_primary_reviewers(paths: ExperimentPaths) -> None:
    _compose_reviewer(
        paths,
        old_path=V1_PATHS.reviewer_a,
        fragment_path=paths.replacement_reviewer_a,
        output_path=paths.reviewer_a,
    )
    _compose_reviewer(
        paths,
        old_path=V1_PATHS.reviewer_b,
        fragment_path=paths.replacement_reviewer_b,
        output_path=paths.reviewer_b,
    )


def write_tiebreak_request(paths: ExperimentPaths) -> tuple[str, ...]:
    preliminary = build_reference(paths, include_tiebreaker=False)
    disputed = preliminary.unresolved_field_ids
    value: dict[str, object] = {
        "schema_version": ("artana.staged_generalization.fresh_cg_tiebreak_request.v2"),
        "review_packet_sha256": _file_sha256(paths.review_packet),
        "primary_reviewer_answers_disclosed": False,
        "replacement_case_id": _replacement_case_id(load_v2_selection(paths.selection)),
        "instruction": (
            "Independently adjudicate the replacement case. Only disputed fields "
            "will be used as tiebreak votes; retained V1 votes remain sealed."
        ),
        "disputed_field_ids": list(disputed),
    }
    paths.tiebreak_request.parent.mkdir(parents=True, exist_ok=True)
    paths.tiebreak_request.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return disputed


def compose_tiebreaker(paths: ExperimentPaths) -> None:
    _compose_reviewer(
        paths,
        old_path=V1_PATHS.tiebreaker,
        fragment_path=paths.replacement_tiebreaker,
        output_path=paths.tiebreaker,
    )


def build_reference(
    paths: ExperimentPaths,
    *,
    include_tiebreaker: bool,
) -> FreshCGTwoLaneReference:
    selection = load_v2_selection(paths.selection)
    packet = FreshCGReviewPacket.model_validate_json(
        paths.review_packet.read_text(encoding="utf-8")
    )
    reviewer_a = load_reviewer_artifact(paths.reviewer_a)
    reviewer_b = load_reviewer_artifact(paths.reviewer_b)
    tiebreaker = (
        ReviewArtifactInput(load_reviewer_artifact(paths.tiebreaker), paths.tiebreaker)
        if include_tiebreaker
        else None
    )
    return build_two_lane_reference(
        ReferenceBuildInputs(
            selection=cast("FreshCGSelection", selection),
            packet=packet,
            selection_artifact_path=paths.selection,
            review_packet_path=paths.review_packet,
            review_prompt_path=paths.review_prompt,
            primary_reviewers=(
                ReviewArtifactInput(reviewer_a, paths.reviewer_a),
                ReviewArtifactInput(reviewer_b, paths.reviewer_b),
            ),
            tiebreaker=tiebreaker,
        )
    )


def write_reference(paths: ExperimentPaths) -> None:
    write_two_lane_reference(
        paths.reference,
        build_reference(paths, include_tiebreaker=True),
    )


def _compose_reviewer(
    paths: ExperimentPaths,
    *,
    old_path: Path,
    fragment_path: Path,
    output_path: Path,
) -> None:
    selection = load_v2_selection(paths.selection)
    packet = FreshCGReviewPacket.model_validate_json(
        paths.review_packet.read_text(encoding="utf-8")
    )
    old = load_reviewer_artifact(old_path)
    fragment = ReplacementReviewFragmentV2.model_validate_json(
        fragment_path.read_text(encoding="utf-8")
    )
    _validate_fragment(fragment, paths, selection, packet, old.reviewer_id)
    old_cases = {case.case_id: case for case in old.cases}
    old_sources = {item.document_id: item for item in old.retrieved_sources}
    cases = tuple(
        fragment.case
        if case.document_id == REPLACEMENT_DOCUMENT_ID
        else old_cases[case.case_id]
        for case in selection.cases
    )
    sources = tuple(
        fragment.retrieved_source
        if case.document_id == REPLACEMENT_DOCUMENT_ID
        else old_sources[case.document_id]
        for case in selection.cases
    )
    artifact = FreshCGReviewerArtifact(
        reviewer_id=fragment.reviewer_id,
        reviewer_task_identity=fragment.reviewer_task_identity,
        reviewer_model_identity=fragment.reviewer_model_identity,
        review_prompt_sha256=fragment.review_prompt_sha256,
        review_packet_sha256=fragment.review_packet_sha256,
        retrieved_sources=sources,
        cases=cases,
        independence_declaration=fragment.independence_declaration,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(artifact.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _validate_fragment(
    fragment: ReplacementReviewFragmentV2,
    paths: ExperimentPaths,
    selection: FreshCGSelectionV2,
    packet: FreshCGReviewPacket,
    expected_reviewer_id: str,
) -> None:
    if fragment.reviewer_id != expected_reviewer_id:
        raise ValueError("replacement reviewer identity changed")
    if fragment.review_prompt_sha256 != _file_sha256(paths.review_prompt):
        raise ValueError("replacement review prompt hash changed")
    if fragment.review_packet_sha256 != _file_sha256(paths.review_packet):
        raise ValueError("replacement review packet hash changed")
    case_id = _replacement_case_id(selection)
    if fragment.case.case_id != case_id:
        raise ValueError("replacement review case identity changed")
    if fragment.retrieved_source.document_id != REPLACEMENT_DOCUMENT_ID:
        raise ValueError("replacement retrieval document identity changed")
    packet_case_ids = tuple(case.case_id for case in packet.cases)
    if packet_case_ids != tuple(case.case_id for case in selection.cases):
        raise ValueError("replacement packet differs from selection")


def _replacement_case_id(selection: FreshCGSelectionV2) -> str:
    return selection.cases[-1].case_id


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "ReplacementReviewFragmentV2",
    "ReplacementReviewTaskV2",
    "build_reference",
    "compose_primary_reviewers",
    "compose_tiebreaker",
    "write_reference",
    "write_review_packet",
    "write_tiebreak_request",
]
