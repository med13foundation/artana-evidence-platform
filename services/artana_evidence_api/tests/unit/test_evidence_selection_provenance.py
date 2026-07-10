"""Tests for evidence-selection source-manifest policy behavior."""

from __future__ import annotations

from artana_evidence_api.evidence_selection.provenance import (
    source_manifest_blocking_reasons,
)


def test_optional_missing_source_manifest_skips_manifest_only_checks() -> None:
    reasons = source_manifest_blocking_reasons(
        provenance_summary={"source_manifest_present": False},
        require_source_manifest=False,
        min_source_artifact_count=2,
    )

    assert reasons == ()
