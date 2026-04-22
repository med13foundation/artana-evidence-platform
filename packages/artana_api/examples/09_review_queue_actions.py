from __future__ import annotations

import argparse

from _example_support import (
    add_api_key_argument,
    add_base_url_argument,
    create_client,
    exit_with_error,
    print_heading,
    require_value,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create one staged queue item from text and then promote or reject it.",
    )
    add_base_url_argument(parser)
    add_api_key_argument(parser)
    parser.add_argument(
        "--title",
        default="Proposal review note",
        help="Title recorded for the tracked document.",
    )
    parser.add_argument(
        "--text",
        default="MED13 associates with cardiomyopathy.",
        help="Raw text used to generate one staged queue item.",
    )
    parser.add_argument(
        "--decision",
        choices=("promote", "reject"),
        default="promote",
        help="Review decision to apply to the first staged proposal.",
    )
    parser.add_argument(
        "--reason",
        default="Reviewed from the SDK review-queue example.",
        help="Reason attached to the decision.",
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
            metadata={"example": "09_review_queue_actions"},
        )
        extraction = client.documents.extract(document_id=ingestion.document.id)
        queue = client.review_queue.list(document_id=ingestion.document.id)
        if not queue.items:
            exit_with_error("No staged review items were created from the document.")
        queue_item = queue.items[0]
        if args.decision == "promote":
            reviewed = client.review_queue.act(
                item_id=queue_item.id,
                action="promote",
                reason=args.reason,
                metadata={"example": "09_review_queue_actions"},
            )
            follow_up_search = client.graph.search(
                question="What is known about MED13 and cardiomyopathy?",
            )
        else:
            reviewed = client.review_queue.act(
                item_id=queue_item.id,
                action="reject",
                reason=args.reason,
                metadata={"example": "09_review_queue_actions"},
            )
            follow_up_search = None

    print_heading("Review Decision")
    print(f"item_id: {reviewed.id}")
    print(f"decision: {reviewed.status}")
    print(f"reason: {reviewed.decision_reason}")

    if follow_up_search is not None and follow_up_search.result.results:
        top_result = follow_up_search.result.results[0]
        print_heading("Graph Visibility")
        print(f"matching_relation_count: {len(top_result.matching_relation_ids)}")
        print(f"support_summary: {top_result.support_summary}")


if __name__ == "__main__":
    main()
