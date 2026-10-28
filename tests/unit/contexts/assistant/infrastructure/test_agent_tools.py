from uuid import uuid4

from tests.fakes.candidate_assessor import FakeCandidateAssessor
from tests.fakes.documents import FakeDocumentSearch
from tests.fakes.embedding_client import FakeEmbeddingClient

from contexts.assistant.application.use_cases.recommend_candidate import RecommendCandidate
from contexts.assistant.domain.candidate import RubricAnswers
from contexts.assistant.domain.retrieved_document import RetrievedDocument
from contexts.assistant.domain.selection import SelectionReason
from contexts.assistant.infrastructure.agent.tools import (
    ToolContext,
    ToolSpec,
    api_tool_definitions,
    build_tools,
    dispatch,
)

QUESTION = "Which of these do you recommend for winter hiking?"
YES = RubricAnswers(meets_requirements=1.0, suitable_for_use=1.0)
NO = RubricAnswers(meets_requirements=1.0, suitable_for_use=0.0)


def _doc(sku: str, name: str, price_cents: int, score: float) -> RetrievedDocument:
    return RetrievedDocument(
        product_id=uuid4(),
        content=f"SKU: {sku}\nName: {name}",
        score=score,
        sku=sku,
        name=name,
        price_cents=price_cents,
        currency="EUR",
    )


BOOT = _doc("BOOT-1", "Winter boot", 12900, 0.9)
SANDAL = _doc("SAND-1", "Summer sandal", 3900, 0.4)


def _tools(
    assessor: FakeCandidateAssessor, embeddings: FakeEmbeddingClient | None = None
) -> list[ToolSpec]:
    search = FakeDocumentSearch([BOOT, SANDAL], products=[BOOT])
    recommend = RecommendCandidate(
        assessor, top_n=10, timeout_s=5.0, requirements_threshold=0.5, min_score=0.5
    )
    return build_tools(
        embedding_client=embeddings or FakeEmbeddingClient(),
        document_search=search,
        recommend_candidate=recommend,
        rag_top_k=5,
        selector_top_n=10,
    )


CONTEXT = ToolContext(question=QUESTION, question_embedding=[0.0, 1.0, 0.0])


class TestSingleDefinition:
    def test_b11_api_definitions_come_from_the_tool_specs(self) -> None:
        tools = _tools(FakeCandidateAssessor(default=YES))

        definitions = api_tool_definitions(tools)

        assert [d["name"] for d in definitions] == [
            "semantic_search",
            "get_product_by_sku",
            "recommend_candidate",
        ]
        for spec, definition in zip(tools, definitions, strict=True):
            assert definition["description"] == spec.description
            assert definition["input_schema"] == spec.input_schema

    async def test_b11_dispatch_uses_the_same_specs_and_rejects_unknown_tools(self) -> None:
        tools = _tools(FakeCandidateAssessor(default=YES))

        outcome = await dispatch(tools, "delete_everything", {}, CONTEXT)

        assert outcome.is_error is True
        assert "unknown tool" in outcome.text


class TestHandlers:
    async def test_semantic_search_lists_the_hits_and_records_them(self) -> None:
        outcome = await dispatch(
            _tools(FakeCandidateAssessor()), "semantic_search", {"query": "warm boots"}, CONTEXT
        )

        assert "BOOT-1" in outcome.text and "SAND-1" in outcome.text
        assert [d.sku for d in outcome.retrieved] == ["BOOT-1", "SAND-1"]

    async def test_get_product_by_sku_finds_an_indexed_product(self) -> None:
        outcome = await dispatch(
            _tools(FakeCandidateAssessor()), "get_product_by_sku", {"sku": "BOOT-1"}, CONTEXT
        )

        assert "Winter boot" in outcome.text
        assert outcome.is_error is False

    async def test_rb3_get_product_by_sku_adds_the_product_with_its_real_score(self) -> None:
        outcome = await dispatch(
            _tools(FakeCandidateAssessor()), "get_product_by_sku", {"sku": "BOOT-1"}, CONTEXT
        )

        assert [(d.sku, d.score) for d in outcome.retrieved] == [("BOOT-1", BOOT.score)]

    async def test_rb3_recommend_candidate_reuses_the_question_embedding(self) -> None:
        embeddings = FakeEmbeddingClient()

        await dispatch(
            _tools(FakeCandidateAssessor(default=YES), embeddings),
            "recommend_candidate",
            {},
            CONTEXT,
        )

        assert embeddings.calls == []

    async def test_get_product_by_sku_reports_an_unknown_sku(self) -> None:
        outcome = await dispatch(
            _tools(FakeCandidateAssessor()), "get_product_by_sku", {"sku": "NOPE"}, CONTEXT
        )

        assert "NOPE" in outcome.text
        assert outcome.retrieved == ()

    async def test_recommend_candidate_reports_the_selection(self) -> None:
        assessor = FakeCandidateAssessor(outcomes={BOOT.product_id: YES, SANDAL.product_id: NO})

        outcome = await dispatch(_tools(assessor), "recommend_candidate", {}, CONTEXT)

        assert outcome.recommendation is not None
        assert outcome.recommendation.reason is SelectionReason.CHOSEN
        assert outcome.recommendation.sku == "BOOT-1"
        assert "BOOT-1" in outcome.text

    async def test_b1_without_a_recommendation_it_says_so_and_lists_name_sku_and_price(
        self,
    ) -> None:
        assessor = FakeCandidateAssessor(default=NO)

        outcome = await dispatch(_tools(assessor), "recommend_candidate", {}, CONTEXT)

        assert outcome.recommendation is not None
        assert outcome.recommendation.reason is SelectionReason.BELOW_THRESHOLD
        assert outcome.recommendation.sku is None
        assert "no clear recommendation" in outcome.text.lower()
        for expected in ("Winter boot", "BOOT-1", "129.00 EUR", "Summer sandal", "39.00 EUR"):
            assert expected in outcome.text

    async def test_recommend_candidate_uses_the_original_question(self) -> None:
        assessor = FakeCandidateAssessor(default=YES)

        await dispatch(_tools(assessor), "recommend_candidate", {"question": "ignored"}, CONTEXT)

        assert assessor.questions == [QUESTION, QUESTION]
