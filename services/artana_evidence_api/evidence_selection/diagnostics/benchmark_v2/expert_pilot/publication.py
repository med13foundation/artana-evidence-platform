"""Atomic no-replace publication for expert-pilot workflow stages."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.pilot_publication import (
    publish_directory_no_replace,
)


def publish_expert_pilot_stage(
    *,
    output_dir: Path,
    content_by_name: dict[str, str],
) -> None:
    """Publish a complete workflow stage without partial or replaced output."""

    resolved_output = output_dir.resolve()
    if resolved_output.exists():
        raise ValueError("expert-pilot stage output directory must not already exist")
    if not content_by_name or any(
        Path(name).name != name or name in {".", ".."} for name in content_by_name
    ):
        raise ValueError("expert-pilot stage artifact names must be flat and nonempty")
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{resolved_output.name}.staging-",
            dir=resolved_output.parent,
        )
    )
    try:
        for name, content in content_by_name.items():
            path = staging / name
            path.write_text(content, encoding="utf-8")
            path.chmod(0o600)
        publish_directory_no_replace(staging=staging, destination=resolved_output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = ["publish_expert_pilot_stage"]
