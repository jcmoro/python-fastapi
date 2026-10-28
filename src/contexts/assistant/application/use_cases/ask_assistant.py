from collections.abc import Sequence

from contexts.assistant.application.dtos import (
    AnswerDTO,
    AskCommand,
    RecommendationSummaryDTO,
    SourceDTO,
    UsageDTO,
)
from contexts.assistant.domain.agent import (
    AgentRecommendation,
    AgentStopReason,
    AgentUnavailableError,
)
from contexts.assistant.domain.completion import INCOMPLETE_STOP_REASONS
from contexts.assistant.domain.exceptions import LLMUnavailableError
from contexts.assistant.domain.ports.catalog_agent import CatalogAgent
from contexts.assistant.domain.ports.document_search import DocumentSearch
from contexts.assistant.domain.ports.embedding_client import EmbeddingClient
from contexts.assistant.domain.ports.llm_client import LLMClient
from contexts.assistant.domain.question import Question
from contexts.assistant.domain.retrieved_document import RetrievedDocument

SYSTEM_PROMPT = (
    "You are the assistant of a product catalog. "
    "Answer the user's question concisely, using only the catalog products provided. "
    "If they do not answer the question, say so instead of guessing."
)

FALLBACK_WITH_SOURCES = (
    "The assistant is unavailable right now. "
    "These catalog products best match your question:"
)
FALLBACK_WITHOUT_SOURCES = (
    "The assistant is unavailable right now and no catalog products match your question."
)


class AskAssistant:
    def __init__(
        self,
        llm_client: LLMClient,
        embedding_client: EmbeddingClient,
        document_search: DocumentSearch,
        *,
        max_tokens: int,
        top_k: int,
        agent: CatalogAgent | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._embedding_client = embedding_client
        self._document_search = document_search
        self._max_tokens = max_tokens
        self._top_k = top_k
        self._agent = agent

    async def execute(self, command: AskCommand) -> AnswerDTO:
        question = Question.create(command.question)
        if self._agent is not None:
            return await self._ask_agent(self._agent, question.text)

        sources = await self._retrieve(question.text)

        try:
            completion = await self._llm_client.complete(
                system=SYSTEM_PROMPT,
                prompt=build_rag_prompt(question.text, sources),
                max_tokens=self._max_tokens,
            )
        except LLMUnavailableError:
            return AnswerDTO.fallback(_fallback_text(sources), sources)
        if completion.stop_reason in INCOMPLETE_STOP_REASONS:
            return AnswerDTO.fallback(
                _fallback_text(sources), sources, model_stop_reason=completion.stop_reason
            )
        return AnswerDTO.from_completion(completion, sources)

    async def _ask_agent(self, agent: CatalogAgent, question: str) -> AnswerDTO:
        try:
            result = await agent.run(question)
        except AgentUnavailableError as error:
            sources = _sources(error.sources) or await self._retrieve(question)
            return AnswerDTO.fallback(
                _fallback_text(sources), sources, recommendation=_summary(error.recommendation)
            )
        except LLMUnavailableError:
            sources = await self._retrieve(question)
            return AnswerDTO.fallback(_fallback_text(sources), sources)
        if result.stop_reason is AgentStopReason.MODEL_INCOMPLETE:
            sources = _sources(result.sources) or await self._retrieve(question)
            return AnswerDTO.fallback(
                _fallback_text(sources),
                sources,
                recommendation=_summary(result.recommendation),
                stop_reason=result.stop_reason,
                model_stop_reason=result.model_stop_reason,
            )
        return AnswerDTO(
            text=result.text,
            sources=_sources(result.sources),
            fallback_used=False,
            usage=UsageDTO(
                model=result.usage.model,
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
                latency_ms=result.usage.latency_ms,
            ),
            recommendation=_summary(result.recommendation),
            stop_reason=result.stop_reason,
        )

    async def _retrieve(self, question: str) -> tuple[SourceDTO, ...]:
        [embedding] = await self._embedding_client.embed([question])
        return _sources(await self._document_search.search(embedding, self._top_k))


def build_rag_prompt(question: str, sources: tuple[SourceDTO, ...]) -> str:
    if not sources:
        return question
    products = "\n\n".join(source.content for source in sources)
    return f"Catalog products:\n\n{products}\n\nQuestion: {question}"


def _sources(documents: Sequence[RetrievedDocument]) -> tuple[SourceDTO, ...]:
    return tuple(SourceDTO.from_retrieved(document) for document in documents)


def _summary(recommendation: AgentRecommendation | None) -> RecommendationSummaryDTO | None:
    if recommendation is None:
        return None
    return RecommendationSummaryDTO.from_agent(recommendation)


def _fallback_text(sources: tuple[SourceDTO, ...]) -> str:
    if not sources:
        return FALLBACK_WITHOUT_SOURCES
    lines = "\n".join(f"- {_single_line(source.content)}" for source in sources)
    return f"{FALLBACK_WITH_SOURCES}\n{lines}"


def _single_line(content: str) -> str:
    return content.replace("\n", " | ")
