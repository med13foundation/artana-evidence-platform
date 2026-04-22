"""
License manifest generation utilities.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from src.type_definitions.packaging import (
        LicenseInfo,
        LicenseManifest,
        LicenseRecord,
    )

from .manager import LicenseCompatibility, LicenseManager


class LicenseManifestGenerator:
    """Generate license manifests for packages."""

    @staticmethod
    def generate_manifest(
        package_license: str,
        source_licenses: list[LicenseRecord],
        output_path: Path | None = None,
    ) -> LicenseManifest:
        """
        Generate license manifest.

        Args:
            package_license: Package license identifier
            source_licenses: List of source license dictionaries
            output_path: Optional path to write manifest file

        Returns:
            License manifest dictionary
        """
        manifest: LicenseManifest = {
            "package_license": package_license,
            "sources": source_licenses,
            "compliance": {
                "status": "compliant",
                "issues": [],
                "warnings": [],
            },
        }

        # Check compliance
        for license_info in source_licenses:
            source_license = license_info.get("license", "unknown")
            source_name = license_info.get("source", "unknown")

            compatibility = LicenseManager.check_compatibility(
                source_license,
                package_license,
            )

            if compatibility == LicenseCompatibility.MISSING:
                compliance = manifest["compliance"]
                warnings = compliance.setdefault("warnings", [])
                warnings.append(f"Missing license for source: {source_name}")

            elif compatibility == LicenseCompatibility.INCOMPATIBLE:
                compliance = manifest["compliance"]
                compliance["status"] = "non-compliant"
                issues_list = compliance.setdefault("issues", [])
                issues_list.append(
                    f"Incompatible license '{source_license}' "
                    f"from source '{source_name}'",
                )

        # Write to file if path provided
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open("w", encoding="utf-8") as f:
                yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)

        return manifest

    @staticmethod
    def generate_source_license_info(
        source_name: str,
        license_id: str,
        license_url: str | None = None,
        attribution: str | None = None,
    ) -> LicenseRecord:
        """
        Generate source license information dictionary.

        Args:
            source_name: Name of the data source
            license_id: License identifier
            license_url: Optional license URL
            attribution: Optional attribution text

        Returns:
            Source license information dictionary
        """
        license_info: LicenseInfo = LicenseManager.get_license_info(license_id)

        return {
            "source": source_name,
            "license": license_id,
            "license_url": license_url or license_info.get("url", ""),
            "attribution": attribution or f"Data from {source_name}",
        }
