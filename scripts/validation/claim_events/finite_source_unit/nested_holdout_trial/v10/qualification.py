"""Deterministic replay contract for the V10 scientific gate."""

from __future__ import annotations

import hashlib
import json
from typing import Final

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitEligibilityCategory,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v9.qualification import (
    QualificationReplayContract,
    require_replayed_nested_qualification,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v10.prompts import (
    V10_PROMPT_POLICY,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v10.selection import (
    tenth_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    FrozenSourceUnit,
)

TENTH_ARCHIVE_SHA256: Final = (
    "f70e5f6d6e2a7f7fcdb5c8671715f3909a77662a6238015b2916ce939f2a890f"
)
TENTH_EXPERT_GRAPH_SHA256: Final = (
    "ddd564c4fc7a431358df7f193c4b0284ff5dcebc87a4fd6ce6f61d6b29f28cc5"
)
TENTH_PROJECTION_SET_SHA256: Final = (
    "4f6add86982fe4eabb9df893ee71af9b8cce60aa1b280d18edff9598004821cd"
)
TENTH_SOURCE_IDENTITY: Final[tuple[tuple[str, object], ...]] = (
    ("case_id", "bionlp-ge-2011-holdout:PMC-2222968-04-Results-03"),
    (
        "unit_id",
        "source-unit-463bf8e1b37963d7547eb57c6d51545a466050b2c6c9faa9abc76ff8e2330914",
    ),
    ("unit_index", 17),
    ("source_start", 2622),
    ("source_end", 2723),
    (
        "source_sha256",
        "d452cea84a786851d0d5686c5acab618745b4b8ccaf09cc6fa638a48b370a17a",
    ),
    (
        "input_sha256",
        "cc50c7039a85ec0c7512d0f8f9571331f4001a61e88284a040ec701ec619a121",
    ),
)
TENTH_PROMPT_DIGESTS: Final[tuple[tuple[str, str], ...]] = (
    (
        "extraction_prompt_sha256",
        "13f5cb79aaa72d97b11628ed48847a562ca553a010131b47021d87ce8ccac4e7",
    ),
    (
        "verification_prompt_probe_sha256",
        "bbd7aeb9e7365e2744ca843ca4425f4b57d79698b3362f7c8ce146c3ccdc7c0d",
    ),
)


def require_replayed_tenth_qualification(report: dict[str, object]) -> None:
    """Rebuild V10 from receipt-bound outputs and its frozen scientific gold."""

    _require_tenth_frozen_lineage(report)
    require_replayed_nested_qualification(
        report,
        contract=QualificationReplayContract(
            ordinal="tenth",
            unit_identity=dict(TENTH_SOURCE_IDENTITY),
            expected_eligibility_category=SourceUnitEligibilityCategory.NULL_RESULT,
            projection_set=tenth_projection_set(),
            prompt_policy=V10_PROMPT_POLICY,
        ),
    )


def _require_tenth_frozen_lineage(report: dict[str, object]) -> None:
    projection_set = tenth_projection_set()
    if (
        _sha256_json(projection_set.canonical_projection.graph.as_json())
        != TENTH_EXPERT_GRAPH_SHA256
        or _sha256_json(projection_set.as_json()) != TENTH_PROJECTION_SET_SHA256
    ):
        raise RuntimeError("tenth holdout scientific contract identity changed")
    source_corpus = _required_dict(report, "source_corpus")
    if (
        source_corpus.get("archive_sha256") != TENTH_ARCHIVE_SHA256
        or source_corpus.get("expert_graph_sha256") != TENTH_EXPERT_GRAPH_SHA256
        or source_corpus.get("projection_set_sha256") != TENTH_PROJECTION_SET_SHA256
    ):
        raise RuntimeError("tenth holdout source corpus identity changed")
    unit = _required_dict(report, "unit")
    if any(unit.get(key) != expected for key, expected in TENTH_SOURCE_IDENTITY):
        raise RuntimeError("tenth holdout source identity changed")
    frozen_unit = FrozenSourceUnit(
        unit_id=_required_string(unit, "unit_id"),
        index=_required_int(unit, "unit_index"),
        source_start=_required_int(unit, "source_start"),
        source_end=_required_int(unit, "source_end"),
        text=_required_string(unit, "text"),
        source_sha256=_required_string(unit, "source_sha256"),
    )
    if frozen_unit.input_sha256 != dict(TENTH_SOURCE_IDENTITY)["input_sha256"]:
        raise RuntimeError("tenth holdout source text identity changed")
    actual_prompt_digests = {
        "extraction_prompt_sha256": _sha256_text(
            V10_PROMPT_POLICY.extraction_prompt(frozen_unit),
        ),
        "verification_prompt_probe_sha256": _sha256_text(
            V10_PROMPT_POLICY.verification_prompt(unit=frozen_unit, candidates=()),
        ),
    }
    if actual_prompt_digests != dict(TENTH_PROMPT_DIGESTS):
        raise RuntimeError("tenth holdout prompt policy identity changed")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
    ).hexdigest()


def _required_dict(value: dict[str, object], key: str) -> dict[str, object]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise TypeError(f"tenth holdout {key} must be an object")
    return item


def _required_string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise TypeError(f"tenth holdout {key} must be text")
    return item


def _required_int(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise TypeError(f"tenth holdout {key} must be an integer")
    return item


__all__ = [
    "TENTH_ARCHIVE_SHA256",
    "TENTH_EXPERT_GRAPH_SHA256",
    "TENTH_PROMPT_DIGESTS",
    "TENTH_PROJECTION_SET_SHA256",
    "TENTH_SOURCE_IDENTITY",
    "require_replayed_tenth_qualification",
]
