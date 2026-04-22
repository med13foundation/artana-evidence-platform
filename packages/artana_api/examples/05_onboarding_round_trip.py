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
        description="Start onboarding and send one follow-up reply.",
    )
    add_base_url_argument(parser)
    add_api_key_argument(parser)
    parser.add_argument(
        "--research-title",
        default="MED13",
        help="Research title for onboarding.",
    )
    parser.add_argument(
        "--objective",
        default="Understand cardiomyopathy mechanisms linked to MED13.",
        help="Primary objective for the onboarding run.",
    )
    parser.add_argument(
        "--reply-text",
        default="Focus on cardiomyopathy outcomes first.",
        help="Reply used for the continuation turn.",
    )
    parser.add_argument(
        "--thread-id",
        default="thread-1",
        help="Synthetic thread id for the continuation example.",
    )
    parser.add_argument(
        "--message-id",
        default="message-1",
        help="Synthetic message id for the continuation example.",
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
        started = client.onboarding.start(
            research_title=args.research_title,
            primary_objective=args.objective,
        )
        continued = client.onboarding.reply(
            thread_id=args.thread_id,
            message_id=args.message_id,
            intent="answer",
            mode="reply",
            reply_text=args.reply_text,
        )

    print_heading("Initial Onboarding Message")
    print(f"run_id: {started.run.id}")
    print(f"message_type: {started.assistant_message.message_type}")
    print(f"summary: {started.assistant_message.summary}")
    print(f"pending_questions: {started.research_state.pending_questions}")

    print_heading("Continuation")
    print(f"run_id: {continued.run.id}")
    print(f"message_type: {continued.assistant_message.message_type}")
    print(f"summary: {continued.assistant_message.summary}")
    print(f"current_hypotheses: {continued.research_state.current_hypotheses}")


if __name__ == "__main__":
    main()
