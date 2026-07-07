#!/usr/bin/env python3
"""Build source-export inputs from a completed shadow-review packet."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

from artana_evidence_api.evidence_selection.shadow_review_completion import (  # noqa: E402
    EvidenceSelectionShadowReviewSourceInputRequest,
    build_evidence_selection_shadow_review_source_inputs,
)
from artana_evidence_api.types.common import JSONObject, json_object  # noqa: E402


@dataclass(frozen=True, slots=True)
class _PreparedOutput:
    """Rollback information for one output path."""

    final_path: Path
    backup_path: Path | None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Convert a completed evidence-selection shadow-review packet into "
            "selection-review labels and review-ranking study inputs."
        ),
    )
    parser.add_argument(
        "--packet",
        type=Path,
        required=True,
        help="Completed evidence_selection_shadow_review_packet.v1 JSON file.",
    )
    parser.add_argument(
        "--selection-reviews-output",
        type=Path,
        required=True,
        help="Output JSON path for the selection_reviews source input.",
    )
    parser.add_argument(
        "--review-ranking-output",
        type=Path,
        required=True,
        help="Output JSON path for the review-ranking calibration source input.",
    )
    parser.add_argument(
        "--adjudication-note",
        required=True,
        help="Human adjudication note for the completed review-ranking study.",
    )
    parser.add_argument("--description", default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Write source-input files and return a process-style exit code."""

    args = parse_args(argv)
    try:
        _validate_output_paths(
            packet_path=args.packet,
            selection_output_path=args.selection_reviews_output,
            review_ranking_output_path=args.review_ranking_output,
        )
        result = build_evidence_selection_shadow_review_source_inputs(
            EvidenceSelectionShadowReviewSourceInputRequest(
                packet=_load_json_object(args.packet),
                adjudication_note=args.adjudication_note,
                description=args.description,
            ),
        )
        _write_paired_json(
            selection_output_path=args.selection_reviews_output,
            selection_payload=result.selection_reviews_payload(),
            review_ranking_output_path=args.review_ranking_output,
            review_ranking_payload=result.review_ranking_payload(),
        )
    except (OSError, ValueError, ValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        "evidence_selection_shadow_review_source_inputs "
        f"selection_reviews={len(result.selection_reviews)} "
        f"review_ranking_decisions={len(result.review_ranking.decisions)}",
    )
    print(f"Wrote selection-review labels: {args.selection_reviews_output}")
    print(f"Wrote review-ranking study: {args.review_ranking_output}")
    return 0


def _validate_output_paths(
    *,
    packet_path: Path,
    selection_output_path: Path,
    review_ranking_output_path: Path,
) -> None:
    resolved_packet = packet_path.resolve(strict=False)
    resolved_selection = selection_output_path.resolve(strict=False)
    resolved_ranking = review_ranking_output_path.resolve(strict=False)
    if resolved_selection == resolved_ranking:
        msg = "Selection-review and review-ranking outputs must be different files."
        raise ValueError(msg)
    if resolved_selection == resolved_packet:
        msg = "Selection-review output must not overwrite source packet."
        raise ValueError(msg)
    if resolved_ranking == resolved_packet:
        msg = "Review-ranking output must not overwrite source packet."
        raise ValueError(msg)
    _validate_output_file_path(
        output_path=selection_output_path,
        label="Selection-review output",
    )
    _validate_output_file_path(
        output_path=review_ranking_output_path,
        label="Review-ranking output",
    )


def _validate_output_file_path(*, output_path: Path, label: str) -> None:
    if output_path.exists() and output_path.is_dir():
        msg = f"{label} must be a file path, not a directory."
        raise ValueError(msg)
    output_parent = output_path.parent
    if output_parent.exists() and not output_parent.is_dir():
        msg = f"{label} parent must be a directory."
        raise ValueError(msg)


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


def _write_paired_json(
    *,
    selection_output_path: Path,
    selection_payload: JSONObject,
    review_ranking_output_path: Path,
    review_ranking_payload: JSONObject,
) -> None:
    _validate_output_file_path(
        output_path=selection_output_path,
        label="Selection-review output",
    )
    _validate_output_file_path(
        output_path=review_ranking_output_path,
        label="Review-ranking output",
    )
    selection_temp_path: Path | None = None
    review_ranking_temp_path: Path | None = None
    prepared_outputs: list[_PreparedOutput] = []
    try:
        selection_temp_path = _write_temp_sibling(
            final_path=selection_output_path,
            payload=selection_payload,
        )
        review_ranking_temp_path = _write_temp_sibling(
            final_path=review_ranking_output_path,
            payload=review_ranking_payload,
        )
        prepared_outputs.append(_prepare_output_for_replace(selection_output_path))
        prepared_outputs.append(_prepare_output_for_replace(review_ranking_output_path))
        selection_temp_path.replace(selection_output_path)
        selection_temp_path = None
        review_ranking_temp_path.replace(review_ranking_output_path)
        review_ranking_temp_path = None
        _discard_prepared_backups(prepared_outputs)
    except OSError as exc:
        _cleanup_temp_path(selection_temp_path)
        _cleanup_temp_path(review_ranking_temp_path)
        _restore_prepared_outputs(prepared_outputs)
        msg = f"Unable to write paired shadow-review source inputs: {exc}"
        raise OSError(msg) from exc


def _write_temp_sibling(*, final_path: Path, payload: JSONObject) -> Path:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = final_path.with_name(f".{final_path.name}.tmp-{uuid4().hex}")
    temp_path.write_text(_json_text(payload), encoding="utf-8")
    return temp_path


def _prepare_output_for_replace(final_path: Path) -> _PreparedOutput:
    if not final_path.exists():
        return _PreparedOutput(final_path=final_path, backup_path=None)
    backup_path = final_path.with_name(f".{final_path.name}.bak-{uuid4().hex}")
    final_path.replace(backup_path)
    return _PreparedOutput(final_path=final_path, backup_path=backup_path)


def _restore_prepared_outputs(prepared_outputs: list[_PreparedOutput]) -> None:
    for prepared_output in reversed(prepared_outputs):
        if prepared_output.backup_path is None:
            _cleanup_temp_path(prepared_output.final_path)
            continue
        if prepared_output.final_path.exists():
            _cleanup_temp_path(prepared_output.final_path)
        prepared_output.backup_path.replace(prepared_output.final_path)


def _discard_prepared_backups(prepared_outputs: list[_PreparedOutput]) -> None:
    for prepared_output in prepared_outputs:
        if prepared_output.backup_path is not None:
            _cleanup_temp_path(prepared_output.backup_path)
    prepared_outputs.clear()


def _cleanup_temp_path(path: Path | None) -> None:
    if path is None:
        return
    with suppress(OSError):
        path.unlink(missing_ok=True)


def _json_text(payload: JSONObject) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
