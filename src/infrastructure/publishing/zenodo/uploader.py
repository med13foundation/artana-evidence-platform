"""
File upload handling for Zenodo deposits.
"""

import logging
from pathlib import Path

from src.type_definitions.external_apis import ZenodoDepositResponse, ZenodoMetadata

from .client import ZenodoClient

logger = logging.getLogger(__name__)


class ZenodoUploader:
    """Handle file uploads to Zenodo."""

    def __init__(self, client: ZenodoClient):
        """
        Initialize uploader.

        Args:
            client: ZenodoClient instance
        """
        self.client = client

    async def upload_package(
        self,
        package_path: Path,
        metadata: ZenodoMetadata,
        *,
        include_subdirectories: bool = True,
    ) -> ZenodoDepositResponse:
        """
        Upload a complete package directory to Zenodo.

        Args:
            package_path: Path to package directory
            metadata: Deposit metadata
            include_subdirectories: Whether to include subdirectories

        Returns:
            Deposit information dictionary
        """
        package_path = Path(package_path)

        if not package_path.exists():
            message = f"Package path does not exist: {package_path}"
            raise ValueError(message)

        # Collect files to upload
        files_to_upload = self._collect_files(
            package_path,
            include_subdirectories=include_subdirectories,
        )

        # Create deposit and upload files
        return await self.client.create_deposit(
            metadata=metadata,
            files=files_to_upload,
        )

    def _collect_files(
        self,
        base_path: Path,
        *,
        include_subdirectories: bool,
    ) -> list[Path]:
        """
        Collect files from package directory.

        Args:
            base_path: Base directory path
            include_subdirectories: Whether to include subdirectories

        Returns:
            List of file paths
        """
        files = []

        if base_path.is_file():
            files.append(base_path)
        elif base_path.is_dir():
            if include_subdirectories:
                files.extend(base_path.rglob("*"))
            else:
                files.extend(base_path.glob("*"))

        # Filter to only files (not directories)
        return [f for f in files if f.is_file()]

    async def upload_files(
        self,
        files: list[Path],
        metadata: ZenodoMetadata,
    ) -> ZenodoDepositResponse:
        """
        Upload a list of files to Zenodo.

        Args:
            files: List of file paths
            metadata: Deposit metadata

        Returns:
            Deposit information dictionary
        """
        # Validate files exist
        for file_path in files:
            if not Path(file_path).exists():
                message = f"File not found: {file_path}"
                raise ValueError(message)

        # Create deposit and upload
        return await self.client.create_deposit(metadata=metadata, files=files)
