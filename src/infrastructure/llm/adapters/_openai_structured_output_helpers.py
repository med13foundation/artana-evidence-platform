"""Shared helpers for OpenAI structured-output request/response handling."""

from __future__ import annotations


def should_use_responses_api(openai_model: str) -> bool:
    """Return whether this model should use the Responses API path."""
    normalized_model = openai_model.strip().lower()
    return normalized_model.startswith(("gpt-5", "o1", "o3", "o4"))


def build_chat_completions_payload(
    *,
    openai_model: str,
    prompt: str,
    schema_name: str,
    schema_payload: dict[str, object],
) -> dict[str, object]:
    """Build a strict JSON-schema chat-completions request payload."""
    return {
        "model": openai_model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema_payload,
                "strict": True,
            },
        },
    }


def build_responses_payload(
    *,
    openai_model: str,
    prompt: str,
    schema_name: str,
    schema_payload: dict[str, object],
) -> dict[str, object]:
    """Build a strict JSON-schema responses request payload."""
    return {
        "model": openai_model,
        "input": prompt,
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema_payload,
                "strict": True,
            },
        },
    }


def extract_responses_output_text(body: dict[str, object]) -> str:
    """Extract structured-output text from a raw OpenAI Responses payload."""
    output_text = body.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output_items = body.get("output")
    collected_fragments = (
        [
            fragment
            for item in output_items
            for fragment in _extract_text_from_responses_output_item(item)
        ]
        if isinstance(output_items, list)
        else []
    )
    joined_output = "".join(collected_fragments).strip()
    if joined_output:
        return joined_output

    msg = "OpenAI responses payload did not include structured output text."
    raise ValueError(msg)


def _extract_text_from_responses_output_item(item: object) -> list[str]:
    if not isinstance(item, dict):
        return []
    content_items = item.get("content")
    if not isinstance(content_items, list):
        return []
    return [
        fragment
        for fragment in (
            _extract_text_from_responses_content_item(content_item)
            for content_item in content_items
        )
        if fragment is not None
    ]


def _extract_text_from_responses_content_item(content_item: object) -> str | None:
    if not isinstance(content_item, dict):
        return None
    if content_item.get("type") not in {"output_text", "text"}:
        return None
    text_payload = content_item.get("text")
    if isinstance(text_payload, str):
        normalized = text_payload.strip()
        return normalized or None
    if isinstance(text_payload, dict):
        for key in ("value", "text"):
            nested_text = text_payload.get(key)
            if isinstance(nested_text, str):
                normalized = nested_text.strip()
                if normalized:
                    return normalized
    return None


__all__ = [
    "build_chat_completions_payload",
    "build_responses_payload",
    "extract_responses_output_text",
    "should_use_responses_api",
]
