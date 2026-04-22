"""
Storage and archival functionality for packages.
"""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile


class PackageStorage:
    """Manage storage and archival of packages."""

    def __init__(self, base_storage_path: Path):
        """
        Initialize storage manager.

        Args:
            base_storage_path: Base directory for storing packages
        """
        self.base_storage_path = Path(base_storage_path)
        self.base_storage_path.mkdir(parents=True, exist_ok=True)

    def archive_package(
        self,
        package_path: Path,
        version: str,
        name: str | None = None,
    ) -> Path:
        """
        Archive a package with versioning.

        Args:
            package_path: Path to package directory
            version: Package version
            name: Optional package name

        Returns:
            Path to archived package
        """
        package_path = Path(package_path)
        package_name = name or package_path.name

        # Create versioned archive directory
        archive_dir = self.base_storage_path / package_name / version
        archive_dir.mkdir(parents=True, exist_ok=True)

        # Copy package to archive
        archive_path = archive_dir / package_path.name
        if package_path.is_dir():
            shutil.copytree(package_path, archive_path, dirs_exist_ok=True)
        else:
            shutil.copy2(package_path, archive_path)

        # Create archive metadata
        metadata = {
            "package_name": package_name,
            "version": version,
            "archived_at": datetime.now(UTC).isoformat(),
            "source_path": str(package_path),
        }

        metadata_path = archive_dir / "archive_metadata.json"
        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        return archive_path

    def create_zip_archive(
        self,
        package_path: Path,
        version: str,
        name: str | None = None,
    ) -> Path:
        """
        Create ZIP archive of package.

        Args:
            package_path: Path to package directory
            version: Package version
            name: Optional package name

        Returns:
            Path to ZIP archive
        """
        package_path = Path(package_path)
        package_name = name or package_path.name

        # Create archive directory
        archive_dir = self.base_storage_path / package_name
        archive_dir.mkdir(parents=True, exist_ok=True)

        # Create ZIP file
        zip_filename = f"{package_name}-v{version}.zip"
        zip_path = archive_dir / zip_filename

        with ZipFile(zip_path, "w") as zip_file:
            if package_path.is_dir():
                for file_path in package_path.rglob("*"):
                    if file_path.is_file():
                        arcname = file_path.relative_to(package_path)
                        zip_file.write(file_path, arcname)
            else:
                zip_file.write(package_path, package_path.name)

        return zip_path

    def list_versions(self, package_name: str) -> list[str]:
        """
        List all versions of a package.

        Args:
            package_name: Package name

        Returns:
            List of version strings
        """
        package_dir = self.base_storage_path / package_name
        if not package_dir.exists():
            return []

        versions = [item.name for item in package_dir.iterdir() if item.is_dir()]
        return sorted(versions)

    def get_latest_version(self, package_name: str) -> str | None:
        """
        Get latest version of a package.

        Args:
            package_name: Package name

        Returns:
            Latest version string or None
        """
        versions = self.list_versions(package_name)
        return versions[-1] if versions else None
