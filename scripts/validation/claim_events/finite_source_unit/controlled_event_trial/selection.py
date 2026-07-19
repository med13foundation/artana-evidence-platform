"""Deterministic fresh controlled-event selection before provider execution."""

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

_SELECTION_SEED: Final = "5d494a1467e1ce5ff38575a4fd24162ad71394da"
_EXPECTED_CASE_ID: Final = "bionlp-ge-2011:PMC-2222968-06-Results-05"
_EXPECTED_UNIT_INDEX: Final = 11
_EXPECTED_UNIT_ID: Final = (
    "source-unit-02c41780fd8d83965debdc337f89adce6283552fa76ac7d36ee12c56060ef21b"
)
_EXPECTED_SOURCE_SHA256: Final = (
    "ecdada19b46e778707b2b0804ba4f75098678a0f2dac65aedd458c55fb3ff2ba"
)
_EXPECTED_INPUT_SHA256: Final = (
    "f278e87030694fc31da95804cb04664fe19fd6fe23526024c4b6ddf35183f0c4"
)
_EXPECTED_SELECTION_RANK: Final = (
    "2f0ce84394e893d0f145e72fdd0bfd1cdc8ea3b877f40dfda4e90e263bb484ff"
)
_AUTHORITATIVE_ARTICLE_URL: Final = "https://pmc.ncbi.nlm.nih.gov/articles/PMC2222968/"
_PRIOR_EXPOSED_CASE_IDS: Final = frozenset(
    {
        "bionlp-ge-2011:PMID-9361029",
        "bionlp-ge-2011:PMC-2222968-03-Results-02",
        "bionlp-ge-2011:PMC-2222968-05-Results-04",
        "bionlp-ge-2011:PMC-2222968-15-Materials_and_Methods-07",
        "bionlp-ge-2011:PMC-1134658-06-Results-05",
        "bionlp-ge-2011:PMID-7537762",
    }
)
_PRIOR_EXPOSED_UNIT_IDS: Final = frozenset(
    {
        "source-unit-063ab2e2ce044fe71c9f700805f4ed61be4a66879bd9aa3d50e7a683c2ee3af1",
        "source-unit-a1e6d72064289601fc6e82446a14036433e1b1bf32cd014de2c817bf7b4cfde9",
        "source-unit-e14e44064324af2f721a3d02d2caf44c00218a0ab6c4afc58e9bace413c9d46c",
        "source-unit-20ebe2019ebdd3e3651c8886f9f60c7d171883555237b2df667a47f90bab35f0",
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
class ControlledEventTrialSelection:
    """One source unit selected without exposing its expert event to the model."""

    case_id: str
    unit: FrozenSourceUnit
    expert_events: tuple[NaryClaimEvent, ...]
    selection_rank: str
    exposure_registry_sha256: str
    authoritative_article_url: str


def select_controlled_event_trial(
    fixture: NaryClaimFixture,
) -> ControlledEventTrialSelection:
    """Choose the lowest seeded rank among fresh causal-regulation units."""

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
            if unit.unit_id in _PRIOR_EXPOSED_UNIT_IDS:
                continue
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
                f"{_SELECTION_SEED}:controlled-event:{unit.unit_id}".encode(),
            ).hexdigest()
            candidates.append((rank, case.case_id, unit, local_events))
    if not candidates:
        raise RuntimeError("no fresh controlled-event source unit is available")
    rank, case_id, unit, expert_events = min(candidates, key=lambda item: item[0])
    if (
        rank != _EXPECTED_SELECTION_RANK
        or case_id != _EXPECTED_CASE_ID
        or unit.index != _EXPECTED_UNIT_INDEX
        or unit.unit_id != _EXPECTED_UNIT_ID
        or unit.source_sha256 != _EXPECTED_SOURCE_SHA256
        or unit.input_sha256 != _EXPECTED_INPUT_SHA256
    ):
        raise RuntimeError("pre-registered controlled-event selection changed")
    return ControlledEventTrialSelection(
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
        "scope": "tracked TG-04 live reports through merged PR #177",
        "prior_exposed_case_ids": sorted(_PRIOR_EXPOSED_CASE_IDS),
        "prior_exposed_unit_ids": sorted(_PRIOR_EXPOSED_UNIT_IDS),
        "selection_seed": _SELECTION_SEED,
        "selection_rule": "lowest_sha256_causal_regulation_unit",
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
    ).hexdigest()


__all__ = ["ControlledEventTrialSelection", "select_controlled_event_trial"]
