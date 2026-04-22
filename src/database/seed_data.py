"""Seed catalog entry definitions used by database seeding helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, TypeGuard

if TYPE_CHECKING:
    from src.type_definitions.data_sources import SourceCatalogEntrySeed

CATALOG_ENTRIES_PATH = Path(__file__).with_name("catalog_entries_seed.json")


def _is_valid_seed_entry(value: object) -> TypeGuard[SourceCatalogEntrySeed]:
    """Runtime validation helper ensuring JSON entries match expected schema."""
    if not isinstance(value, dict):
        return False

    required_str_keys = ("id", "name", "description", "category", "param_type")
    for key in required_str_keys:
        raw_value = value.get(key)
        if not isinstance(raw_value, str) or raw_value.strip() == "":
            return False

    optional_str_keys = ("url_template", "api_endpoint", "source_type")
    for key in optional_str_keys:
        if key in value and value[key] is not None and not isinstance(value[key], str):
            return False

    if "tags" in value:
        tags_value = value["tags"]
        if not isinstance(tags_value, list) or any(
            not isinstance(tag, str) for tag in tags_value
        ):
            return False

    bool_keys = ("is_active", "requires_auth")
    for key in bool_keys:
        if key in value and not isinstance(value[key], bool):
            return False

    return True


def _load_catalog_seed_entries() -> list[SourceCatalogEntrySeed]:
    """Load catalog entries from disk."""
    raw_text = CATALOG_ENTRIES_PATH.read_text(encoding="utf-8")
    raw_entries = json.loads(raw_text)

    if not isinstance(raw_entries, list):
        error_message = "Catalog entries seed must be a list"
        raise TypeError(error_message)

    validated_entries: list[SourceCatalogEntrySeed] = []
    for entry in raw_entries:
        if not _is_valid_seed_entry(entry):
            error_message = f"Invalid catalog entry seed encountered: {entry}"
            raise ValueError(error_message)
        validated_entries.append(entry)

    return validated_entries


SOURCE_CATALOG_ENTRIES: list[SourceCatalogEntrySeed] = _load_catalog_seed_entries()

DEFAULT_SOURCE_TYPE = "api"
SOURCE_TYPE_OVERRIDES: dict[str, str] = {
    "pubmed": "pubmed",
    "omop": "database",
    "trinetx": "database",
    "ukbiobank": "database",
    "finngen": "database",
    "marketscan": "database",
    "dbgap": "database",
    "stjude_cloud": "database",
    "reddit": "web_scraping",
    "patientslikeme": "web_scraping",
}

for entry in SOURCE_CATALOG_ENTRIES:
    entry_id = entry.get("id")
    if not entry_id:
        continue
    entry.setdefault(
        "source_type",
        SOURCE_TYPE_OVERRIDES.get(entry_id, DEFAULT_SOURCE_TYPE),
    )
