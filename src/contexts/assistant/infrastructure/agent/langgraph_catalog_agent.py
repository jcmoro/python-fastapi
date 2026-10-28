import logging
import time
from collections.abc import Sequence
from typing import Protocol, TypedDict

from anthropic.types import MessageParam, ToolParam, ToolResultBlockParam
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from contexts.assistant.application.dtos import SourceDTO
from contexts.assistant.application.use_cases.ask_assistant import SYSTEM_PROMPT, build_rag_prompt
from contexts.assistant.domain.agent import (
    AgentRecommendation,
    AgentResult,
    AgentStopReason,
    AgentUnavailableError,
    AgentUsage,
)
from contexts.assistant.domain.completion import INCOMPLETE_STOP_REASONS
from contexts.assistant.domain.exceptions import LLMUnavailableError
from contexts.assistant.domain.ports.catalog_agent import CatalogAgent
from contexts.assistant.domain.ports.embedding_client import EmbeddingClient
from contexts.assistant.domain.retrieved_document import RetrievedDocument
from contexts.assistant.infrastructure.agent.anthropic_agent_model import ModelTurn, ToolCall
from contexts.assistant.infrastructure.agent.tools import (
    ToolContext,
    ToolSpec,
    api_tool_definitions,
    dispatch,
)

logger = logging.getLogger(__name__)

AGENT_SYSTEM_PROMPT = (
    "You are the assistant of a product catalog. Use the tools to look products up. "
    "When the user asks which product to choose for a use, call recommend_candidate and "
    "report its result as given: never pick a product yourself. If it reports no clear "
    "recommendation, say so and list the candidates with name, SKU and price. "
    "Answer concisely."
)

ROUTE_TOOLS = "tools"
ROUTE_RAG = "rag_answer"


class AgentModel(Protocol):
    @property
    def model_name(self) -> str: ...

    async def respond(
        self,
        *,
        system: str,
        messages: Sequence[MessageParam],
        tools: Sequence[ToolParam] | None,
    ) -> ModelTurn: ...


class _State(TypedDict):
    question: str
    question_embedding: list[float]
    messages: list[MessageParam]
    pending: list[ToolCall]
    tool_calls: int
    retrieved: list[RetrievedDocument]
    recommendation: AgentRecommendation | None
    text: str
    stop_reason: AgentStopReason | None
    model_stop_reason: str | None
    model: str
    input_tokens: int
    output_tokens: int


class _ModelFailedError(Exception):
    def __init__(self, state: _State) -> None:
        super().__init__("the language model is unavailable")
        self.state = state


class LangGraphCatalogAgent(CatalogAgent):
    def __init__(
        self,
        *,
        model: AgentModel,
        tools: Sequence[ToolSpec],
        embedding_client: EmbeddingClient,
        max_tool_calls: int,
    ) -> None:
        self._model = model
        self._tools = list(tools)
        self._embedding_client = embedding_client
        self._definitions = api_tool_definitions(self._tools)
        self._max_tool_calls = max_tool_calls
        self._graph = self._build()

    async def run(self, question: str) -> AgentResult:
        started = time.perf_counter()
        [embedding] = await self._embedding_client.embed([question])
        initial: _State = {
            "question": question,
            "question_embedding": embedding,
            "messages": [{"role": "user", "content": question}],
            "pending": [],
            "tool_calls": 0,
            "retrieved": [],
            "recommendation": None,
            "text": "",
            "stop_reason": None,
            "model_stop_reason": None,
            "model": self._model.model_name,
            "input_tokens": 0,
            "output_tokens": 0,
        }
        try:
            final = await self._graph.ainvoke(
                initial, config={"recursion_limit": 2 * self._max_tool_calls + 6}
            )
        except _ModelFailedError as failure:
            partial = failure.state
            error = AgentUnavailableError(
                sources=tuple(partial["retrieved"]),
                recommendation=partial["recommendation"],
                usage=_usage(
                    model=partial["model"],
                    tool_calls=partial["tool_calls"],
                    input_tokens=partial["input_tokens"],
                    output_tokens=partial["output_tokens"],
                    started=started,
                ),
            )
            _log("unavailable", None, error.usage, error.recommendation)
            raise error from failure.__cause__
        result = AgentResult(
            text=final["text"],
            sources=tuple(final["retrieved"]),
            recommendation=final["recommendation"],
            stop_reason=final["stop_reason"],
            usage=_usage(
                model=final["model"],
                tool_calls=final["tool_calls"],
                input_tokens=final["input_tokens"],
                output_tokens=final["output_tokens"],
                started=started,
            ),
            model_stop_reason=final["model_stop_reason"],
        )
        _log(
            result.stop_reason.value,
            result.model_stop_reason,
            result.usage,
            result.recommendation,
        )
        return result

    def _build(self) -> CompiledStateGraph[_State, None, _State, _State]:
        graph = StateGraph(_State)
        graph.add_node("model", self._model_node)
        graph.add_node(ROUTE_TOOLS, self._tools_node)
        graph.add_node(ROUTE_RAG, self._rag_node)
        graph.add_edge(START, "model")
        graph.add_conditional_edges(
            "model", self._route, {ROUTE_TOOLS: ROUTE_TOOLS, ROUTE_RAG: ROUTE_RAG, END: END}
        )
        graph.add_edge(ROUTE_TOOLS, "model")
        graph.add_edge(ROUTE_RAG, END)
        return graph.compile()

    def _route(self, state: _State) -> str:
        if not state["pending"]:
            return END
        if state["tool_calls"] + len(state["pending"]) > self._max_tool_calls:
            return ROUTE_RAG
        return ROUTE_TOOLS

    async def _respond(
        self,
        state: _State,
        *,
        system: str,
        messages: Sequence[MessageParam],
        tools: Sequence[ToolParam] | None,
    ) -> ModelTurn:
        try:
            return await self._model.respond(system=system, messages=messages, tools=tools)
        except LLMUnavailableError as error:
            raise _ModelFailedError(state) from error

    async def _model_node(self, state: _State) -> dict[str, object]:
        turn = await self._respond(
            state, system=AGENT_SYSTEM_PROMPT, messages=state["messages"], tools=self._definitions
        )
        incomplete = turn.stop_reason in INCOMPLETE_STOP_REASONS
        assistant: MessageParam = {"role": "assistant", "content": turn.assistant_content}
        update: dict[str, object] = {
            "messages": [*state["messages"], assistant],
            "pending": [] if incomplete else list(turn.tool_calls),
            "model": turn.model,
            "input_tokens": state["input_tokens"] + turn.input_tokens,
            "output_tokens": state["output_tokens"] + turn.output_tokens,
        }
        if incomplete:
            update["text"] = turn.text
            update["stop_reason"] = AgentStopReason.MODEL_INCOMPLETE
            update["model_stop_reason"] = turn.stop_reason
        elif not turn.tool_calls:
            update["text"] = turn.text
            update["stop_reason"] = AgentStopReason.ANSWERED
        return update

    async def _tools_node(self, state: _State) -> dict[str, object]:
        context = ToolContext(
            question=state["question"], question_embedding=state["question_embedding"]
        )
        retrieved = list(state["retrieved"])
        recommendation = state["recommendation"]
        results: list[ToolResultBlockParam] = []
        for call in state["pending"]:
            outcome = await dispatch(self._tools, call.name, call.input, context)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": outcome.text,
                    "is_error": outcome.is_error,
                }
            )
            known = {document.product_id for document in retrieved}
            retrieved += [d for d in outcome.retrieved if d.product_id not in known]
            if outcome.recommendation is not None:
                recommendation = outcome.recommendation
        tool_message: MessageParam = {"role": "user", "content": results}
        return {
            "messages": [*state["messages"], tool_message],
            "pending": [],
            "tool_calls": state["tool_calls"] + len(state["pending"]),
            "retrieved": retrieved,
            "recommendation": recommendation,
        }

    async def _rag_node(self, state: _State) -> dict[str, object]:
        sources = tuple(SourceDTO.from_retrieved(document) for document in state["retrieved"])
        turn = await self._respond(
            state,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_rag_prompt(state["question"], sources)}],
            tools=None,
        )
        incomplete = turn.stop_reason in INCOMPLETE_STOP_REASONS
        return {
            "text": turn.text,
            "stop_reason": (
                AgentStopReason.MODEL_INCOMPLETE if incomplete else AgentStopReason.MAX_STEPS
            ),
            "model_stop_reason": turn.stop_reason if incomplete else None,
            "pending": [],
            "model": turn.model,
            "input_tokens": state["input_tokens"] + turn.input_tokens,
            "output_tokens": state["output_tokens"] + turn.output_tokens,
        }


def _usage(
    *, model: str, tool_calls: int, input_tokens: int, output_tokens: int, started: float
) -> AgentUsage:
    return AgentUsage(
        model=model,
        tool_calls=tool_calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=round((time.perf_counter() - started) * 1000),
    )


def _log(
    stop_reason: str,
    model_stop_reason: str | None,
    usage: AgentUsage,
    recommendation: AgentRecommendation | None,
) -> None:
    logger.info(
        "agent_run stop_reason=%s model_stop_reason=%s tool_calls=%d model=%s input_tokens=%d "
        "output_tokens=%d latency_ms=%d recommendation_reason=%s product_id=%s",
        stop_reason,
        model_stop_reason,
        usage.tool_calls,
        usage.model,
        usage.input_tokens,
        usage.output_tokens,
        usage.latency_ms,
        recommendation.reason.value if recommendation is not None else None,
        recommendation.product_id if recommendation is not None else None,
    )
