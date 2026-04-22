"""Pure payload helpers for PubMed search gateway responses."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.type_definitions.common import JSONObject, JSONValue  # noqa: TC001


def extract_article_ids(raw_id_list: JSONValue | None) -> list[str]:
    if not isinstance(raw_id_list, Sequence) or isinstance(
        raw_id_list,
        str | bytes | bytearray,
    ):
        return []
    article_ids: list[str] = []
    for raw_id in raw_id_list:
        if isinstance(raw_id, str):
            normalized = raw_id.strip()
            if normalized:
                article_ids.append(normalized)
    return article_ids


def extract_summary_ids(
    result_payload: Mapping[str, JSONValue],
    *,
    fallback_ids: list[str],
) -> list[str]:
    raw_uids = result_payload.get("uids")
    if not isinstance(raw_uids, Sequence) or isinstance(
        raw_uids,
        str | bytes | bytearray,
    ):
        return fallback_ids

    ordered_ids: list[str] = []
    for raw_uid in raw_uids:
        if isinstance(raw_uid, str):
            normalized = raw_uid.strip()
            if normalized:
                ordered_ids.append(normalized)
    return ordered_ids or fallback_ids


def build_preview_record(
    article_id: str,
    summary_payload: Mapping[str, JSONValue],
) -> JSONObject:
    record: JSONObject = {
        "pmid": article_id,
        "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{article_id}/",
    }

    title = normalized_string(summary_payload.get("title"))
    if title is not None:
        record["title"] = title

    pubdate = normalized_string(summary_payload.get("pubdate"))
    if pubdate is not None:
        record["pubdate"] = pubdate

    journal = normalized_string(summary_payload.get("fulljournalname")) or (
        normalized_string(summary_payload.get("source"))
    )
    if journal is not None:
        record["journal"] = journal

    doi = extract_article_identifier(
        summary_payload,
        expected_id_type="doi",
    )
    if doi is not None:
        record["doi"] = doi

    pmc_id = extract_article_identifier(
        summary_payload,
        expected_id_type="pmc",
    ) or extract_article_identifier(
        summary_payload,
        expected_id_type="pmcid",
    )
    if pmc_id is not None:
        record["pmc_id"] = pmc_id

    authors = extract_authors(summary_payload.get("authors"))
    if authors:
        record["authors"] = authors

    languages = extract_string_list(summary_payload.get("lang"))
    if languages:
        record["languages"] = languages

    publication_types = extract_string_list(summary_payload.get("pubtype"))
    if publication_types:
        record["publication_types"] = publication_types

    return record


def extract_article_identifier(
    summary_payload: Mapping[str, JSONValue],
    *,
    expected_id_type: str,
) -> str | None:
    raw_article_ids = summary_payload.get("articleids")
    if not isinstance(raw_article_ids, Sequence) or isinstance(
        raw_article_ids,
        str | bytes | bytearray,
    ):
        return None

    for raw_identifier in raw_article_ids:
        if not isinstance(raw_identifier, Mapping):
            continue
        raw_id_type = raw_identifier.get("idtype")
        if not isinstance(raw_id_type, str):
            continue
        if raw_id_type.strip().lower() != expected_id_type:
            continue

        raw_value = raw_identifier.get("value")
        if not isinstance(raw_value, str):
            continue
        normalized = raw_value.strip()
        if normalized == "":
            continue
        if expected_id_type in {"pmc", "pmcid"}:
            return normalize_pmc_id(normalized)
        return normalized

    return None


def normalize_pmc_id(raw_value: str) -> str | None:
    normalized = raw_value.strip().upper().rstrip(";")
    if normalized.startswith("PMC-ID:"):
        normalized = normalized.removeprefix("PMC-ID:").strip()
    if not normalized:
        return None
    if normalized.startswith("PMC"):
        return normalized
    return f"PMC{normalized}"


def extract_authors(raw_authors: JSONValue | None) -> list[str]:
    if not isinstance(raw_authors, Sequence) or isinstance(
        raw_authors,
        str | bytes | bytearray,
    ):
        return []

    author_names: list[str] = []
    for raw_author in raw_authors:
        if not isinstance(raw_author, Mapping):
            continue
        raw_name = raw_author.get("name")
        if isinstance(raw_name, str):
            normalized = raw_name.strip()
            if normalized:
                author_names.append(normalized)
    return author_names


def extract_string_list(raw_values: JSONValue | None) -> list[str]:
    if not isinstance(raw_values, Sequence) or isinstance(
        raw_values,
        str | bytes | bytearray,
    ):
        return []

    values: list[str] = []
    for raw_value in raw_values:
        if isinstance(raw_value, str):
            normalized = raw_value.strip()
            if normalized:
                values.append(normalized)
    return values


def normalized_string(raw_value: JSONValue | None) -> str | None:
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    return normalized or None


def coerce_int(raw_value: JSONValue | None) -> int:
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, float):
        return int(raw_value)
    if isinstance(raw_value, str):
        try:
            return int(raw_value)
        except ValueError:
            return 0
    return 0
