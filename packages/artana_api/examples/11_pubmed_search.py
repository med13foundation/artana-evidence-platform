from __future__ import annotations

import argparse

from _example_support import (
    add_api_key_argument,
    add_base_url_argument,
    create_client,
    print_heading,
    require_value,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one explicit PubMed search and then fetch the saved job.",
    )
    add_base_url_argument(parser)
    add_api_key_argument(parser)
    parser.add_argument(
        "--gene-symbol",
        default="MED13",
        help="Gene symbol used to seed the PubMed query.",
    )
    parser.add_argument(
        "--search-term",
        default="MED13 cardiomyopathy",
        help="Primary PubMed search term.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=25,
        help="Maximum number of PubMed results to request.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    base_url = require_value(
        args.base_url,
        env_name="ARTANA_API_BASE_URL",
        help_text="This example needs a reachable Artana API URL.",
    )
    api_key = require_value(
        args.api_key,
        env_name="ARTANA_API_KEY",
        help_text="Run the bootstrap example first if you do not have an API key.",
    )

    with create_client(base_url=base_url, api_key=api_key) as client:
        created_job = client.pubmed.search(
            gene_symbol=args.gene_symbol,
            search_term=args.search_term,
            max_results=args.max_results,
        )
        fetched_job = client.pubmed.get_job(job_id=created_job.id)

    print_heading("Created Search Job")
    print(f"job_id: {created_job.id}")
    print(f"query_preview: {created_job.query_preview}")
    print(f"total_results: {created_job.total_results}")

    print_heading("Fetched Search Job")
    print(f"job_id: {fetched_job.id}")
    print(f"status: {fetched_job.status}")
    preview_records = fetched_job.result_metadata.get("preview_records", [])
    if isinstance(preview_records, list) and preview_records:
        first_record = preview_records[0]
        if isinstance(first_record, dict):
            print(f"first_preview_title: {first_record.get('title')}")


if __name__ == "__main__":
    main()
