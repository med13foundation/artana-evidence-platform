"""Forward-only selection contract for the deterministically extended reserve."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from scripts.validation.public_gold.staged_event.contracts import StrictStageModel
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.contracts import (
    FreshCGCase,  # noqa: TC001 - Pydantic runtime contract.
    SkippedDocument,  # noqa: TC001 - Pydantic runtime contract.
)


class FreshCGSelectionV2(StrictStageModel):
    """Eight cases after excluding V1's consumed case and extending the reserve."""

    schema_version: Literal["artana.staged_generalization.fresh_cg_selection.v2"] = (
        "artana.staged_generalization.fresh_cg_selection.v2"
    )
    selection_policy_version: Literal[
        "artana.staged_generalization.fresh_cg_selection_policy.v1"
    ] = "artana.staged_generalization.fresh_cg_selection_policy.v1"
    reservation_extension_policy: Literal[
        "SAME_SALTED_ORDER_FIRST_ELIGIBLE_AFTER_ORIGINAL_TWELVE"
    ]
    reservation_base_commit: str = Field(min_length=1)
    reservation_salt: str = Field(min_length=1)
    original_reserve_order: tuple[str, ...] = Field(min_length=12, max_length=12)
    extended_reserve_order: tuple[str, ...] = Field(min_length=13)
    selected_document_ids: tuple[str, ...] = Field(min_length=8, max_length=8)
    unused_original_document_ids: tuple[str, ...] = Field(
        min_length=5,
        max_length=5,
    )
    consumed_case_id: str = Field(min_length=1)
    consumed_document_id: str = Field(pattern=r"^PMID-\d+$")
    replacement_document_id: str = Field(pattern=r"^PMID-\d+$")
    replacement_reserve_position: int = Field(ge=13)
    skipped_documents: tuple[SkippedDocument, ...]
    cases: tuple[FreshCGCase, ...] = Field(min_length=8, max_length=8)
    provider_packet_excludes: tuple[str, ...]
    model_outputs_used_for_selection: Literal[False] = False
    unresolved_coreference_rule: Literal[
        "DIRECT_TEXT_BOUND_CORE_ARGUMENTS_WITH_NO_PRONOMINAL_MENTIONS"
    ] = "DIRECT_TEXT_BOUND_CORE_ARGUMENTS_WITH_NO_PRONOMINAL_MENTIONS"

    @model_validator(mode="after")
    def validate_extension_and_cases(self) -> FreshCGSelectionV2:
        if self.extended_reserve_order[:12] != self.original_reserve_order:
            raise ValueError("reserve extension changed the original twelve")
        if len(set(self.extended_reserve_order)) != len(self.extended_reserve_order):
            raise ValueError("extended reserve contains duplicate documents")
        replacement_index = self.replacement_reserve_position - 1
        if (
            self.extended_reserve_order[replacement_index]
            != self.replacement_document_id
        ):
            raise ValueError("replacement position differs from extended reserve")
        if self.replacement_reserve_position != len(self.extended_reserve_order):
            raise ValueError("reserve must stop at the first eligible replacement")
        case_ids = tuple(case.case_id for case in self.cases)
        if self.consumed_case_id in case_ids:
            raise ValueError("consumed V1 case re-entered the experiment")
        if tuple(case.document_id for case in self.cases) != self.selected_document_ids:
            raise ValueError("selected document order differs from case order")
        if tuple(case.case_order for case in self.cases) != tuple(range(1, 9)):
            raise ValueError("fresh case order must be exactly one through eight")
        if self.cases[-1].document_id != self.replacement_document_id:
            raise ValueError("replacement case must be eighth")
        if self.consumed_document_id not in self.unused_original_document_ids:
            raise ValueError("consumed document must remain excluded")
        return self


__all__ = ["FreshCGSelectionV2"]
