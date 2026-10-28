from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from anthropic import AsyncAnthropic, omit
from anthropic.types import (
    ContentBlockParam,
    MessageParam,
    RedactedThinkingBlock,
    TextBlock,
    ThinkingBlock,
    ToolParam,
    ToolUseBlock,
)

from contexts.assistant.infrastructure.llm.anthropic_errors import transient_errors_as_unavailable


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    input: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ModelTurn:
    assistant_content: list[ContentBlockParam]
    text: str
    tool_calls: tuple[ToolCall, ...]
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str | None


class AnthropicAgentModel:
    def __init__(
        self,
        *,
        client: AsyncAnthropic,
        model: str,
        timeout_s: float,
        max_retries: int,
        max_tokens: int,
    ) -> None:
        self._client = client.with_options(timeout=timeout_s, max_retries=max_retries)
        self._model = model
        self._max_tokens = max_tokens

    @property
    def model_name(self) -> str:
        return self._model

    async def respond(
        self,
        *,
        system: str,
        messages: Sequence[MessageParam],
        tools: Sequence[ToolParam] | None,
    ) -> ModelTurn:
        with transient_errors_as_unavailable():
            message = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=list(messages),
                tools=list(tools) if tools else omit,
            )

        content: list[ContentBlockParam] = []
        calls: list[ToolCall] = []
        texts: list[str] = []
        for block in message.content:
            if isinstance(block, TextBlock):
                texts.append(block.text)
                content.append({"type": "text", "text": block.text})
            elif isinstance(block, ToolUseBlock):
                tool_input = block.input if isinstance(block.input, dict) else {}
                calls.append(ToolCall(id=block.id, name=block.name, input=tool_input))
                content.append(
                    {"type": "tool_use", "id": block.id, "name": block.name, "input": tool_input}
                )
            elif isinstance(block, ThinkingBlock):
                content.append(
                    {"type": "thinking", "thinking": block.thinking, "signature": block.signature}
                )
            elif isinstance(block, RedactedThinkingBlock):
                content.append({"type": "redacted_thinking", "data": block.data})

        return ModelTurn(
            assistant_content=content,
            text="".join(texts),
            tool_calls=tuple(calls),
            model=message.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            stop_reason=message.stop_reason,
        )
