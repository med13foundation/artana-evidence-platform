"""
Zenodo API client for publishing packages.

Provides integration with Zenodo API for depositing research data packages
and minting DOIs.
"""

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import TypeGuard

import httpx

from src.type_definitions.external_apis import (
    ZenodoDepositResponse,
    ZenodoFileInfo,
    ZenodoMetadata,
    ZenodoPublishResponse,
)

logger = logging.getLogger(__name__)


class ZenodoClient:
    """Client for interacting with Zenodo API."""

    # API endpoints
    SANDBOX_URL = "https://sandbox.zenodo.org/api"
    PRODUCTION_URL = "https://zenodo.org/api"

    def __init__(
        self,
        access_token: str,
        *,
        sandbox: bool = True,
        timeout: int = 30,
    ):
        """
        Initialize Zenodo client.

        Args:
            access_token: Zenodo API access token
            sandbox: Whether to use sandbox environment (default: True)
            timeout: Request timeout in seconds
        """
        self.access_token = access_token
        self.base_url = self.SANDBOX_URL if sandbox else self.PRODUCTION_URL
        self.timeout = timeout
        self.sandbox = sandbox

        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    async def create_deposit(
        self,
        metadata: ZenodoMetadata,
        files: list[Path] | None = None,
    ) -> ZenodoDepositResponse:
        """
        Create a new deposit on Zenodo.

        Args:
            metadata: Deposit metadata dictionary
            files: Optional list of file paths to upload

        Returns:
            Deposit information dictionary
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            create_url = f"{self.base_url}/deposit/depositions"
            response = await client.post(
                create_url,
                headers=self.headers,
                json={"metadata": metadata},
            )
            response.raise_for_status()
            payload = response.json()
            if not _is_zenodo_deposit_response(payload):
                message = "Zenodo deposit response payload is invalid"
                raise ValueError(message)
            deposit = payload

            bucket_url = deposit["links"]["bucket"]

            if files:
                await self._upload_files(client, bucket_url, files)

            return deposit

    async def _upload_files(
        self,
        client: httpx.AsyncClient,
        bucket_url: str,
        files: list[Path],
    ) -> None:
        """
        Upload files to Zenodo deposit bucket.

        Args:
            client: HTTP client instance
            bucket_url: Zenodo bucket URL
            files: List of file paths to upload
        """
        for path_item in files:
            file_path = Path(path_item)
            if not file_path.exists():
                logger.warning("File not found: %s", file_path)
                continue

            upload_url = f"{bucket_url}/{file_path.name}"

            with file_path.open("rb") as f:
                upload_headers = {"Authorization": f"Bearer {self.access_token}"}
                response = await client.put(
                    upload_url,
                    headers=upload_headers,
                    content=f.read(),
                )
                response.raise_for_status()

    async def publish_deposit(self, deposit_id: int) -> ZenodoPublishResponse:
        """
        Publish a deposit (mint DOI).

        Args:
            deposit_id: Deposit ID

        Returns:
            Published deposit information with DOI
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            publish_url = (
                f"{self.base_url}/deposit/depositions/{deposit_id}/actions/publish"
            )
            response = await client.post(publish_url, headers=self.headers)
            response.raise_for_status()
            payload = response.json()
            normalized = _coerce_publish_response(payload)
            if normalized is None:
                message = "Zenodo publish response payload is invalid"
                raise ValueError(message)
            return normalized

    async def get_deposit(self, deposit_id: int) -> ZenodoDepositResponse:
        """
        Get deposit information.

        Args:
            deposit_id: Deposit ID

        Returns:
            Deposit information dictionary
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            url = f"{self.base_url}/deposit/depositions/{deposit_id}"
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            payload = response.json()
            if not _is_zenodo_deposit_response(payload):
                message = "Zenodo deposit response payload is invalid"
                raise ValueError(message)
            return payload

    async def update_deposit(
        self,
        deposit_id: int,
        metadata: ZenodoMetadata,
    ) -> ZenodoDepositResponse:
        """
        Update deposit metadata.

        Args:
            deposit_id: Deposit ID
            metadata: Updated metadata dictionary

        Returns:
            Updated deposit information
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            url = f"{self.base_url}/deposit/depositions/{deposit_id}"
            response = await client.put(
                url,
                headers=self.headers,
                json={"metadata": metadata},
            )
            response.raise_for_status()
            payload = response.json()
            if not _is_zenodo_deposit_response(payload):
                message = "Zenodo deposit response payload is invalid"
                raise ValueError(message)
            return payload

    def extract_doi(
        self,
        deposit: ZenodoDepositResponse | ZenodoPublishResponse,
    ) -> str | None:
        """
        Extract DOI from deposit response.

        Args:
            deposit: Deposit information dictionary

        Returns:
            DOI string or None
        """
        doi_value = deposit.get("doi")
        if isinstance(doi_value, str):
            return doi_value

        metadata = deposit.get("metadata")
        if isinstance(metadata, dict):
            metadata_doi = metadata.get("doi")
            if isinstance(metadata_doi, str):
                return metadata_doi

        return None


def _is_str_dict(value: object) -> TypeGuard[dict[str, str]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(k, str) and isinstance(v, str) for k, v in value.items())


def _is_list_of_str_dicts(value: object) -> bool:
    if not isinstance(value, list):
        return False
    return all(
        isinstance(item, dict)
        and all(isinstance(k, str) and isinstance(v, str) for k, v in item.items())
        for item in value
    )


def _is_list_of_strings(value: object) -> bool:
    if not isinstance(value, list):
        return False
    return all(isinstance(item, str) for item in value)


def _is_zenodo_metadata(value: object) -> TypeGuard[ZenodoMetadata]:
    if not isinstance(value, dict):
        return False

    for key, entry in value.items():
        if key in {
            "title",
            "description",
            "license",
            "publication_date",
            "access_right",
            "version",
            "language",
            "notes",
        }:
            if not isinstance(entry, str):
                return False
        elif key == "keywords":
            if not _is_list_of_strings(entry):
                return False
        elif key in {"creators", "communities", "subjects"}:
            if not _is_list_of_str_dicts(entry):
                return False
        else:
            return False
    return True


def _is_zenodo_file_info(value: object) -> TypeGuard[ZenodoFileInfo]:
    if not isinstance(value, dict):
        return False
    required_fields: dict[str, type[object]] = {
        "id": str,
        "filename": str,
        "filesize": int,
        "checksum": str,
        "download": str,
    }
    for field, field_type in required_fields.items():
        entry = value.get(field)
        if not isinstance(entry, field_type):
            return False
    return True


def _is_file_info_list(value: object) -> bool:
    if not isinstance(value, list):
        return False
    return all(_is_zenodo_file_info(item) for item in value)


def _has_optional_int_fields(
    payload: Mapping[str, object],
    fields: tuple[str, ...],
) -> bool:
    for field in fields:
        value = payload.get(field)
        if value is None:
            continue
        if not isinstance(value, int):
            return False
    return True


def _has_optional_str_fields(
    payload: Mapping[str, object],
    fields: tuple[str, ...],
) -> bool:
    for field in fields:
        value = payload.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            return False
    return True


def _is_optional_bool(value: object) -> bool:
    return value is None or isinstance(value, bool)


def _is_optional_metadata(value: object) -> bool:
    return value is None or _is_zenodo_metadata(value)


def _is_optional_files(value: object) -> bool:
    return value is None or _is_file_info_list(value)


def _is_zenodo_deposit_response(value: object) -> TypeGuard[ZenodoDepositResponse]:
    if not isinstance(value, dict):
        return False
    validations = (
        _has_optional_int_fields(value, ("id", "owner", "record_id")),
        _has_optional_str_fields(
            value,
            ("conceptrecid", "doi", "doi_url", "record_url", "state"),
        ),
        _is_optional_bool(value.get("submitted")),
        _is_optional_metadata(value.get("metadata")),
        _is_optional_files(value.get("files")),
    )
    if not all(validations):
        return False
    return _is_str_dict(value.get("links"))


def _coerce_publish_response(value: object) -> ZenodoPublishResponse | None:
    if not isinstance(value, dict):
        return None
    identifier = value.get("id")
    doi_value = value.get("doi")
    if not isinstance(identifier, int) or not isinstance(doi_value, str):
        return None

    def _string_field(field: str) -> str:
        raw = value.get(field)
        return raw if isinstance(raw, str) else ""

    return {
        "id": identifier,
        "doi": doi_value,
        "doi_url": _string_field("doi_url"),
        "record_url": _string_field("record_url"),
        "conceptdoi": _string_field("conceptdoi"),
        "conceptrecid": _string_field("conceptrecid"),
    }
