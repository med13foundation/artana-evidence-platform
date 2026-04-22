"""Deterministic smoke test for PubMed open-access full-text retrieval."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING

from src.infrastructure.llm.content_enrichment_full_text import (
    fetch_pubmed_open_access_full_text,
)

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject
else:
    type JSONObject = dict[str, object]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Attempt deterministic full-text retrieval for one PubMed paper "
            "and print a transparent JSON report."
        ),
    )
    parser.add_argument("--pmid", required=True, help="PubMed ID (digits).")
    parser.add_argument("--pmcid", default=None, help="Optional PMCID override.")
    parser.add_argument("--doi", default=None, help="Optional DOI override.")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=20,
        help="HTTP timeout for each endpoint call.",
    )
    parser.add_argument(
        "--output-text",
        type=Path,
        default=None,
        help="Optional output path for retrieved full text.",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=400,
        help="Number of chars to include in stdout preview.",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Exit 0 even when no full text is found.",
    )
    return parser.parse_args()


def _normalize_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _build_metadata_payload(
    *,
    pmid: str,
    pmcid: str | None,
    doi: str | None,
) -> JSONObject:
    raw_record: JSONObject = {
        "pubmed_id": pmid,
        "pmc_id": pmcid,
        "doi": doi,
    }
    return {"raw_record": raw_record}


def _build_report_payload(
    *,
    pmid: str,
    pmcid: str | None,
    doi: str | None,
    result: JSONObject,
    preview_chars: int,
) -> JSONObject:
    content_text: str | None = None
    content_text_value = result.get("content_text")
    if isinstance(content_text_value, str):
        content_text = content_text_value
    preview = content_text[:preview_chars] if content_text else None
    report: JSONObject = {
        "pmid": pmid,
        "pmcid": pmcid,
        "doi": doi,
        "found": bool(result.get("found")),
        "acquisition_method": result.get("acquisition_method"),
        "content_length_chars": result.get("content_length_chars"),
        "source_url": result.get("source_url"),
        "attempted_sources": result.get("attempted_sources"),
        "warning": result.get("warning"),
        "preview": preview,
    }
    return report


def _write_output_text(path: Path, content_text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content_text, encoding="utf-8")


def main() -> int:
    args = _parse_args()
    pmid = args.pmid.strip()
    if not pmid.isdigit():
        print(json.dumps({"error": f"Invalid PMID: {args.pmid!r}"}, indent=2))
        return 2

    pmcid = _normalize_identifier(args.pmcid)
    doi = _normalize_identifier(args.doi)
    metadata = _build_metadata_payload(
        pmid=pmid,
        pmcid=pmcid,
        doi=doi,
    )
    fetch_result = fetch_pubmed_open_access_full_text(
        metadata,
        timeout_seconds=max(args.timeout_seconds, 1),
    )
    result_payload = fetch_result.as_json()

    content_text_obj: object = result_payload.get("content_text")
    if isinstance(content_text_obj, str) and args.output_text is not None:
        _write_output_text(args.output_text, content_text_obj)

    report = _build_report_payload(
        pmid=pmid,
        pmcid=pmcid,
        doi=doi,
        result=result_payload,
        preview_chars=max(args.preview_chars, 0),
    )
    if args.output_text is not None and isinstance(content_text_obj, str):
        report["output_text"] = str(args.output_text)

    print(json.dumps(report, indent=2))
    if bool(result_payload.get("found")):
        return 0
    return 0 if args.allow_missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
