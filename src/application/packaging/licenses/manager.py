"""
License compliance checking for Artana Resource Library packages.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

import yaml

if TYPE_CHECKING:
    from src.type_definitions.packaging import (
        LicenseInfo,
        LicenseManifest,
        LicenseRecord,
        LicenseValidationResult,
    )


class LicenseCompatibility(str, Enum):
    """License compatibility levels."""

    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    UNCERTAIN = "uncertain"
    MISSING = "missing"


class LicenseType(str, Enum):
    """Common license types."""

    CC_BY_4_0 = "CC-BY-4.0"
    CC0_1_0 = "CC0-1.0"
    MIT = "MIT"
    APACHE_2_0 = "Apache-2.0"
    GPL_3_0 = "GPL-3.0"
    PROPRIETARY = "proprietary"
    UNKNOWN = "unknown"


class LicenseManager:
    """Manage license compliance and checking."""

    # License compatibility matrix
    COMPATIBILITY_MATRIX: ClassVar[dict[str, list[str]]] = {
        "CC-BY-4.0": ["CC-BY-4.0", "CC0-1.0", "MIT", "Apache-2.0"],
        "CC0-1.0": ["CC-BY-4.0", "CC0-1.0", "MIT", "Apache-2.0"],
        "MIT": ["CC-BY-4.0", "CC0-1.0", "MIT", "Apache-2.0"],
        "Apache-2.0": ["CC-BY-4.0", "CC0-1.0", "MIT", "Apache-2.0"],
        "GPL-3.0": ["GPL-3.0"],
    }

    @staticmethod
    def check_compatibility(
        source_license: str,
        target_license: str,
    ) -> LicenseCompatibility:
        """
        Check compatibility between two licenses.

        Args:
            source_license: Source license identifier
            target_license: Target license identifier

        Returns:
            LicenseCompatibility result
        """
        if not source_license or source_license == "unknown":
            return LicenseCompatibility.MISSING

        if not target_license or target_license == "unknown":
            return LicenseCompatibility.MISSING

        if source_license == target_license:
            return LicenseCompatibility.COMPATIBLE

        compatible_licenses = LicenseManager.COMPATIBILITY_MATRIX.get(
            source_license,
            [],
        )

        if target_license in compatible_licenses:
            return LicenseCompatibility.COMPATIBLE

        return LicenseCompatibility.INCOMPATIBLE

    @staticmethod
    def validate_license(license_id: str) -> LicenseValidationResult:
        """
        Validate license identifier.

        Args:
            license_id: License identifier

        Returns:
            Validation result dictionary
        """
        valid_licenses = [
            "CC-BY-4.0",
            "CC0-1.0",
            "MIT",
            "Apache-2.0",
            "GPL-3.0",
        ]

        is_valid = license_id in valid_licenses

        return {
            "valid": is_valid,
            "license": license_id,
            "message": (
                f"License '{license_id}' is valid"
                if is_valid
                else f"License '{license_id}' is not recognized"
            ),
        }

    @staticmethod
    def generate_manifest(
        licenses: list[LicenseRecord],
        output_path: Path | None = None,
    ) -> LicenseManifest:
        """
        Generate license manifest.

        Args:
            licenses: List of license dictionaries
            output_path: Optional path to write manifest file

        Returns:
            License manifest dictionary
        """
        package_license = "CC-BY-4.0"
        manifest: LicenseManifest = {
            "package_license": package_license,
            "sources": licenses,
            "compliance": {
                "status": "compliant",
                "issues": [],
            },
        }

        # Check compliance
        for license_info in licenses:
            source_license = license_info.get("license", "unknown")
            compatibility = LicenseManager.check_compatibility(
                source_license,
                package_license,
            )

            if compatibility == LicenseCompatibility.INCOMPATIBLE:
                compliance = manifest["compliance"]
                issues_list = compliance.setdefault("issues", [])
                compliance["status"] = "non-compliant"
                issues_list.append(
                    f"Incompatible license: {source_license} "
                    f"from {license_info.get('source', 'unknown')}",
                )

        # Write to file if path provided
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8") as f:
                yaml.dump(manifest, f, default_flow_style=False)

        return manifest

    @staticmethod
    def get_license_info(license_id: str) -> LicenseInfo:
        """
        Get license information.

        Args:
            license_id: License identifier

        Returns:
            License information dictionary
        """
        license_urls = {
            "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
            "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
            "MIT": "https://opensource.org/licenses/MIT",
            "Apache-2.0": "https://opensource.org/licenses/Apache-2.0",
            "GPL-3.0": "https://www.gnu.org/licenses/gpl-3.0.html",
        }

        return {
            "id": license_id,
            "url": license_urls.get(license_id, ""),
            "name": license_id,
        }
