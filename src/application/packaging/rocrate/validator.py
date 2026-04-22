"""Typed RO-Crate validator with a minimal feature-set for the tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SectionReport:
    valid: bool
    errors: list[str]

    def to_dict(self) -> dict[str, object]:
        return {"valid": self.valid, "errors": list(self.errors)}


class ROCrateValidator:
    def __init__(self, crate_path: Path) -> None:
        self.crate_path = Path(crate_path)

    def _structure_report(self) -> SectionReport:
        errors: list[str] = []
        if not self.crate_path.exists():
            errors.append("Crate path does not exist")
        if not (self.crate_path / "ro-crate-metadata.json").exists():
            errors.append("Missing ro-crate-metadata.json")
        if not (self.crate_path / "data").exists():
            errors.append("Missing data directory")
        return SectionReport(valid=not errors, errors=errors)

    def validate_structure(self) -> dict[str, object]:
        return self._structure_report().to_dict()

    def _metadata_report(self) -> SectionReport:
        metadata_path = self.crate_path / "ro-crate-metadata.json"
        if not metadata_path.exists():
            return SectionReport(valid=False, errors=["Missing ro-crate-metadata.json"])

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return SectionReport(valid=False, errors=[f"Invalid metadata: {exc}"])

        missing_fields = [
            field for field in ("@context", "@graph") if field not in metadata
        ]

        return SectionReport(valid=not missing_fields, errors=missing_fields)

    def validate_metadata(self) -> dict[str, object]:
        return self._metadata_report().to_dict()

    def validate_fair_compliance(self) -> dict[str, dict[str, object]]:
        structure_report = self._structure_report()
        metadata_report = self._metadata_report()

        compliance = {
            "findable": structure_report,
            "accessible": metadata_report,
            "interoperable": metadata_report,
            "reusable": metadata_report,
        }

        return {name: report.to_dict() for name, report in compliance.items()}

    def validate(self) -> dict[str, object]:
        structure = self._structure_report().to_dict()
        metadata = self._metadata_report().to_dict()
        fair = self.validate_fair_compliance()

        return {
            "valid": structure["valid"] and metadata["valid"],
            "structure": structure,
            "metadata": metadata,
            "fair_compliance": fair,
        }


__all__ = ["ROCrateValidator"]
