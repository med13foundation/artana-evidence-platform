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
        description="Submit a text document, extract staged facts, and list the review queue.",
    )
    add_base_url_argument(parser)
    add_api_key_argument(parser)
    parser.add_argument(
        "--title",
        default="MED13 evidence note",
        help="Title recorded for the tracked document.",
    )
    parser.add_argument(
        "--text",
        default="MED13 associates with cardiomyopathy.",
        help="Raw text that will be stored and extracted.",
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
        ingestion = client.documents.submit_text(
            title=args.title,
            text=args.text,
            metadata={"example": "08_document_ingestion_and_extraction"},
        )
        extraction = client.documents.extract(document_id=ingestion.document.id)
        queue = client.review_queue.list(document_id=ingestion.document.id)

    print_heading("Document")
    print(f"document_id: {ingestion.document.id}")
    print(f"source_type: {ingestion.document.source_type}")
    print(f"ingestion_run_id: {ingestion.run.id}")

    print_heading("Extraction")
    print(f"extraction_run_id: {extraction.run.id}")
    print(f"proposal_count: {extraction.proposal_count}")
    print(f"review_item_count: {extraction.review_item_count}")
    print(f"skipped_candidates: {len(extraction.skipped_candidates)}")

    print_heading("Review Queue")
    print(f"total: {queue.total}")
    if queue.items:
        item = queue.items[0]
        print(f"item_id: {item.id}")
        print(f"item_type: {item.item_type}")
        print(f"kind: {item.kind}")
        print(f"status: {item.status}")
        print(f"summary: {item.summary}")


if __name__ == "__main__":
    main()
