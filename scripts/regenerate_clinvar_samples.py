#!/usr/bin/env python3
"""Fetch reference ClinVar API responses for schema validation."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

CLINVAR_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
CLINVAR_SUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
OUTPUT_DIR = Path("tests/fixtures/api_samples")


def fetch_json(url: str, params: dict[str, str]) -> dict:
    response = httpx.get(url, params=params, timeout=30.0)
    response.raise_for_status()
    return response.json()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    search_payload = fetch_json(
        CLINVAR_SEARCH_URL,
        {
            "db": "clinvar",
            "term": "MED13[gene]",
            "retmode": "json",
            "retmax": "20",
        },
    )
    (OUTPUT_DIR / "clinvar_search_response.json").write_text(
        json.dumps(search_payload, indent=2),
    )

    idlist = search_payload.get("esearchresult", {}).get("idlist", [])[:5]
    if not idlist:
        msg = "ClinVar search did not return any IDs"
        raise RuntimeError(msg)

    summary_payload = fetch_json(
        CLINVAR_SUMMARY_URL,
        {
            "db": "clinvar",
            "id": ",".join(idlist),
            "retmode": "json",
        },
    )
    (OUTPUT_DIR / "clinvar_variant_response.json").write_text(
        json.dumps(summary_payload, indent=2),
    )

    # Note: print is acceptable in script files
    print("Updated ClinVar fixtures:")  # noqa: T201
    print(f" - {OUTPUT_DIR / 'clinvar_search_response.json'}")  # noqa: T201
    print(f" - {OUTPUT_DIR / 'clinvar_variant_response.json'}")  # noqa: T201


if __name__ == "__main__":
    main()
