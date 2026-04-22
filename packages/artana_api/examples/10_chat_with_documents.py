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
        description="Run the assistant-first workflow with one text document.",
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
        help="Raw text attached to the assistant flow.",
    )
    parser.add_argument(
        "--question",
        default="Refresh the latest PubMed evidence for MED13 and cardiomyopathy.",
        help="Question sent to the assistant after document extraction.",
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
        workflow = client.chat.ask_with_text(
            question=args.question,
            title=args.title,
            text=args.text,
            refresh_pubmed_if_needed=True,
        )

    print_heading("Workflow Runs")
    print(f"ingestion_run_id: {workflow.ingestion.run.id}")
    print(f"extraction_run_id: {workflow.extraction.run.id}")
    print(f"chat_run_id: {workflow.chat.run.id}")

    print_heading("Chat Result")
    print(f"session_id: {workflow.chat.session.id}")
    print(f"verification: {workflow.chat.result.verification.status}")
    print(f"answer: {workflow.chat.result.answer_text}")
    print(
        f"referenced_document_ids: {workflow.chat.user_message.metadata.get('document_ids')}",
    )

    if workflow.chat.result.fresh_literature is not None:
        literature = workflow.chat.result.fresh_literature
        print_heading("Fresh Literature")
        print(f"search_job_id: {literature.search_job_id}")
        print(f"query_preview: {literature.query_preview}")
        print(f"total_results: {literature.total_results}")


if __name__ == "__main__":
    main()
