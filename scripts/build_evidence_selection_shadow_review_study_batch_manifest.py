#!/usr/bin/env python3
"""Build a strict manifest for a completed shadow-review study batch."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
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
from artana_evidence_api.evidence_selection.shadow_review_study_batch_manifest import (  # noqa: E402
    EvidenceSelectionShadowReviewStudyBatchManifestBuildRequest,
    build_evidence_selection_shadow_review_study_batch_manifest,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Build an evidence_selection_shadow_review_study_batch.v1 manifest "
            "from completed human-labeled shadow-review packets."
        ),
    )
    parser.add_argument("--batch-id", required=True)
    parser.add_argument(
        "--machine-packet",
        type=Path,
        action="append",
        default=None,
        help="Original machine packet JSON; defaults to <packet>.machine.json.",
    )
    parser.add_argument(
        "--packet",
        type=Path,
        action="append",
        required=True,
        help="Human-completed packet JSON; provide one for each --machine-packet.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output path for the batch manifest JSON.",
    )
    parser.add_argument(
        "--adjudication-note",
        required=True,
        help="Human adjudication note applied to each batch entry.",
    )
    parser.add_argument("--source-system", required=True)
    parser.add_argument("--export-id-prefix", required=True)
    parser.add_argument("--exported-at", required=True)
    parser.add_argument("--exporter-id", required=True)
    parser.add_argument("--redaction-statement", required=True)
    parser.add_argument("--description", default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Write a batch manifest and return a process-style exit code."""

    args = parse_args(argv)
    packet_paths = tuple(args.packet)
    machine_packet_paths = (
        tuple(args.machine_packet) if args.machine_packet is not None else None
    )
    protected_packet_paths = (
        (*machine_packet_paths, *packet_paths)
        if machine_packet_paths is not None
        else (
            *(machine_packet_sidecar_path(packet_path) for packet_path in packet_paths),
            *packet_paths,
        )
    )
    try:
        _validate_output_path(
            output_path=args.output,
            packet_paths=protected_packet_paths,
        )
        manifest = build_evidence_selection_shadow_review_study_batch_manifest(
            EvidenceSelectionShadowReviewStudyBatchManifestBuildRequest(
                batch_id=args.batch_id,
                machine_packet_paths=machine_packet_paths,
                packet_paths=packet_paths,
                manifest_path=args.output,
                adjudication_note=args.adjudication_note,
                source_system=args.source_system,
                export_id_prefix=args.export_id_prefix,
                exported_at=args.exported_at,
                exporter_id=args.exporter_id,
                redaction_statement=args.redaction_statement,
                description=args.description,
            ),
        )
        _write_manifest(args.output, manifest.model_dump_json(indent=2))
    except (OSError, ValueError, ValidationError) as exc:
        print(f"error: {cli_error_message(exc)}", file=sys.stderr)
        return 1
    print(
        "evidence_selection_shadow_review_study_batch_manifest "
        f"batch_id={manifest.batch_id} "
        f"entries={len(manifest.entries)}",
    )
    print(f"Wrote batch manifest: {args.output}")
    return 0


def _validate_output_path(*, output_path: Path, packet_paths: tuple[Path, ...]) -> None:
    for packet_path in packet_paths:
        if paths_alias(output_path, packet_path):
            msg = "Batch manifest output must not overwrite source packet."
            raise ValueError(msg)
    if output_path.exists() and output_path.is_dir():
        msg = f"Batch manifest output must be a file path, not a directory: {output_path}"
        raise ValueError(msg)
    output_parent = output_path.parent
    if output_parent.exists() and not output_parent.is_dir():
        msg = f"Batch manifest output parent must be a directory: {output_parent}"
        raise ValueError(msg)


def _write_manifest(output_path: Path, manifest_json: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f".{output_path.name}.tmp-{uuid4().hex}")
    try:
        temp_path.write_text(manifest_json + "\n", encoding="utf-8")
        temp_path.replace(output_path)
    except OSError:
        if temp_path.exists():
            temp_path.unlink()
        raise


if __name__ == "__main__":
    raise SystemExit(main())
