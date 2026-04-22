"""
Release management and orchestration.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

from src.application.packaging import PackageStorage
from src.infrastructure.publishing.versioning.semantic_versioner import (
    SemanticVersioner,
    VersionType,
)
from src.infrastructure.publishing.zenodo.client import ZenodoClient
from src.infrastructure.publishing.zenodo.doi_service import DOIService
from src.infrastructure.publishing.zenodo.uploader import ZenodoUploader
from src.type_definitions.common import JSONObject
from src.type_definitions.external_apis import ZenodoMetadata

logger = logging.getLogger(__name__)


class ReleaseManager:
    """Manage release lifecycle and publication."""

    def __init__(
        self,
        zenodo_client: ZenodoClient,
        storage_path: Path,
        package_name: str = "Artana Resource Library",
    ):
        """
        Initialize release manager.

        Args:
            zenodo_client: ZenodoClient instance
            storage_path: Path for storing packages
            package_name: Name of the package
        """
        self.zenodo_client = zenodo_client
        self.uploader = ZenodoUploader(zenodo_client)
        self.doi_service = DOIService(zenodo_client)
        self.storage = PackageStorage(storage_path)
        self.versioner = SemanticVersioner()
        self.package_name = package_name

    async def create_release(
        self,
        package_path: Path,
        version: str | None,
        release_notes: str | None = None,
        version_type: VersionType | None = None,
        metadata: ZenodoMetadata | None = None,
    ) -> JSONObject:
        """
        Create and publish a new release.

        Args:
            package_path: Path to package directory
            version: Version string (or None to auto-increment)
            release_notes: Optional release notes
            version_type: Optional version type for auto-increment
            metadata: Optional additional metadata

        Returns:
            Release information dictionary
        """
        # Determine version
        if version is None:
            existing_versions = self.storage.list_versions(self.package_name)
            if existing_versions:
                latest = self.versioner.get_latest_version(existing_versions)
                if latest is None:
                    version = "1.0.0"
                elif version_type is not None:
                    version = self.versioner.increment_version(latest, version_type)
                else:
                    version = self.versioner.increment_version(
                        latest,
                        VersionType.PATCH,
                    )
            else:
                version = "1.0.0"

        # Validate version
        if not self.versioner.validate_version(version):
            message = f"Invalid version format: {version}"
            raise ValueError(message)

        # Archive package
        archive_path = self.storage.archive_package(
            package_path,
            version,
            self.package_name,
        )

        # Create ZIP archive
        zip_path = self.storage.create_zip_archive(
            package_path,
            version,
            self.package_name,
        )

        # Prepare Zenodo metadata
        zenodo_metadata = self._prepare_zenodo_metadata(
            version,
            release_notes,
            metadata,
        )

        # Upload to Zenodo
        deposit = await self.uploader.upload_package(package_path, zenodo_metadata)

        # Mint DOI
        doi_result = await self.doi_service.mint_doi(deposit["id"])

        # Create release record
        release_info: JSONObject = {
            "version": version,
            "doi": doi_result["doi"],
            "doi_url": self.doi_service.format_doi_url(doi_result["doi"]),
            "zenodo_url": doi_result["url"],
            "deposit_id": deposit["id"],
            "archive_path": str(archive_path),
            "zip_path": str(zip_path),
            "created_at": datetime.now(UTC).isoformat(),
            "release_notes": release_notes,
        }

        logger.info(
            "Release %s created successfully: %s",
            version,
            doi_result["doi"],
        )

        return release_info

    def _prepare_zenodo_metadata(
        self,
        version: str,
        release_notes: str | None,
        additional_metadata: ZenodoMetadata | None,
    ) -> ZenodoMetadata:
        """
        Prepare metadata for Zenodo deposit.

        Args:
            version: Version string
            release_notes: Optional release notes
            additional_metadata: Optional additional metadata

        Returns:
            Zenodo metadata dictionary
        """
        metadata: ZenodoMetadata = {
            "title": f"{self.package_name} v{version}",
            "description": release_notes or f"{self.package_name} release {version}",
            "version": version,
            "creators": [
                {
                    "name": "Artana",
                    "affiliation": "Artana",
                },
            ],
            "license": "cc-by-4.0",
            "keywords": [
                "MED13",
                "genetics",
                "variants",
                "phenotypes",
                "biomedical data",
                "FAIR data",
            ],
            "publication_date": datetime.now(UTC).date().isoformat(),
        }

        # Merge additional metadata
        if additional_metadata:
            metadata.update(additional_metadata)

        return metadata

    def list_releases(self) -> list[str]:
        """
        List all release versions.

        Returns:
            List of version strings
        """
        return self.storage.list_versions(self.package_name)

    def get_latest_release(self) -> str | None:
        """
        Get latest release version.

        Returns:
            Latest version string or None
        """
        versions = self.list_releases()
        return self.versioner.get_latest_version(versions) if versions else None
