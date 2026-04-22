"""Regression tests for the upstream Artana LiteLLM adapter behavior."""

from __future__ import annotations

import pytest
from artana.events import ChatMessage
from artana.ports.model import LiteLLMAdapter
from artana.ports.model_types import ModelCallOptions, ModelRequest
from pydantic import BaseModel


class _Decision(BaseModel):
    decision: str


@pytest.mark.asyncio
async def test_artana_adapter_allows_tool_only_chat_turns() -> None:
    async def completion_fn(
        *,
        model: str,
        messages: list[dict[str, object]],
        response_format: type[BaseModel],
        tools: list[dict[str, object]] | None = None,
    ) -> object:
        del model, messages, response_format, tools
        return {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_chat_only_1",
                                "type": "function",
                                "function": {
                                    "name": "lookup_weather",
                                    "arguments": '{"city":"SF"}',
                                },
                            },
                        ],
                    },
                },
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            "_response_cost": 0.001,
        }

    adapter = LiteLLMAdapter(
        completion_fn=completion_fn,
        timeout_seconds=1.0,
        max_retries=0,
    )
    request = ModelRequest(
        run_id="run_model_chat_tool_only",
        model="gpt-4o-mini",
        prompt="hello",
        messages=(ChatMessage(role="user", content="hello"),),
        output_schema=_Decision,
        allowed_tools=(),
    )

    result = await adapter.complete(request)
    assert result.output.model_dump() == {}
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "lookup_weather"
    assert result.tool_calls[0].tool_call_id == "call_chat_only_1"


@pytest.mark.asyncio
async def test_artana_adapter_allows_tool_only_responses_turns() -> None:
    async def completion_fn(
        *,
        model: str,
        messages: list[dict[str, object]],
        response_format: type[BaseModel],
        tools: list[dict[str, object]] | None = None,
    ) -> object:
        del model, messages, response_format, tools
        raise AssertionError("chat completion should not run for this test")

    async def responses_fn(
        *,
        input: str | list[dict[str, object]],  # noqa: A002
        model: str,
        previous_response_id: str | None = None,
        reasoning: dict[str, object] | None = None,
        text: dict[str, object] | None = None,
        text_format: type[BaseModel] | dict[str, object] | None = None,
        tools: list[dict[str, object]] | None = None,
    ) -> object:
        del input, model, previous_response_id, reasoning, text, text_format, tools
        return {
            "id": "resp_tool_only_1",
            "output": [
                {
                    "type": "function_call",
                    "name": "lookup_weather",
                    "arguments": '{"city":"SF"}',
                    "call_id": "call_resp_only_1",
                },
            ],
            "usage": {"input_tokens": 3, "output_tokens": 2},
            "_response_cost": 0.001,
        }

    adapter = LiteLLMAdapter(
        completion_fn=completion_fn,
        responses_fn=responses_fn,
        timeout_seconds=1.0,
        max_retries=0,
    )
    request = ModelRequest(
        run_id="run_model_responses_tool_only",
        model="openai/gpt-5.4",
        prompt="hello",
        messages=(ChatMessage(role="user", content="hello"),),
        output_schema=_Decision,
        allowed_tools=(),
        model_options=ModelCallOptions(api_mode="responses"),
    )

    result = await adapter.complete(request)
    assert result.output.model_dump() == {}
    assert result.api_mode_used == "responses"
    assert result.response_id == "resp_tool_only_1"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "lookup_weather"
    assert result.tool_calls[0].tool_call_id == "call_resp_only_1"
