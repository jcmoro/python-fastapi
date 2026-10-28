import json
import logging
from collections.abc import Sequence
from uuid import uuid4

import pytest
from anthropic.types import MessageParam, ToolParam
from tests.fakes.candidate_assessor import FakeCandidateAssessor
from tests.fakes.documents import FakeDocumentSearch
from tests.fakes.embedding_client import FakeEmbeddingClient

from contexts.assistant.application.use_cases.recommend_candidate import RecommendCandidate
from contexts.assistant.domain.agent import AgentStopReason
from contexts.assistant.domain.candidate import RubricAnswers
from contexts.assistant.domain.exceptions import LLMUnavailableError
from contexts.assistant.domain.retrieved_document import RetrievedDocument
from contexts.assistant.domain.selection import SelectionReason
from contexts.assistant.infrastructure.agent.anthropic_agent_model import ModelTurn, ToolCall
from contexts.assistant.infrastructure.agent.langgraph_catalog_agent import (
    LangGraphCatalogAgent,
)
from contexts.assistant.infrastructure.agent.tools import build_tools

QUESTION = "Which of these do you recommend for winter hiking?"
BOOT = RetrievedDocument(
    product_id=uuid4(),
    content="SKU: BOOT-1\nName: Winter boot\nPrice: 129.00 EUR",
    score=0.9,
    sku="BOOT-1",
    name="Winter boot",
    price_cents=12900,
    currency="EUR",
)
SANDAL = RetrievedDocument(
    product_id=uuid4(),
    content="SKU: SAND-1\nName: Summer sandal\nPrice: 39.00 EUR",
    score=0.4,
    sku="SAND-1",
    name="Summer sandal",
    price_cents=3900,
    currency="EUR",
)


def _turn(*calls: ToolCall, text: str = "") -> ModelTurn:
    content: list[dict[str, object]] = [{"type": "thinking", "thinking": "", "signature": "s"}]
    if text:
        content.append({"type": "text", "text": text})
    content += [
        {"type": "tool_use", "id": c.id, "name": c.name, "input": dict(c.input)} for c in calls
    ]
    return ModelTurn(
        assistant_content=content,
        text=text,
        tool_calls=calls,
        model="claude-test",
        input_tokens=10,
        output_tokens=5,
    )


class ScriptedModel:
    def __init__(self, turns: list[ModelTurn], rag_text: str = "RAG answer") -> None:
        self._turns = list(turns)
        self._rag_text = rag_text
        self.calls: list[tuple[list[MessageParam], bool]] = []

    @property
    def model_name(self) -> str:
        return "claude-test"

    async def respond(
        self,
        *,
        system: str,
        messages: Sequence[MessageParam],
        tools: Sequence[ToolParam] | None,
    ) -> ModelTurn:
        self.calls.append((list(messages), bool(tools)))
        if not tools:
            return _turn(text=self._rag_text)
        return self._turns.pop(0) if self._turns else _turn(_search_call(len(self.calls)))


def _search_call(n: int) -> ToolCall:
    return ToolCall(id=f"toolu_{n}", name="semantic_search", input={"query": f"boots {n}"})


def _agent(model: ScriptedModel, max_tool_calls: int = 5) -> LangGraphCatalogAgent:
    assessor = FakeCandidateAssessor(
        outcomes={
            BOOT.product_id: RubricAnswers(meets_requirements=1, suitable_for_use=1),
            SANDAL.product_id: RubricAnswers(meets_requirements=1, suitable_for_use=0),
        }
    )
    tools = build_tools(
        embedding_client=FakeEmbeddingClient(),
        document_search=FakeDocumentSearch([BOOT, SANDAL]),
        recommend_candidate=RecommendCandidate(
            assessor, top_n=10, timeout_s=5, requirements_threshold=0.5, min_score=0.5
        ),
        rag_top_k=5,
        selector_top_n=10,
    )
    return LangGraphCatalogAgent(model=model, tools=tools, max_tool_calls=max_tool_calls)


class TestStepLimit:
    async def test_b2_b12_five_tool_calls_then_rag_mode(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        model = ScriptedModel([])
        caplog.set_level(logging.INFO, logger="contexts.assistant")

        result = await _agent(model).run(QUESTION)

        assert result.stop_reason is AgentStopReason.MAX_STEPS
        assert result.usage.tool_calls == 5
        assert result.text == "RAG answer"
        rag_messages, rag_with_tools = model.calls[-1]
        assert rag_with_tools is False
        assert "BOOT-1" in str(rag_messages)
        assert any("stop_reason=max_steps" in r.getMessage() for r in caplog.records)

    async def test_b12_a_batch_that_would_pass_the_limit_is_not_executed(self) -> None:
        model = ScriptedModel([_turn(_search_call(1), _search_call(2), _search_call(3))])

        result = await _agent(model, max_tool_calls=2).run(QUESTION)

        assert result.usage.tool_calls == 0
        assert result.stop_reason is AgentStopReason.MAX_STEPS


class TestAnswered:
    async def test_b10_recommendation_comes_from_the_selection_not_the_text(self) -> None:
        model = ScriptedModel(
            [
                _turn(ToolCall(id="toolu_1", name="recommend_candidate", input={})),
                _turn(text="I recommend SAND-1."),
            ]
        )

        result = await _agent(model).run(QUESTION)

        assert result.stop_reason is AgentStopReason.ANSWERED
        assert result.text == "I recommend SAND-1."
        assert result.recommendation is not None
        assert result.recommendation.reason is SelectionReason.CHOSEN
        assert result.recommendation.sku == "BOOT-1"

    async def test_answering_without_recommending_leaves_recommendation_null(self) -> None:
        model = ScriptedModel([_turn(text="Boots keep you warm.")])

        result = await _agent(model).run(QUESTION)

        assert result.recommendation is None
        assert result.usage.tool_calls == 0
        assert result.stop_reason is AgentStopReason.ANSWERED

    async def test_tool_results_go_back_with_their_ids_after_the_assistant_blocks(self) -> None:
        model = ScriptedModel([_turn(_search_call(1)), _turn(text="done")])

        await _agent(model).run(QUESTION)

        second_messages = json.loads(json.dumps(model.calls[1][0]))
        assistant, user = second_messages[-2], second_messages[-1]
        assert assistant["role"] == "assistant"
        assert [block["type"] for block in assistant["content"]] == ["thinking", "tool_use"]
        assert user["content"][0]["tool_use_id"] == "toolu_1"

    async def test_usage_is_summed_across_steps(self) -> None:
        model = ScriptedModel([_turn(_search_call(1)), _turn(text="done")])

        result = await _agent(model).run(QUESTION)

        assert (result.usage.input_tokens, result.usage.output_tokens) == (20, 10)


class TestErrors:
    async def test_a_transient_model_error_propagates(self) -> None:
        class Failing(ScriptedModel):
            async def respond(
                self,
                *,
                system: str,
                messages: Sequence[MessageParam],
                tools: Sequence[ToolParam] | None,
            ) -> ModelTurn:
                raise LLMUnavailableError("down")

        with pytest.raises(LLMUnavailableError):
            await _agent(Failing([])).run(QUESTION)
