"""Zero-credit V9/V11 replay through the V12 two-lane contract."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from scripts.validation.public_gold.staged_event.generalization.grading.artifacts import (
    verify_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.grading.config import (
    DEFAULT_PATHS as GRADING_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    case_policy,
)
from scripts.validation.public_gold.staged_event.generalization.panel import (
    build_panel,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.contracts import (
    load_contract,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.evaluation import (
    evaluate_v12_case,
)


@dataclass(frozen=True, slots=True)
class OfflineReplayPaths:
    contract: Path
    adjudication: Path
    v9_raw: Path
    v9_result: Path
    v11_raw: Path
    v11_result: Path


def build_offline_replay(
    paths: OfflineReplayPaths,
) -> dict[str, object]:
    case = next(
        item
        for item in build_panel()
        if item.case_id == "generalization-drug-sensitivity"
    )
    contract = load_contract(
        paths.contract,
        adjudication_path=paths.adjudication,
    )
    policy = verify_frozen_policy(GRADING_PATHS.grading)
    frozen_case_policy = case_policy(policy, case.case_id)
    entries = []
    for version, raw_path, result_path, terminal in (
        (
            "V9",
            paths.v9_raw,
            paths.v9_result,
            "PIVOT_WITH_EVIDENCE",
        ),
        (
            "V11_RUN_2",
            paths.v11_raw,
            paths.v11_result,
            "V11_EXPOSED_RUN_V2_FAIL_UNRELATED_REGRESSION",
        ),
    ):
        output = V9StagedGeneralizationOutput.model_validate_json(
            raw_path.read_text(encoding="utf-8")
        )
        metrics = evaluate_v12_case(
            case,
            output,
            frozen_case_policy,
            contract,
        )
        entries.append(
            {
                "version": version,
                "sealed_terminal": terminal,
                "raw_output_sha256": _sha256(raw_path),
                "sealed_result_sha256": _sha256(result_path),
                "v12_diagnostic": metrics.as_json(),
                "retroactive_credit": False,
                "sealed_result_changed": False,
            }
        )
    return {
        "schema_version": (
            "artana.staged_generalization.v12_two_lane_offline_replay.v1"
        ),
        "case_id": case.case_id,
        "contract_sha256": _sha256(paths.contract),
        "adjudication_sha256": _sha256(paths.adjudication),
        "diagnostic_only": True,
        "historical_replay_credit": False,
        "entries": entries,
        "graph_writes": 0,
        "trusted_promotion": False,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = ["OfflineReplayPaths", "build_offline_replay"]
