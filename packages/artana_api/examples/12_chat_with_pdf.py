from __future__ import annotations

import argparse
import base64

from _example_support import (
    add_api_key_argument,
    add_base_url_argument,
    create_client,
    print_heading,
    require_value,
)

_SYNTHETIC_PDF_BASE64 = (
    "JVBERi0xLjQKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIgPj4KZW5k"
    "b2JqCjIgMCBvYmoKPDwgL1R5cGUgL1BhZ2VzIC9LaWRzIFszIDAgUl0gL0NvdW50IDEgPj4K"
    "ZW5kb2JqCjMgMCBvYmoKPDwgL1R5cGUgL1BhZ2UgL1BhcmVudCAyIDAgUiAvTWVkaWFCb3gg"
    "WzAgMCAzMDAgMTQ0XSAvQ29udGVudHMgNCAwIFIgL1Jlc291cmNlcyA8PCAvRm9udCA8PCAv"
    "RjEgNSAwIFIgPj4gPj4gPj4KZW5kb2JqCjQgMCBvYmoKPDwgL0xlbmd0aCA2OSA+PgpzdHJl"
    "YW0KQlQKL0YxIDEyIFRmCjcyIDEwMCBUZAooTUVEMTMgYXNzb2NpYXRlcyB3aXRoIGNhcmRp"
    "b215b3BhdGh5LikgVGoKRVQKZW5kc3RyZWFtCmVuZG9iago1IDAgb2JqCjw8IC9UeXBlIC9G"
    "b250IC9TdWJ0eXBlIC9UeXBlMSAvQmFzZUZvbnQgL0hlbHZldGljYSA+PgplbmRvYmoKeHJl"
    "ZgowIDYKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAwMDA5IDAwMDAwIG4gCjAwMDAwMDAw"
    "NTggMDAwMDAgbiAKMDAwMDAwMDExNSAwMDAwMCBuIAowMDAwMDAwMjQxIDAwMDAwIG4gCjAw"
    "MDAwMDAzNTkgMDAwMDAgbiAKdHJhaWxlcgo8PCAvUm9vdCAxIDAgUiAvU2l6ZSA2ID4+CnN0"
    "YXJ0eHJlZgo0MjkKJSVFT0YK"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the assistant-first workflow with one embedded PDF.",
    )
    add_base_url_argument(parser)
    add_api_key_argument(parser)
    parser.add_argument(
        "--title",
        default="MED13 PDF evidence note",
        help="Title recorded for the tracked PDF document.",
    )
    parser.add_argument(
        "--filename",
        default="med13.pdf",
        help="Filename sent with the PDF upload helper.",
    )
    parser.add_argument(
        "--question",
        default="Refresh the latest PubMed evidence for MED13 and cardiomyopathy.",
        help="Question sent to the assistant after PDF enrichment and extraction.",
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

    pdf_bytes = base64.b64decode(_SYNTHETIC_PDF_BASE64)

    with create_client(base_url=base_url, api_key=api_key) as client:
        workflow = client.chat.ask_with_pdf(
            question=args.question,
            title=args.title,
            filename=args.filename,
            file_path=pdf_bytes,
            refresh_pubmed_if_needed=True,
        )

    print_heading("Workflow Runs")
    print(f"ingestion_run_id: {workflow.ingestion.run.id}")
    print(f"enrichment_run_id: {workflow.extraction.document.last_enrichment_run_id}")
    print(f"extraction_run_id: {workflow.extraction.run.id}")
    print(f"chat_run_id: {workflow.chat.run.id}")

    print_heading("Document")
    print(f"document_id: {workflow.ingestion.document.id}")
    print(
        f"ingestion_enrichment_status: {workflow.ingestion.document.enrichment_status}",
    )
    print(
        f"extracted_enrichment_status: {workflow.extraction.document.enrichment_status}",
    )
    print(f"proposal_count: {workflow.extraction.proposal_count}")

    print_heading("Chat Result")
    print(f"session_id: {workflow.chat.session.id}")
    print(f"verification: {workflow.chat.result.verification.status}")
    print(f"answer: {workflow.chat.result.answer_text}")

    if workflow.chat.result.fresh_literature is not None:
        literature = workflow.chat.result.fresh_literature
        print_heading("Fresh Literature")
        print(f"search_job_id: {literature.search_job_id}")
        print(f"query_preview: {literature.query_preview}")
        print(f"total_results: {literature.total_results}")


if __name__ == "__main__":
    main()
