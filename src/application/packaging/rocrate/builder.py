"""
RO-Crate builder for Artana Resource Library.

Creates Research Object Crates (RO-Crates) following the RO-Crate specification
for FAIR data packaging and distribution.
"""

import json
import shutil
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from src.type_definitions.common import JSONObject, JSONValue
from src.type_definitions.json_utils import to_json_value
from src.type_definitions.packaging import ProvenanceMetadata, ROCrateFileEntry

JSONMetadata = JSONObject


class ROCrateBuilder:
    """
    Builder for creating RO-Crate compliant packages.

    RO-Crate is a lightweight approach to packaging research data with
    their metadata in a machine-readable way. See: https://www.researchobject.org/ro-crate/
    """

    def __init__(  # noqa: PLR0913 - constructor takes crate metadata options
        self,
        base_path: Path,
        name: str = "Artana Resource Library Dataset",
        description: str | None = None,
        version: str = "1.0.0",
        license_id: str | None = None,
        author: str | None = None,
        **legacy_kwargs: str | None,
    ):
        """
        Initialize RO-Crate builder.

        Args:
            base_path: Base directory for the RO-Crate package
            name: Dataset name
            description: Dataset description
            version: Dataset version
            license_id: License identifier (default: CC-BY-4.0)
            author: Author/organization name
            legacy_kwargs: Additional compatibility parameters (e.g., legacy license)
        """
        legacy_license = legacy_kwargs.pop("license", None)
        if legacy_kwargs:
            unexpected = ", ".join(sorted(legacy_kwargs))
            msg = f"Unexpected keyword arguments: {unexpected}"
            raise TypeError(msg)

        self.base_path = Path(base_path)
        self.name = name
        self.description = description or (
            "Curated biomedical data for MED13 genetic variants, "
            "phenotypes, and supporting evidence"
        )
        self.version = version
        if (
            legacy_license is not None
            and license_id is not None
            and legacy_license != license_id
        ):
            msg = "license and license_id parameters must match when both provided"
            raise ValueError(msg)
        resolved_license = license_id or legacy_license or "CC-BY-4.0"
        self.license_id = resolved_license
        self.author = author or "Artana"
        self.crate_id = str(uuid.uuid4())
        self.created_at = datetime.now(UTC).isoformat()

        # Ensure base path exists
        self.base_path.mkdir(parents=True, exist_ok=True)

    @property
    def license(self) -> str:
        """Backward-compatible access to the crate license identifier."""
        return self.license_id

    @license.setter
    def license(self, value: str) -> None:
        """Update the crate license identifier."""
        self.license_id = value

    def create_crate_structure(self) -> dict[str, Path]:
        """
        Create RO-Crate directory structure.

        Returns:
            Dictionary with created paths
        """
        paths = {
            "data": self.base_path / "data",
            "metadata": self.base_path / "metadata",
        }

        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)

        return paths

    def add_data_file(
        self,
        source_path: Path,
        target_name: str | None = None,
        _description: str | None = None,
    ) -> str:
        """
        Add a data file to the RO-Crate package.

        Args:
            source_path: Path to source file
            target_name: Optional target filename (defaults to source name)
            description: Optional file description

        Returns:
            Relative path to the file in the crate
        """
        data_dir = self.base_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        target_name = target_name or source_path.name
        target_path = data_dir / target_name

        # Copy file
        shutil.copy2(source_path, target_path)

        return f"data/{target_name}"

    def _coerce_path(self, file_info: ROCrateFileEntry) -> str:
        """Extract and validate the required path field from file info."""
        path_value = file_info.get("path")
        if not isinstance(path_value, str) or not path_value:
            msg = "file_info entry must include a non-empty 'path' string"
            raise ValueError(msg)
        return path_value

    def _string_or_none(
        self,
        payload: Mapping[str, object],
        field: str,
    ) -> str | None:
        """Safely read string fields from JSON metadata objects."""
        value = payload.get(field)
        return value if isinstance(value, str) else None

    def _create_root_dataset(
        self,
        *,
        license_info: JSONObject,
        creator_info: JSONObject,
    ) -> JSONObject:
        keyword_values: list[str] = [
            "MED13",
            "genetics",
            "variants",
            "phenotypes",
            "biomedical data",
            "FAIR data",
        ]
        keywords_json = self._json_list(
            keyword_values,
            error_message="Keywords must serialize to a JSON list",
        )
        return {
            "@id": "./",
            "@type": "Dataset",
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "license": license_info,
            "creator": creator_info,
            "datePublished": self.created_at,
            "keywords": keywords_json,
        }

    def _provenance_entries(
        self,
        provenance_info: ProvenanceMetadata | None,
    ) -> list[JSONMetadata]:
        entries: list[JSONMetadata] = []
        if not provenance_info:
            return entries
        sources_value = provenance_info.get("sources")
        if not isinstance(sources_value, list):
            return entries
        structured_sources: list[Mapping[str, object]] = [
            source for source in sources_value if isinstance(source, Mapping)
        ]
        for source in structured_sources:
            download_entry: JSONMetadata = {
                "@type": self._string_or_none(source, "@type") or "DataDownload",
                "name": self._string_or_none(source, "name"),
                "contentUrl": self._string_or_none(source, "url"),
                "datePublished": self._string_or_none(source, "datePublished"),
                "version": self._string_or_none(source, "version"),
            }
            entries.append(download_entry)
        return entries

    def _build_file_entities(
        self,
        data_files: Sequence[ROCrateFileEntry],
    ) -> list[JSONMetadata]:
        entities: list[JSONMetadata] = []
        for file_info in data_files:
            file_path = self._coerce_path(file_info)
            file_entity: JSONMetadata = {
                "@id": file_path,
                "@type": "File",
                "name": self._string_or_none(file_info, "name") or Path(file_path).name,
            }

            description = self._string_or_none(file_info, "description")
            if description:
                file_entity["description"] = description

            encoding = self._string_or_none(file_info, "encodingFormat")
            if encoding:
                file_entity["encodingFormat"] = encoding

            date_created = self._string_or_none(file_info, "dateCreated")
            if date_created:
                file_entity["dateCreated"] = date_created

            entities.append(file_entity)
        return entities

    @staticmethod
    def _json_list(value: object, *, error_message: str) -> list[JSONValue]:
        converted = to_json_value(value)
        if not isinstance(converted, list):
            raise TypeError(error_message)
        return converted

    def generate_metadata(
        self,
        data_files: Sequence[ROCrateFileEntry],
        provenance_info: ProvenanceMetadata | None = None,
    ) -> JSONMetadata:
        """
        Generate RO-Crate metadata.json.

        Args:
            data_files: List of data file metadata dictionaries
            provenance_info: Optional provenance information

        Returns:
            RO-Crate metadata dictionary
        """
        # Build context with RO-Crate vocabulary
        context: JSONObject = {
            "@vocab": "https://schema.org/",
            "ro-crate": "https://w3id.org/ro/crate#",
        }

        # Root dataset entity
        license_info: JSONObject = {
            "@id": f"https://spdx.org/licenses/{self.license_id}.html",
            "@type": "CreativeWork",
            "name": self.license_id,
        }
        creator_info: JSONObject = {
            "@type": "Organization",
            "name": self.author,
        }
        root_dataset = self._create_root_dataset(
            license_info=license_info,
            creator_info=creator_info,
        )

        has_part = self._provenance_entries(provenance_info)

        file_entities = self._build_file_entities(data_files)
        if file_entities:
            has_part.extend(file_entities)

        if has_part:
            root_dataset["hasPart"] = self._json_list(
                has_part,
                error_message="hasPart entries must serialize to a JSON list",
            )

        return {
            "@context": context,
            "@graph": [root_dataset, *file_entities],
        }

    def build(
        self,
        data_files: Sequence[ROCrateFileEntry],
        provenance_info: ProvenanceMetadata | None = None,
    ) -> Path:
        """
        Build complete RO-Crate package.

        Args:
            data_files: List of data file metadata dictionaries
            provenance_info: Optional provenance information

        Returns:
            Path to the created RO-Crate directory
        """
        # Create directory structure
        self.create_crate_structure()

        # Generate metadata
        metadata = self.generate_metadata(data_files, provenance_info)

        # Write metadata file
        metadata_path = self.base_path / "ro-crate-metadata.json"
        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        return self.base_path

    def validate(self) -> JSONObject:
        """
        Validate RO-Crate structure and metadata.

        Returns:
            Validation result dictionary
        """
        errors = []
        warnings = []

        # Check for required files
        metadata_file = self.base_path / "ro-crate-metadata.json"
        if not metadata_file.exists():
            errors.append("Missing ro-crate-metadata.json")

        # Validate metadata structure
        if metadata_file.exists():
            try:
                with metadata_file.open(encoding="utf-8") as f:
                    metadata = json.load(f)

                # Check required fields
                if "@context" not in metadata:
                    errors.append("Missing @context in metadata")

                if "@graph" not in metadata:
                    errors.append("Missing @graph in metadata")
                else:
                    # Check for root dataset
                    root_found = False
                    for entity in metadata["@graph"]:
                        if (
                            entity.get("@id") == "./"
                            and entity.get("@type") == "Dataset"
                        ):
                            root_found = True
                            break

                    if not root_found:
                        errors.append("Missing root dataset entity")

            except json.JSONDecodeError as e:
                errors.append(f"Invalid JSON in metadata: {e}")

        # Check data directory
        data_dir = self.base_path / "data"
        if not data_dir.exists():
            warnings.append("Data directory does not exist")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }
