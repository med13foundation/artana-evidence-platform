"""Pre-registered selection of a second fresh causal-event source unit."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from artana_evidence_api.document_extraction import normalize_text_document

from scripts.validation.claim_events.contracts import (
    BenchmarkEventType,
    CaseControlStatus,
    EventRole,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    FrozenSourceUnit,
    enumerate_source_units,
)

if TYPE_CHECKING:
    from scripts.validation.claim_events.contracts import (
        NaryClaimEvent,
        NaryClaimFixture,
    )

_SELECTION_SEED: Final = (
    "7a97214a6540f4de7cfeefc8d556cbdc69e4f08e9f24a4410016bd902ef38435"
)
_EXPECTED_CASE_ID: Final = "bionlp-ge-2011:PMC-2806624-05-RESULTS-04"
_EXPECTED_UNIT_INDEX: Final = 7
_EXPECTED_UNIT_ID: Final = (
    "source-unit-6508d78fe2bb4886b606f91f2c990c36b55f54b2ac9886448e5251693222b3fe"
)
_EXPECTED_SOURCE_SHA256: Final = (
    "ab0322de4eb313be491e0bd0cfe2a6fef122ef8fa9b425c947d21b7ecb8e9da3"
)
_EXPECTED_INPUT_SHA256: Final = (
    "55ec5b34c0b7a0294792bd4bd696c1ff9db682548729352703ed3ac43d84ab50"
)
_EXPECTED_SELECTION_RANK: Final = (
    "06fac890eb60c0d5eb972e3b5f3fd9f3f0a623a72a47dd477a0b1fa81e9e001e"
)
_AUTHORITATIVE_ARTICLE_URL: Final = "https://pmc.ncbi.nlm.nih.gov/articles/PMC2806624/"
_PRIOR_EXPOSED_CASE_IDS: Final = frozenset(
    {
        "bionlp-ge-2011:PMID-9361029",
        "bionlp-ge-2011:PMC-2222968-03-Results-02",
        "bionlp-ge-2011:PMC-2222968-05-Results-04",
        "bionlp-ge-2011:PMC-2222968-15-Materials_and_Methods-07",
        "bionlp-ge-2011:PMC-1134658-06-Results-05",
        "bionlp-ge-2011:PMID-7537762",
        "bionlp-ge-2011:PMC-2222968-06-Results-05",
    }
)
_REGULATION_TYPES: Final = frozenset(
    {
        BenchmarkEventType.POSITIVE_REGULATION,
        BenchmarkEventType.NEGATIVE_REGULATION,
        BenchmarkEventType.REGULATION,
    }
)
_MAXIMUM_LOCAL_EVENT_COUNT: Final = 3


@dataclass(frozen=True, slots=True)
class GeneralizationTrialSelection:
    """One untouched source unit and its sealed minimum expert structure."""

    case_id: str
    unit: FrozenSourceUnit
    expert_events: tuple[NaryClaimEvent, ...]
    selection_rank: str
    exposure_registry_sha256: str
    authoritative_article_url: str


def select_generalization_trial(
    fixture: NaryClaimFixture,
) -> GeneralizationTrialSelection:
    """Choose the lowest reassessment-seeded rank among untouched causal units."""

    candidates: list[tuple[str, str, FrozenSourceUnit, tuple[NaryClaimEvent, ...]]] = []
    for case in fixture.cases:
        if (
            case.control_status is not CaseControlStatus.EVENT_GOLD
            or case.case_id in _PRIOR_EXPOSED_CASE_IDS
        ):
            continue
        units = enumerate_source_units(
            case_id=case.case_id,
            source_text=normalize_text_document(case.source_text),
        )
        for unit in units:
            local_events = tuple(
                event
                for event in case.events
                if unit.source_start <= event.trigger_source_start < unit.source_end
            )
            if not 1 <= len(local_events) <= _MAXIMUM_LOCAL_EVENT_COUNT or not any(
                _is_causal_regulation(event) for event in local_events
            ):
                continue
            rank = hashlib.sha256(
                f"{_SELECTION_SEED}:causal-event:{unit.unit_id}".encode(),
            ).hexdigest()
            candidates.append((rank, case.case_id, unit, local_events))
    if not candidates:
        raise RuntimeError("no untouched causal-event source unit is available")
    rank, case_id, unit, expert_events = min(candidates, key=lambda item: item[0])
    if (
        rank != _EXPECTED_SELECTION_RANK
        or case_id != _EXPECTED_CASE_ID
        or unit.index != _EXPECTED_UNIT_INDEX
        or unit.unit_id != _EXPECTED_UNIT_ID
        or unit.source_sha256 != _EXPECTED_SOURCE_SHA256
        or unit.input_sha256 != _EXPECTED_INPUT_SHA256
    ):
        raise RuntimeError("pre-registered generalization selection changed")
    return GeneralizationTrialSelection(
        case_id=case_id,
        unit=unit,
        expert_events=expert_events,
        selection_rank=rank,
        exposure_registry_sha256=_exposure_registry_sha256(),
        authoritative_article_url=_AUTHORITATIVE_ARTICLE_URL,
    )


def _is_causal_regulation(event: NaryClaimEvent) -> bool:
    return event.event_type in _REGULATION_TYPES and any(
        argument.event_role is EventRole.CAUSE for argument in event.arguments
    )


def _exposure_registry_sha256() -> str:
    payload = {
        "scope": "TG-04 live work through the successful zero-call reassessment",
        "prior_exposed_case_ids": sorted(_PRIOR_EXPOSED_CASE_IDS),
        "selection_seed": _SELECTION_SEED,
        "selection_rule": "lowest_sha256_untouched_causal_event_unit",
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
    ).hexdigest()


__all__ = ["GeneralizationTrialSelection", "select_generalization_trial"]
