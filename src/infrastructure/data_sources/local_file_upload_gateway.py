"""
Infrastructure implementation of the file upload gateway.

Handles filesystem persistence and parsing for CSV, JSON, XML, and TSV
uploads, returning the domain-level result objects.
"""

from __future__ import annotations

import csv
import json
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from src.domain.services.file_upload_service import (
    DataRecord,
    FileUploadGateway,
    FileUploadResult,
)
from src.type_definitions.common import (  # noqa: TCH001
    JSONObject,
    JSONValue,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from xml.etree.ElementTree import Element

    from src.domain.entities.user_data_source import SourceConfiguration

# Prefer defusedxml if available
try:  # pragma: no cover - import guard
    from defusedxml.ElementTree import fromstring as xml_fromstring

    DEFUSED_XML_AVAILABLE = True
except (ImportError, ModuleNotFoundError):  # pragma: no cover
    xml_fromstring = None  # type: ignore[assignment]
    DEFUSED_XML_AVAILABLE = False


class LocalFileUploadGateway(FileUploadGateway):
    """Persist uploads to disk and parse them with built-in libraries."""

    def __init__(self, upload_dir: str = "data/uploads"):
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.supported_formats = {
            "csv": ["text/csv", "application/csv"],
            "json": ["application/json", "text/json"],
            "xml": ["application/xml", "text/xml"],
            "tsv": ["text/tab-separated-values"],
        }
        self._logger = logging.getLogger(__name__)

    def process_upload(
        self,
        *,
        filename: str,
        content_type: str,
        file_bytes: bytes,
        configuration: SourceConfiguration,
        max_records: int = 10_000,
    ) -> FileUploadResult:
        file_size = len(file_bytes)
        if file_size > 100 * 1024 * 1024:
            return FileUploadResult(
                success=False,
                errors=["File too large (max 100MB)"],
                file_size=file_size,
            )

        detected_format = self._detect_format(filename, content_type, file_bytes)
        if not detected_format:
            return FileUploadResult(
                success=False,
                errors=["Unsupported file format"],
                file_size=file_size,
            )

        try:
            file_path = self._save_file(file_bytes, filename)
        except OSError as exc:  # pragma: no cover - filesystem error
            return FileUploadResult(
                success=False,
                file_size=file_size,
                errors=[f"Unable to store file: {exc!s}"],
            )

        try:
            records = self.parse_records(
                filename=filename,
                content_type=content_type,
                file_bytes=file_bytes,
                max_records=max_records,
            )
        except ValueError as exc:
            return FileUploadResult(
                success=False,
                file_path=str(file_path),
                file_size=file_size,
                detected_format=detected_format,
                errors=[str(exc)],
            )

        validation_errors = self._validate_records(records, configuration)

        metadata: JSONObject = {
            "columns": self._to_json_value(self._extract_columns(records)),
            "inferred_types": self._to_json_value(self._infer_data_types(records)),
            "validation_errors": self._to_json_value(validation_errors),
        }

        return FileUploadResult(
            success=len(validation_errors) == 0,
            file_path=str(file_path),
            record_count=len(records),
            file_size=file_size,
            detected_format=detected_format,
            errors=validation_errors,
            metadata=metadata,
        )

    def parse_records(
        self,
        *,
        filename: str,
        content_type: str,
        file_bytes: bytes,
        max_records: int = 10_000,
    ) -> list[DataRecord]:
        detected_format = self._detect_format(filename, content_type, file_bytes)
        if not detected_format:
            error = "Unsupported file format"
            raise ValueError(error)

        content_text = file_bytes.decode("utf-8", errors="replace")
        parser_map: dict[str, Callable[[str, int], list[DataRecord]]] = {
            "csv": self._parse_csv,
            "json": self._parse_json,
            "xml": self._parse_xml,
            "tsv": self._parse_tsv,
        }
        parser = parser_map.get(detected_format)
        if parser is None:
            error = f"No parser registered for format {detected_format}"
            raise ValueError(error)
        return parser(content_text, max_records)

    def _detect_format(
        self,
        filename: str,
        content_type: str,
        file_bytes: bytes,
    ) -> str | None:
        ext = Path(filename).suffix.lower().replace(".", "")
        detected: str | None = next(
            (
                fmt
                for fmt, mimetypes in self.supported_formats.items()
                if content_type in mimetypes
            ),
            None,
        )

        if detected is None and ext in self.supported_formats:
            detected = ext

        if detected is None:
            head_line = file_bytes.splitlines()[0:1]
            head = head_line[0] if head_line else b""
            if file_bytes.startswith((b"{", b"[")):
                detected = "json"
            elif file_bytes.startswith(b"<"):
                detected = "xml"
            elif b"," in head:
                detected = "csv"
            elif b"\t" in head:
                detected = "tsv"

        return detected

    def _save_file(self, file_content: bytes, filename: str) -> Path:
        safe_name = f"{uuid.uuid4()}_{Path(filename).name}"
        file_path = self.upload_dir / safe_name
        file_path.write_bytes(file_content)
        return file_path

    def _parse_csv(self, content: str, max_records: int) -> list[DataRecord]:
        records: list[DataRecord] = []
        reader = csv.DictReader(content.splitlines())
        for i, row in enumerate(reader):
            if i >= max_records:
                break
            data = self._row_to_json_object(row)
            records.append(DataRecord(data=data, line_number=i + 1))
        return records

    def _parse_tsv(self, content: str, max_records: int) -> list[DataRecord]:
        records: list[DataRecord] = []
        reader = csv.DictReader(content.splitlines(), delimiter="\t")
        for i, row in enumerate(reader):
            if i >= max_records:
                break
            data = self._row_to_json_object(row)
            records.append(DataRecord(data=data, line_number=i + 1))
        return records

    def _parse_json(self, content: str, max_records: int) -> list[DataRecord]:
        parsed = json.loads(content or "{}")
        records: list[DataRecord] = []
        if isinstance(parsed, list):
            for i, item in enumerate(parsed[:max_records]):
                if isinstance(item, dict):
                    data = self._to_json_object(item)
                else:
                    data = {"value": self._to_json_value(item)}
                records.append(DataRecord(data=data, line_number=i + 1))
        elif isinstance(parsed, dict):
            data = self._to_json_object(parsed)
            records.append(DataRecord(data=data))
        elif isinstance(parsed, str):
            records.append(
                DataRecord(
                    data={"value": parsed},
                    line_number=1,
                ),
            )
        return records

    def _parse_xml(self, content: str, max_records: int) -> list[DataRecord]:
        if not DEFUSED_XML_AVAILABLE or xml_fromstring is None:
            error = "XML parsing is disabled (defusedxml not installed)"
            raise ValueError(error)
        root = xml_fromstring(content)
        records: list[DataRecord] = []
        for i, element in enumerate(root):
            if i >= max_records:
                break
            record_data = self._xml_element_to_dict(element)
            records.append(DataRecord(data=record_data, line_number=i + 1))
        return records

    def _xml_element_to_dict(self, element: Element) -> JSONObject:
        data: JSONObject = {}
        data[element.tag] = {child.tag: child.text or "" for child in element}
        return data

    def _row_to_json_object(self, row: Mapping[str, object]) -> JSONObject:
        """Convert CSV/TSV rows to typed JSON objects."""
        return {str(key): self._to_json_value(value) for key, value in row.items()}

    def _validate_records(
        self,
        records: list[DataRecord],
        configuration: SourceConfiguration,
    ) -> list[str]:
        metadata = configuration.metadata or {}
        expected_fields = self._as_str_list(metadata.get("expected_fields"))
        required_fields = self._as_str_list(metadata.get("required_fields"))
        expected_types = self._as_str_dict(metadata.get("expected_types"))

        errors: list[str] = []
        if required_fields:
            errors.extend(self._validate_required_fields(records, required_fields))
        if expected_fields:
            errors.extend(self._validate_expected_fields(records, expected_fields))
        if expected_types:
            errors.extend(self._validate_expected_types(records, expected_types))
        return errors

    @staticmethod
    def _to_json_value(value: object) -> JSONValue:
        if isinstance(value, str | int | float | bool) or value is None:
            return value
        if isinstance(value, dict):
            return {
                str(k): LocalFileUploadGateway._to_json_value(v)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [LocalFileUploadGateway._to_json_value(item) for item in value]
        return str(value)

    @staticmethod
    def _to_json_object(payload: Mapping[str, object]) -> JSONObject:
        return {
            str(key): LocalFileUploadGateway._to_json_value(value)
            for key, value in payload.items()
        }

    @staticmethod
    def _as_str_list(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        return []

    @staticmethod
    def _as_str_dict(value: object) -> dict[str, str]:
        if isinstance(value, dict):
            return {str(k): str(v) for k, v in value.items()}
        return {}

    def _validate_required_fields(
        self,
        records: list[DataRecord],
        required_fields: list[str],
    ) -> list[str]:
        errors: list[str] = []
        for record in records:
            missing = [field for field in required_fields if field not in record.data]
            if missing:
                error = f"Missing required fields: {missing}"
                record.validation_errors.append(error)
                errors.append(error)
        return errors

    def _validate_expected_fields(
        self,
        records: list[DataRecord],
        expected_fields: list[str],
    ) -> list[str]:
        errors: list[str] = []
        for record in records:
            unexpected = [
                field for field in record.data if field not in expected_fields
            ]
            if unexpected:
                error = f"Unexpected fields: {unexpected}"
                record.validation_errors.append(error)
                errors.append(error)
        return errors

    def _validate_expected_types(
        self,
        records: list[DataRecord],
        expected_types: dict[str, str],
    ) -> list[str]:
        errors: list[str] = []
        for record in records:
            for field, expected_type in expected_types.items():
                if field in record.data:
                    value = record.data[field]
                    if not self._validate_data_type(value, expected_type):
                        error = (
                            f"Field '{field}' has wrong type (expected {expected_type})"
                        )
                        record.validation_errors.append(error)
                        errors.append(error)
        return errors

    def _validate_data_type(self, value: JSONValue, expected_type: str) -> bool:
        validators: dict[str, Callable[[JSONValue], bool]] = {
            "string": lambda v: isinstance(v, str),
            "integer": self._is_integer_like,
            "float": self._is_float_like,
            "boolean": self._is_boolean_like,
        }

        def _accept_any(_value: JSONValue) -> bool:
            return True

        validator = validators.get(expected_type, _accept_any)
        return validator(value)

    @staticmethod
    def _is_integer_like(value: JSONValue) -> bool:
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return True
        if isinstance(value, str):
            try:
                int(value)
            except ValueError:
                return False
            else:
                return True
        return False

    @staticmethod
    def _is_float_like(value: JSONValue) -> bool:
        if isinstance(value, bool):
            return False
        if isinstance(value, int | float):
            return True
        if isinstance(value, str):
            try:
                float(value)
            except ValueError:
                return False
            else:
                return True
        return False

    @staticmethod
    def _is_boolean_like(value: JSONValue) -> bool:
        if isinstance(value, bool):
            return True
        if isinstance(value, str):
            return value.lower() in {"true", "false", "1", "0"}
        return False

    def _extract_columns(self, records: list[DataRecord]) -> list[str]:
        columns: set[str] = set()
        for record in records:
            columns.update(record.data.keys())
        return sorted(columns)

    def _infer_data_types(self, records: list[DataRecord]) -> dict[str, str]:
        if not records:
            return {}
        type_counts: dict[str, dict[str, int]] = {}
        columns = self._extract_columns(records)
        for column in columns:
            type_counts[column] = {
                "string": 0,
                "integer": 0,
                "float": 0,
                "boolean": 0,
            }
            for record in records[:100]:
                if column in record.data:
                    value = record.data[column]
                    if isinstance(value, str):
                        if self._is_integer_like(value):
                            type_counts[column]["integer"] += 1
                        elif self._is_float_like(value):
                            type_counts[column]["float"] += 1
                        elif self._is_boolean_like(value):
                            type_counts[column]["boolean"] += 1
                        else:
                            type_counts[column]["string"] += 1
        inferred_types = {}
        for column, counts in type_counts.items():
            most_common = max(counts.items(), key=lambda x: x[1])
            inferred_types[column] = most_common[0]
        return inferred_types
