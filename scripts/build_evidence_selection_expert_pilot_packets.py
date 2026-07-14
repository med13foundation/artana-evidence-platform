#!/usr/bin/env python3
"""Build blinded semantic benchmark packets for independent expert review."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

from artana_evidence_api.evidence_selection.cli_errors import (  # noqa: E402
    cli_error_message,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2 import (  # noqa: E402
    load_expert_pilot,
    publish_expert_pilot_packets,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Publish blinded reviewer packets and separately signed machine "
            "sidecars for the semantic benchmark expert pilot."
        )
    )
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Build an atomic packet publication and return a process-style status."""

    args = parse_args(argv)
    try:
        loaded = load_expert_pilot(
            protocol_path=args.protocol,
            repository_root=Path.cwd(),
        )
        manifest = publish_expert_pilot_packets(
            loaded=loaded,
            output_dir=args.output_dir,
        )
    except (OSError, ValueError, ValidationError) as exc:
        print(f"error: {cli_error_message(exc)}", file=sys.stderr)
        return 1
    print(
        "evidence_selection_expert_pilot "
        f"reviewers={manifest.independent_reviewer_count} "
        f"packets={manifest.reviewer_packet_count} "
        f"candidate_reviews={manifest.candidate_review_count} "
        "production_readiness=false production_calibration=false"
    )
    print(f"Wrote expert-pilot packet publication: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
