"""
License validation utilities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

from .manager import LicenseCompatibility, LicenseManager

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from src.type_definitions.common import JSONObject
    from src.type_definitions.packaging import LicenseSourceEntry


class LicenseValidator:
    """Validate license compliance for packages."""

    def __init__(self, package_license: str = "CC-BY-4.0") -> None:
        """
        Initialize validator.

        Args:
            package_license: Package license identifier
        """
        self.package_license = package_license

    def validate_sources(
        self,
        source_licenses: Sequence[LicenseSourceEntry],
    ) -> JSONObject:
        """
        Validate source licenses against package license.

        Args:
            source_licenses: List of source license dictionaries

        Returns:
            Validation result dictionary
        """
        issues: list[str] = []
        warnings: list[str] = []

        for source_info in source_licenses:
            source_license_value = source_info.get("license") or "unknown"
            source_name_value = source_info.get("source") or "unknown"
            source_license = str(source_license_value)
            source_name = str(source_name_value)

            compatibility = LicenseManager.check_compatibility(
                source_license,
                self.package_license,
            )

            if compatibility == LicenseCompatibility.MISSING:
                warnings.append(f"Missing license for source: {source_name}")
            elif compatibility == LicenseCompatibility.INCOMPATIBLE:
                issues.append(
                    f"Incompatible license '{source_license}' "
                    f"from source '{source_name}'",
                )

        return self._format_result(
            is_valid=len(issues) == 0,
            issues=issues,
            warnings=warnings,
        )

    def validate_manifest(self, manifest_path: Path) -> JSONObject:
        """
        Validate license manifest file.

        Args:
            manifest_path: Path to license manifest file

        Returns:
            Validation result dictionary
        """
        if not manifest_path.exists():
            return self._format_result(
                is_valid=False,
                issues=["License manifest file not found"],
            )

        try:
            with manifest_path.open(encoding="utf-8") as f:
                manifest_raw = yaml.safe_load(f)

            if not isinstance(manifest_raw, dict):
                return self._format_result(
                    is_valid=False,
                    issues=["Manifest must be a mapping"],
                )

            issues: list[str] = []

            package_license_value = manifest_raw.get("package_license")
            if not isinstance(package_license_value, str):
                issues.append("Missing package_license in manifest")

            sources_value = manifest_raw.get("sources")
            sources: list[LicenseSourceEntry] | None = None
            if not isinstance(sources_value, list):
                issues.append("Missing sources in manifest")
            elif not all(isinstance(source, dict) for source in sources_value):
                issues.append("All sources must be JSON objects")
            else:
                sources = list(sources_value)

            if issues:
                return self._format_result(is_valid=False, issues=issues)

            if sources is None:
                return self._format_result(
                    is_valid=False,
                    issues=["Sources could not be parsed"],
                )

            return self.validate_sources(sources)

        except (OSError, ValueError, yaml.YAMLError) as exc:
            return self._format_result(
                is_valid=False,
                issues=[f"Error reading manifest: {exc}"],
            )

    @staticmethod
    def _format_result(
        *,
        is_valid: bool,
        issues: list[str],
        warnings: list[str] | None = None,
    ) -> JSONObject:
        """Create a standardized validation result."""
        return {
            "valid": is_valid,
            "issues": issues,
            "warnings": warnings or [],
        }
