#!/usr/bin/env python3
"""Build an incomplete evidence-selection packet for human shadow review."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import ValidationError

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

from artana_evidence_api.evidence_selection.cli_errors import (
    cli_error_message,  # noqa: E402
)
from artana_evidence_api.evidence_selection.output_paths import (
    paths_alias,  # noqa: E402
)
from artana_evidence_api.evidence_selection.shadow_review_completion import (  # noqa: E402
    machine_packet_sidecar_path,
)
from artana_evidence_api.evidence_selection.shadow_review_packet import (  # noqa: E402
    EvidenceSelectionShadowReviewPacketRequest,
    EvidenceSelectionShadowReviewRankingItem,
    build_evidence_selection_shadow_review_packet,
)
from artana_evidence_api.types.common import (  # noqa: E402
    JSONObject,
    JSONValue,
    json_array,
    json_object,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Build an editable human-label packet plus a separate signed "
            "machine-packet sidecar from an evidence-selection result artifact."
        ),
    )
    parser.add_argument(
        "--run-result",
        type=Path,
        required=True,
        help="Evidence-selection result JSON artifact.",
    )
    parser.add_argument("--study-id", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output path for the editable shadow-review packet JSON.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Build a packet and return a process-style exit code."""

    args = parse_args(argv)
    try:
        packet = build_evidence_selection_shadow_review_packet(
            _request_from_result_payload(
                payload=_load_json_object(args.run_result),
                study_id=args.study_id,
            ),
        )
        machine_path = machine_packet_sidecar_path(args.output)
        _write_packet_pair(
            run_result_path=args.run_result,
            completed_packet_path=args.output,
            machine_packet_path=machine_path,
            payload=packet.model_dump_json(indent=2),
        )
    except (OSError, ValueError, ValidationError) as exc:
        print(f"error: {cli_error_message(exc)}", file=sys.stderr)
        return 1
    print(
        "evidence_selection_shadow_review_packet "
        f"selection_forms={len(packet.selection_review_forms)} "
        f"candidate_records={len(packet.candidate_records)} "
        f"review_ranking_forms={len(packet.review_ranking_forms)}",
    )
    print(f"Wrote editable shadow-review packet: {args.output}")
    print(f"Wrote signed machine packet: {machine_path}")
    return 0


def _request_from_result_payload(
    *,
    payload: JSONObject,
    study_id: str,
) -> EvidenceSelectionShadowReviewPacketRequest:
    goal = _required_payload_string(payload, "goal")
    return EvidenceSelectionShadowReviewPacketRequest(
        study_id=study_id,
        run_id=_run_id_from_result_payload(payload),
        goal=goal,
        selected_records=_json_object_tuple(payload.get("selected_records")),
        skipped_records=_json_object_tuple(payload.get("skipped_records")),
        deferred_records=_json_object_tuple(payload.get("deferred_records")),
        review_ranking_items=_review_ranking_items_from_result(
            payload=payload,
            goal=goal,
        ),
    )


def _run_id_from_result_payload(payload: JSONObject) -> str:
    run_payload = json_object(payload.get("run"))
    if run_payload is not None:
        run_id = run_payload.get("id")
        if isinstance(run_id, str) and run_id.strip() != "":
            return run_id.strip()
    raw_run_id = payload.get("run_id")
    if isinstance(raw_run_id, str) and raw_run_id.strip() != "":
        return raw_run_id.strip()
    msg = "Evidence-selection result must include run.id or run_id."
    raise ValueError(msg)


def _required_payload_string(payload: JSONObject, key: str) -> str:
    value = payload.get(key)
    if isinstance(value, str) and value.strip() != "":
        return value.strip()
    msg = f"Evidence-selection result is missing string field '{key}'."
    raise ValueError(msg)


def _json_object_tuple(value: JSONValue | None) -> tuple[JSONObject, ...]:
    raw_array = json_array(value)
    if raw_array is None:
        return ()
    records: list[JSONObject] = []
    for index, raw_item in enumerate(raw_array):
        item = json_object(raw_item)
        if item is None:
            msg = f"Expected JSON object at records[{index}]."
            raise ValueError(msg)
        records.append(item)
    return tuple(records)


def _review_ranking_items_from_result(
    *,
    payload: JSONObject,
    goal: str,
) -> tuple[EvidenceSelectionShadowReviewRankingItem, ...]:
    direct_items = _direct_review_ranking_items(payload.get("review_ranking_items"))
    proposal_items = _ranking_items_from_artifact_records(
        payload.get("proposals"),
        source_kind="proposal",
        id_field="proposal_id",
        shape_field="proposal_type",
        goal=goal,
    )
    review_item_items = _ranking_items_from_artifact_records(
        payload.get("review_items"),
        source_kind="review_item",
        id_field="review_item_id",
        shape_field="review_type",
        goal=goal,
    )
    return (*direct_items, *proposal_items, *review_item_items)


def _direct_review_ranking_items(
    value: JSONValue | None,
) -> tuple[EvidenceSelectionShadowReviewRankingItem, ...]:
    raw_array = json_array(value)
    if raw_array is None:
        return ()
    items: list[EvidenceSelectionShadowReviewRankingItem] = []
    for index, raw_item in enumerate(raw_array):
        item = json_object(raw_item)
        if item is None:
            msg = f"Expected JSON object at review_ranking_items[{index}]."
            raise ValueError(msg)
        items.append(EvidenceSelectionShadowReviewRankingItem.model_validate(item))
    return tuple(items)


def _ranking_items_from_artifact_records(
    value: JSONValue | None,
    *,
    source_kind: Literal["proposal", "review_item"],
    id_field: str,
    shape_field: str,
    goal: str,
) -> tuple[EvidenceSelectionShadowReviewRankingItem, ...]:
    raw_array = json_array(value)
    if raw_array is None:
        return ()
    items: list[EvidenceSelectionShadowReviewRankingItem] = []
    for index, raw_item in enumerate(raw_array):
        item = json_object(raw_item)
        if item is None:
            msg = f"Expected JSON object at {source_kind}s[{index}]."
            raise ValueError(msg)
        items.append(
            EvidenceSelectionShadowReviewRankingItem(
                source_kind=source_kind,
                item_id=_required_artifact_string(item, id_field),
                ranking_score=_calibration_score(
                    _required_artifact_number(item, "ranking_score"),
                ),
                goal=goal,
                evidence_shape=_optional_artifact_string(item, shape_field),
            ),
        )
    return tuple(items)


def _required_artifact_string(payload: JSONObject, key: str) -> str:
    value = payload.get(key)
    if isinstance(value, str) and value.strip() != "":
        return value.strip()
    msg = f"Review-ranking artifact record is missing string field '{key}'."
    raise ValueError(msg)


def _optional_artifact_string(payload: JSONObject, key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value.strip() != "":
        return value.strip()
    return None


def _required_artifact_number(payload: JSONObject, key: str) -> float:
    value = payload.get(key)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    msg = f"Review-ranking artifact record is missing numeric field '{key}'."
    raise ValueError(msg)


def _calibration_score(value: float) -> float:
    if value > 1.0:
        value = value / 10.0
    return round(max(0.0, min(value, 1.0)), 6)


def _load_json_object(path: Path) -> JSONObject:
    source_text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(source_text)
    except json.JSONDecodeError as exc:
        msg = f"{path} is not valid JSON: {exc.msg}."
        raise ValueError(msg) from exc
    result = json_object(payload)
    if result is None:
        msg = f"{path} does not contain a JSON object."
        raise ValueError(msg)
    return result


def _write_packet_pair(
    *,
    run_result_path: Path,
    completed_packet_path: Path,
    machine_packet_path: Path,
    payload: str,
) -> None:
    _validate_packet_output_paths(
        run_result_path=run_result_path,
        completed_packet_path=completed_packet_path,
        machine_packet_path=machine_packet_path,
    )
    completed_temp_path: Path | None = None
    machine_temp_path: Path | None = None
    published_paths: list[Path] = []
    try:
        completed_temp_path = _write_temp_packet(completed_packet_path, payload)
        machine_temp_path = _write_temp_packet(machine_packet_path, payload)
        machine_temp_path.replace(machine_packet_path)
        machine_temp_path = None
        published_paths.append(machine_packet_path)
        completed_temp_path.replace(completed_packet_path)
        completed_temp_path = None
        published_paths.append(completed_packet_path)
    except OSError:
        for path in published_paths:
            with suppress(OSError):
                path.unlink()
        raise
    finally:
        for temp_path in (completed_temp_path, machine_temp_path):
            if temp_path is not None:
                with suppress(OSError):
                    temp_path.unlink(missing_ok=True)


def _validate_packet_output_paths(
    *,
    run_result_path: Path,
    completed_packet_path: Path,
    machine_packet_path: Path,
) -> None:
    if paths_alias(completed_packet_path, machine_packet_path):
        msg = "Editable and machine packet outputs must be different files."
        raise ValueError(msg)
    for output_path in (completed_packet_path, machine_packet_path):
        if paths_alias(output_path, run_result_path):
            msg = "Shadow-review packet output must not overwrite the run result."
            raise ValueError(msg)
        if output_path.exists():
            msg = f"Shadow-review packet output already exists: {output_path}"
            raise ValueError(msg)
        if output_path.parent.exists() and not output_path.parent.is_dir():
            msg = f"Shadow-review packet output parent is not a directory: {output_path.parent}"
            raise ValueError(msg)


def _write_temp_packet(output_path: Path, payload: str) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f".{output_path.name}.tmp-{uuid4().hex}")
    temp_path.write_text(payload + "\n", encoding="utf-8")
    return temp_path


if __name__ == "__main__":
    raise SystemExit(main())
