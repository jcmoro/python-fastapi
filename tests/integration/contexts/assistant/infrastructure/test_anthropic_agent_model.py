import json
from collections.abc import Callable

import anthropic
import httpx2
import pytest

from contexts.assistant.domain.exceptions import LLMUnavailableError
from contexts.assistant.infrastructure.agent.anthropic_agent_model import (
    AnthropicAgentModel,
    ModelTurn,
)

Handler = Callable[[httpx2.Request], httpx2.Response]
TOOLS: list[anthropic.types.ToolParam] = [
    {
        "name": "semantic_search",
        "description": "Search.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
    }
]


def _response(content: list[dict[str, object]], stop_reason: str = "end_turn") -> httpx2.Response:
    return httpx2.Response(
        200,
        json={
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-test",
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 30, "output_tokens": 12},
        },
    )


def _error(status_code: int) -> httpx2.Response:
    return httpx2.Response(
        status_code, json={"type": "error", "error": {"type": "api_error", "message": "boom"}}
    )


class Recording:
    def __init__(self, response: httpx2.Response) -> None:
        self._response = response
        self.bodies: list[dict[str, object]] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.bodies.append(json.loads(request.content))
        return self._response


def _model(handler: Handler) -> AnthropicAgentModel:
    client = anthropic.AsyncAnthropic(
        api_key="test-key",
        max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return AnthropicAgentModel(
        client=client, model="claude-test", timeout_s=1.0, max_retries=0, max_tokens=512
    )


async def _respond(model: AnthropicAgentModel) -> ModelTurn:
    return await model.respond(
        system="system", messages=[{"role": "user", "content": "hi"}], tools=TOOLS
    )


class TestTurns:
    async def test_tool_use_turn_exposes_the_calls_and_keeps_every_block(self) -> None:
        handler = Recording(
            _response(
                [
                    {"type": "thinking", "thinking": "", "signature": "sig-1"},
                    {"type": "text", "text": "Let me search."},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "semantic_search",
                        "input": {"query": "boots"},
                    },
                ],
                stop_reason="tool_use",
            )
        )

        turn = await _respond(_model(handler))

        assert [(c.id, c.name, c.input) for c in turn.tool_calls] == [
            ("toolu_1", "semantic_search", {"query": "boots"})
        ]
        assert [block["type"] for block in turn.assistant_content] == [
            "thinking",
            "text",
            "tool_use",
        ]
        assert turn.assistant_content[0] == {
            "type": "thinking",
            "thinking": "",
            "signature": "sig-1",
        }
        assert (turn.input_tokens, turn.output_tokens, turn.model) == (30, 12, "claude-test")
        assert turn.stop_reason == "tool_use"

    async def test_final_turn_returns_the_text(self) -> None:
        turn = await _respond(_model(Recording(_response([{"type": "text", "text": "Done."}]))))

        assert turn.tool_calls == ()
        assert turn.text == "Done."

    async def test_rb4_reports_a_cut_off_turn(self) -> None:
        turn = await _respond(
            _model(Recording(_response([{"type": "text", "text": "Half"}], "max_tokens")))
        )

        assert turn.stop_reason == "max_tokens"

    async def test_sends_the_tools_and_no_sampling_parameters(self) -> None:
        handler = Recording(_response([{"type": "text", "text": "ok"}]))

        await _respond(_model(handler))

        body = handler.bodies[0]
        assert body["tools"] == TOOLS
        assert "temperature" not in body and "top_p" not in body


class TestErrors:
    @pytest.mark.parametrize("status_code", [429, 500, 529])
    async def test_b4_transient_status_raises_llm_unavailable(self, status_code: int) -> None:
        with pytest.raises(LLMUnavailableError):
            await _respond(_model(lambda _r: _error(status_code)))

    async def test_b4_connection_failure_raises_llm_unavailable(self) -> None:
        def handler(_request: httpx2.Request) -> httpx2.Response:
            raise httpx2.ConnectError("refused")

        with pytest.raises(LLMUnavailableError):
            await _respond(_model(handler))

    @pytest.mark.parametrize(
        ("status_code", "sdk_error"),
        [(400, anthropic.BadRequestError), (401, anthropic.AuthenticationError)],
    )
    async def test_b4_configuration_error_propagates(
        self, status_code: int, sdk_error: type[anthropic.APIStatusError]
    ) -> None:
        with pytest.raises(sdk_error):
            await _respond(_model(lambda _r: _error(status_code)))
