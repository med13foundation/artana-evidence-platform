"""Frozen fresh-unit selection and prior-exposure registry."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from artana_evidence_api.document_extraction import normalize_text_document

from scripts.validation.claim_events.finite_source_unit.source_units import (
    FrozenSourceUnit,
    enumerate_source_units,
)

if TYPE_CHECKING:
    from scripts.validation.claim_events.contracts import NaryClaimFixture

_CASE_ID: Final = "bionlp-ge-2011:PMID-7537762"
_UNIT_INDEX: Final = 4
_EXPECTED_UNIT_ID: Final = (
    "source-unit-20ebe2019ebdd3e3651c8886f9f60c7d171883555237b2df667a47f90bab35f0"
)
_EXPECTED_SOURCE_SHA256: Final = (
    "363b49c8071440e28f2d89c86814e1c9e370ffd27d0cc08969703eadea0922e4"
)
_EXPECTED_INPUT_SHA256: Final = (
    "517b4ab2c503e65ce9d1b11f6b77e2361215f642cd0c54eec6abbb785a88c905"
)
_ARTICLE_URL: Final = "https://pubmed.ncbi.nlm.nih.gov/7537762/"
_PRIOR_EXPOSED_CASE_IDS: Final = frozenset(
    {
        "bionlp-ge-2011:PMID-9361029",
        "bionlp-ge-2011:PMC-2222968-03-Results-02",
        "bionlp-ge-2011:PMC-2222968-05-Results-04",
        "bionlp-ge-2011:PMC-2222968-15-Materials_and_Methods-07",
        "bionlp-ge-2011:PMC-1134658-06-Results-05",
    },
)
_PRIOR_EXPOSED_UNIT_IDS: Final = frozenset(
    {
        "source-unit-063ab2e2ce044fe71c9f700805f4ed61be4a66879bd9aa3d50e7a683c2ee3af1",
        "source-unit-a1e6d72064289601fc6e82446a14036433e1b1bf32cd014de2c817bf7b4cfde9",
        "source-unit-e14e44064324af2f721a3d02d2caf44c00218a0ab6c4afc58e9bace413c9d46c",
    },
)


@dataclass(frozen=True, slots=True)
class FreshUnitSelection:
    """Frozen unit plus bounded evidence that it was not previously exposed."""

    unit: FrozenSourceUnit
    hidden_expert_event_count: int
    exposure_registry_sha256: str
    authoritative_article_url: str


def select_fresh_hidden_unit(fixture: NaryClaimFixture) -> FreshUnitSelection:
    """Select one pre-registered unit absent from tracked TG-04 exposures."""

    if _CASE_ID in _PRIOR_EXPOSED_CASE_IDS:
        raise RuntimeError("fresh discovery case was previously exposed")
    case = next((case for case in fixture.cases if case.case_id == _CASE_ID), None)
    if case is None:
        raise RuntimeError("frozen fresh-discovery case is missing")
    units = enumerate_source_units(
        case_id=case.case_id,
        source_text=normalize_text_document(case.source_text),
    )
    if len(units) <= _UNIT_INDEX:
        raise RuntimeError("frozen fresh-discovery source unit is missing")
    unit = units[_UNIT_INDEX]
    if (
        unit.unit_id != _EXPECTED_UNIT_ID
        or unit.source_sha256 != _EXPECTED_SOURCE_SHA256
        or unit.input_sha256 != _EXPECTED_INPUT_SHA256
    ):
        raise RuntimeError("frozen fresh-discovery source-unit identity changed")
    if unit.unit_id in _PRIOR_EXPOSED_UNIT_IDS:
        raise RuntimeError("fresh discovery unit was previously exposed")
    local_events = tuple(
        event
        for event in case.events
        if unit.source_start <= event.trigger_source_start < unit.source_end
    )
    if local_events:
        raise RuntimeError("fresh-discovery unit unexpectedly contains local gold")
    return FreshUnitSelection(
        unit=unit,
        hidden_expert_event_count=len(local_events),
        exposure_registry_sha256=_exposure_registry_sha256(),
        authoritative_article_url=_ARTICLE_URL,
    )


def _exposure_registry_sha256() -> str:
    payload = {
        "scope": "tracked TG-04 live reports through merged PR #176",
        "prior_exposed_case_ids": sorted(_PRIOR_EXPOSED_CASE_IDS),
        "prior_exposed_unit_ids": sorted(_PRIOR_EXPOSED_UNIT_IDS),
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode(),
    ).hexdigest()


__all__ = ["FreshUnitSelection", "select_fresh_hidden_unit"]
