"""Tests for canonical evidence-selection source export timestamps."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from artana_evidence_api.evidence_selection.source_exports import (
    EvidenceSelectionSourceExportIdentity,
)


def test_source_export_identity_rejects_fractional_second_datetime() -> None:
    with pytest.raises(ValueError, match="canonical UTC format"):
        EvidenceSelectionSourceExportIdentity(
            source_system="artana-shadow-review",
            export_id="shadow-export-2026-07-10",
            exported_at=datetime(2026, 7, 10, 12, 0, 0, 1, tzinfo=UTC),
            exporter_id="review-ops-a",
            redaction_statement="No PHI or raw patient text included.",
        )
