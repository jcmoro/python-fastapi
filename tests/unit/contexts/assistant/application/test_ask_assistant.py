from dataclasses import replace
from uuid import uuid4

import pytest
from tests.fakes.catalog_agent import FakeCatalogAgent
from tests.fakes.documents import FakeDocumentSearch
from tests.fakes.embedding_client import FakeEmbeddingClient
from tests.fakes.llm_client import FakeLLMClient

from contexts.assistant.application.dtos import (
    AnswerDTO,
    AskCommand,
    RecommendationSummaryDTO,
    SourceDTO,
    UsageDTO,
)
from contexts.assistant.application.use_cases.ask_assistant import (
    FALLBACK_WITH_SOURCES,
    FALLBACK_WITHOUT_SOURCES,
    SYSTEM_PROMPT,
    AskAssistant,
)
from contexts.assistant.domain.agent import (
    AgentRecommendation,
    AgentResult,
    AgentStopReason,
    AgentUnavailableError,
    AgentUsage,
)
from contexts.assistant.domain.completion import Completion
from contexts.assistant.domain.exceptions import InvalidQuestionError
from contexts.assistant.domain.retrieved_document import RetrievedDocument
from contexts.assistant.domain.selection import SelectionReason

QUESTION_VECTOR = [0.0, 1.0, 0.0]
WIDGET = RetrievedDocument(
    product_id=uuid4(), content="SKU: W-1\nName: Blue widget\nPrice: 19.99 EUR", score=0.91
)
GADGET = RetrievedDocument(
    product_id=uuid4(), content="SKU: G-1\nName: Gadget\nPrice: 5.00 EUR", score=0.42
)


@pytest.fixture
def embeddings() -> FakeEmbeddingClient:
    return FakeEmbeddingClient({"What is a widget?": QUESTION_VECTOR})


@pytest.fixture
def search() -> FakeDocumentSearch:
    return FakeDocumentSearch([WIDGET, GADGET])


def _use_case(
    llm_client: FakeLLMClient, embeddings: FakeEmbeddingClient, search: FakeDocumentSearch
) -> AskAssistant:
    return AskAssistant(llm_client, embeddings, search, max_tokens=256, top_k=5)


@pytest.fixture
def use_case(
    llm_client: FakeLLMClient, embeddings: FakeEmbeddingClient, search: FakeDocumentSearch
) -> AskAssistant:
    return _use_case(llm_client, embeddings, search)


class TestRetrieval:
    async def test_embeds_the_stripped_question_and_searches_top_k(
        self,
        use_case: AskAssistant,
        embeddings: FakeEmbeddingClient,
        search: FakeDocumentSearch,
    ) -> None:
        await use_case.execute(AskCommand(question="  What is a widget?  "))

        assert embeddings.calls == [["What is a widget?"]]
        assert search.calls == [(QUESTION_VECTOR, 5)]

    async def test_c7_returns_retrieved_documents_as_sources(self, use_case: AskAssistant) -> None:
        result = await use_case.execute(AskCommand(question="What is a widget?"))

        assert result.sources == (
            SourceDTO.from_retrieved(WIDGET),
            SourceDTO.from_retrieved(GADGET),
        )

    async def test_c7_puts_the_documents_and_the_question_in_the_prompt(
        self, use_case: AskAssistant, llm_client: FakeLLMClient
    ) -> None:
        await use_case.execute(AskCommand(question="What is a widget?"))

        request = llm_client.requests[0]
        assert request.prompt == (
            f"Catalog products:\n\n{WIDGET.content}\n\n{GADGET.content}\n\n"
            "Question: What is a widget?"
        )
        assert request.system == SYSTEM_PROMPT
        assert request.max_tokens == 256

    async def test_empty_index_sends_only_the_question(
        self, llm_client: FakeLLMClient, embeddings: FakeEmbeddingClient
    ) -> None:
        use_case = _use_case(llm_client, embeddings, FakeDocumentSearch())

        result = await use_case.execute(AskCommand(question="What is a widget?"))

        assert llm_client.requests[0].prompt == "What is a widget?"
        assert result.sources == ()


class TestAnswer:
    async def test_returns_completion_text_without_fallback(self, use_case: AskAssistant) -> None:
        result = await use_case.execute(AskCommand(question="What is a widget?"))

        assert isinstance(result, AnswerDTO)
        assert result.text == "An answer."
        assert result.fallback_used is False

    async def test_propagates_usage_to_dto(
        self, embeddings: FakeEmbeddingClient, search: FakeDocumentSearch
    ) -> None:
        completion = Completion(
            text="Answer.",
            model="claude-test",
            input_tokens=100,
            output_tokens=20,
            latency_ms=350,
        )
        use_case = _use_case(FakeLLMClient(completion), embeddings, search)

        result = await use_case.execute(AskCommand(question="What is a widget?"))

        assert result.usage == UsageDTO(
            model="claude-test", input_tokens=100, output_tokens=20, latency_ms=350
        )

    async def test_rejects_invalid_question_without_embedding_or_calling_llm(
        self,
        use_case: AskAssistant,
        llm_client: FakeLLMClient,
        embeddings: FakeEmbeddingClient,
    ) -> None:
        with pytest.raises(InvalidQuestionError):
            await use_case.execute(AskCommand(question="   "))

        assert embeddings.calls == []
        assert llm_client.requests == []


class TestFallback:
    async def test_c8_llm_unavailable_returns_sources_without_generation(
        self, embeddings: FakeEmbeddingClient, search: FakeDocumentSearch
    ) -> None:
        use_case = _use_case(FakeLLMClient(fail=True), embeddings, search)

        result = await use_case.execute(AskCommand(question="What is a widget?"))

        assert result.fallback_used is True
        assert result.usage is None
        assert result.sources == (
            SourceDTO.from_retrieved(WIDGET),
            SourceDTO.from_retrieved(GADGET),
        )
        assert result.text == (
            f"{FALLBACK_WITH_SOURCES}\n"
            "- SKU: W-1 | Name: Blue widget | Price: 19.99 EUR\n"
            "- SKU: G-1 | Name: Gadget | Price: 5.00 EUR"
        )

    async def test_c8_llm_unavailable_with_empty_index_returns_fixed_text(
        self, embeddings: FakeEmbeddingClient
    ) -> None:
        use_case = _use_case(FakeLLMClient(fail=True), embeddings, FakeDocumentSearch())

        result = await use_case.execute(AskCommand(question="What is a widget?"))

        assert result.fallback_used is True
        assert result.sources == ()
        assert result.text == FALLBACK_WITHOUT_SOURCES


AGENT_RESULT = AgentResult(
    text="Take the winter boot.",
    sources=(WIDGET,),
    recommendation=AgentRecommendation(
        product_id=WIDGET.product_id, sku="W-1", score=1.0, reason=SelectionReason.CHOSEN
    ),
    stop_reason=AgentStopReason.ANSWERED,
    usage=AgentUsage(
        model="claude-test", tool_calls=2, input_tokens=300, output_tokens=40, latency_ms=900
    ),
)


class TestAgentMode:
    async def test_delegates_to_the_agent_and_maps_its_result(
        self, embeddings: FakeEmbeddingClient, search: FakeDocumentSearch
    ) -> None:
        agent = FakeCatalogAgent(AGENT_RESULT)
        use_case = AskAssistant(
            FakeLLMClient(), embeddings, search, max_tokens=256, top_k=5, agent=agent
        )

        result = await use_case.execute(AskCommand(question="  Which boot for winter?  "))

        assert agent.questions == ["Which boot for winter?"]
        assert result.text == "Take the winter boot."
        assert result.sources == (SourceDTO.from_retrieved(WIDGET),)
        assert result.fallback_used is False
        assert result.usage == UsageDTO(
            model="claude-test", input_tokens=300, output_tokens=40, latency_ms=900
        )
        assert result.recommendation == RecommendationSummaryDTO(
            product_id=WIDGET.product_id, sku="W-1", score=1.0, reason=SelectionReason.CHOSEN
        )
        assert result.stop_reason is AgentStopReason.ANSWERED

    async def test_agent_unavailable_falls_back_to_retrieval_without_generation(
        self, embeddings: FakeEmbeddingClient, search: FakeDocumentSearch
    ) -> None:
        use_case = AskAssistant(
            FakeLLMClient(),
            embeddings,
            search,
            max_tokens=256,
            top_k=5,
            agent=FakeCatalogAgent(fail=True),
        )

        result = await use_case.execute(AskCommand(question="What is a widget?"))

        assert result.fallback_used is True
        assert result.usage is None
        assert result.recommendation is None
        assert result.sources == (
            SourceDTO.from_retrieved(WIDGET),
            SourceDTO.from_retrieved(GADGET),
        )

    async def test_rag_mode_has_no_recommendation_and_no_stop_reason(
        self, use_case: AskAssistant
    ) -> None:
        result = await use_case.execute(AskCommand(question="What is a widget?"))

        assert result.recommendation is None
        assert result.stop_reason is None


class TestReviewFixes:
    async def test_rb2_agent_failure_after_selection_keeps_recommendation_and_sources(
        self, embeddings: FakeEmbeddingClient, search: FakeDocumentSearch
    ) -> None:
        partial = AgentUnavailableError(
            sources=(GADGET,),
            recommendation=AGENT_RESULT.recommendation,
            usage=AGENT_RESULT.usage,
        )
        use_case = AskAssistant(
            FakeLLMClient(),
            embeddings,
            search,
            max_tokens=256,
            top_k=5,
            agent=FakeCatalogAgent(error=partial),
        )

        result = await use_case.execute(AskCommand(question="Which boot for winter?"))

        assert result.fallback_used is True
        expected = AGENT_RESULT.recommendation
        assert expected is not None
        assert result.sources == (SourceDTO.from_retrieved(GADGET),)
        assert result.recommendation == RecommendationSummaryDTO.from_agent(expected)
        assert embeddings.calls == []

    @pytest.mark.parametrize("stop_reason", ["max_tokens", "refusal"])
    async def test_rb4_rag_mode_incomplete_answer_falls_back(
        self, embeddings: FakeEmbeddingClient, search: FakeDocumentSearch, stop_reason: str
    ) -> None:
        completion = Completion(
            text="Half an ans",
            model="claude-test",
            input_tokens=10,
            output_tokens=256,
            latency_ms=5,
            stop_reason=stop_reason,
        )
        use_case = _use_case(FakeLLMClient(completion), embeddings, search)

        result = await use_case.execute(AskCommand(question="What is a widget?"))

        assert result.fallback_used is True
        assert result.model_stop_reason == stop_reason
        assert result.text.startswith(FALLBACK_WITH_SOURCES)

    async def test_rb4_agent_mode_incomplete_answer_falls_back(
        self, embeddings: FakeEmbeddingClient, search: FakeDocumentSearch
    ) -> None:
        incomplete = replace(
            AGENT_RESULT,
            text="Half an ans",
            stop_reason=AgentStopReason.MODEL_INCOMPLETE,
            model_stop_reason="max_tokens",
        )
        use_case = AskAssistant(
            FakeLLMClient(),
            embeddings,
            search,
            max_tokens=256,
            top_k=5,
            agent=FakeCatalogAgent(incomplete),
        )

        result = await use_case.execute(AskCommand(question="Which boot for winter?"))

        assert result.fallback_used is True
        assert result.stop_reason is AgentStopReason.MODEL_INCOMPLETE
        assert result.model_stop_reason == "max_tokens"
        assert result.text.startswith(FALLBACK_WITH_SOURCES)
        assert result.recommendation is not None
