"""Run the non-qualifying dependency-closed V2 diagnostic projection."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from scripts.validation.public_gold.bionlp_cg_event_projection import (
    project_development_directory,
)
from scripts.validation.public_gold.lossless_event_scoring import (
    score_scientific_event_document,
)
from scripts.validation.public_gold.staged_event.assembly import (
    AssemblyInputs,
    ResolvedCandidate,
    assemble_staged_document,
    resolve_discovery_candidates,
)
from scripts.validation.public_gold.staged_event.contracts import (
    EventDiscoveryOutput,
    ModifierOutput,
    ParticipantInventoryOutput,
    RoleAssignmentOutput,
    VerificationOutput,
)
from scripts.validation.public_gold.staged_event.diagnostic_projection import (
    DiagnosticProjection,
    DiagnosticProjectionError,
    project_dependency_closed_subgraph,
)

GOLD_EVENT_DENOMINATOR = 30
EXPECTED_TERMINAL_DECISION = "INVALID_EXPERIMENT"
EXPECTED_DOCUMENT_ID = "PMID-16428936"
_StageModelT = TypeVar("_StageModelT", bound=BaseModel)


def run_offline_projection(
    *,
    result_path: Path,
    receipt_path: Path,
    source_path: Path,
    development_directory: Path,
) -> dict[str, object]:
    """Validate custody, quarantine dependencies, and score the retained graph."""

    result = _load_object(result_path)
    receipt = _load_object(receipt_path)
    if result.get("decision") != EXPECTED_TERMINAL_DECISION:
        raise DiagnosticProjectionError("V2 terminal decision changed")
    if result.get("accounting") != receipt:
        raise DiagnosticProjectionError("V2 result and receipt accounting differ")
    receipts = _object_list(receipt, "receipts")
    if any(item.get("status") != "VERIFIED_LIVE" for item in receipts):
        raise DiagnosticProjectionError("V2 contains an unverified provider receipt")

    source_text = source_path.read_text(encoding="utf-8")
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    stage_outputs = _object(result, "stage_outputs")
    discovery = _stage_model(EventDiscoveryOutput, stage_outputs, "discovery")
    participants = _stage_model(
        ParticipantInventoryOutput, stage_outputs, "participants"
    )
    roles = _stage_model(RoleAssignmentOutput, stage_outputs, "roles")
    modifiers = _stage_model(ModifierOutput, stage_outputs, "modifiers")
    verifications = _stage_model(VerificationOutput, stage_outputs, "verification")
    candidates = resolve_discovery_candidates(
        discovery.candidates,
        source_text=source_text,
        source_sha256=source_sha256,
    ).candidates
    projection = project_dependency_closed_subgraph(
        candidates=candidates,
        participants=participants,
        roles=roles,
        modifiers=modifiers,
        verifications=verifications,
    )
    retained = set(projection.retained_event_ids)
    assembly = assemble_staged_document(
        AssemblyInputs(
            candidates=_filter_candidates(candidates, retained),
            participant_output=ParticipantInventoryOutput(
                inventories=tuple(
                    item for item in participants.inventories if item.event_id in retained
                )
            ),
            role_output=RoleAssignmentOutput(
                events=tuple(item for item in roles.events if item.event_id in retained)
            ),
            modifier_output=ModifierOutput(
                events=tuple(
                    item for item in modifiers.events if item.event_id in retained
                )
            ),
            verification_output=VerificationOutput(
                events=tuple(
                    item for item in verifications.events if item.event_id in retained
                ),
                missing_supported_events=verifications.missing_supported_events,
            ),
            document_id=EXPECTED_DOCUMENT_ID,
            source_text=source_text,
            source_sha256=source_sha256,
            producer_identity="offline-diagnostic-projection-v1",
        )
    )
    gold = next(
        document
        for document in project_development_directory(development_directory)
        if document.document_id == EXPECTED_DOCUMENT_ID
    )
    score = score_scientific_event_document(gold=gold, predicted=assembly.document)
    if score.complete_events.gold != GOLD_EVENT_DENOMINATOR:
        raise DiagnosticProjectionError("public-gold denominator changed")
    return {
        "schema_version": "artana.public_gold.staged_event_offline_diagnostic.v1",
        "status": "OFFLINE_PROJECTION_VALID",
        "qualification_status": "NON_QUALIFYING_DIAGNOSTIC_REVIEW_ONLY",
        "v2_terminal_decision": EXPECTED_TERMINAL_DECISION,
        "custody": {
            "result_sha256": _sha256(result_path),
            "receipt_sha256": _sha256(receipt_path),
            "source_sha256": source_sha256,
            "verified_receipts": len(receipts),
        },
        "projection": _projection_json(projection),
        "score": score.as_json(),
        "trusted_promotion": False,
    }


def _projection_json(projection: DiagnosticProjection) -> dict[str, object]:
    return {
        "candidate_count": (
            len(projection.retained_event_ids) + len(projection.quarantined_events)
        ),
        "retained_closed_subgraph_size": len(projection.retained_event_ids),
        "retained_event_ids": list(projection.retained_event_ids),
        "direct_exclusion_count": projection.direct_exclusion_count,
        "dependency_exclusion_count": projection.dependency_exclusion_count,
        "quarantined_events": [
            {
                **asdict(item),
                "dependency_path": list(item.dependency_path),
                "terminal_state": "REVIEW_ONLY",
            }
            for item in projection.quarantined_events
        ],
    }


def _filter_candidates(
    candidates: tuple[ResolvedCandidate, ...], retained: set[str]
) -> tuple[ResolvedCandidate, ...]:
    return tuple(item for item in candidates if item.event_id in retained)


def _load_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DiagnosticProjectionError(f"{path} must contain an object")
    return value


def _object(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise DiagnosticProjectionError(f"{key} must be an object")
    return value


def _object_list(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise DiagnosticProjectionError(f"{key} must be a list of objects")
    return value


def _stage_model(
    model: type[_StageModelT], payload: dict[str, object], key: str
) -> _StageModelT:
    return model.model_validate_json(json.dumps(_object(payload, key)))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--development-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = run_offline_projection(
        result_path=args.result,
        receipt_path=args.receipt,
        source_path=args.source,
        development_directory=args.development_directory,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(output["projection"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["GOLD_EVENT_DENOMINATOR", "run_offline_projection"]
