from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass

from anthropic.types import ToolParam

from contexts.assistant.application.dtos import CandidateDTO
from contexts.assistant.application.use_cases.recommend_candidate import RecommendCandidate
from contexts.assistant.domain.agent import AgentRecommendation
from contexts.assistant.domain.candidate import Candidate
from contexts.assistant.domain.ports.document_search import DocumentSearch
from contexts.assistant.domain.ports.embedding_client import EmbeddingClient
from contexts.assistant.domain.retrieved_document import RetrievedDocument
from contexts.assistant.domain.selection import SelectionReason


@dataclass(frozen=True, slots=True)
class ToolContext:
    question: str


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    text: str
    is_error: bool = False
    retrieved: tuple[RetrievedDocument, ...] = ()
    recommendation: AgentRecommendation | None = None


ToolHandler = Callable[[Mapping[str, object], ToolContext], Awaitable[ToolOutcome]]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, object]
    handler: ToolHandler


def api_tool_definitions(tools: Sequence[ToolSpec]) -> list[ToolParam]:
    return [
        {"name": tool.name, "description": tool.description, "input_schema": tool.input_schema}
        for tool in tools
    ]


async def dispatch(
    tools: Sequence[ToolSpec], name: str, tool_input: Mapping[str, object], context: ToolContext
) -> ToolOutcome:
    for tool in tools:
        if tool.name == name:
            return await tool.handler(tool_input, context)
    return ToolOutcome(text=f"unknown tool: {name}", is_error=True)


def build_tools(
    *,
    embedding_client: EmbeddingClient,
    document_search: DocumentSearch,
    recommend_candidate: RecommendCandidate,
    rag_top_k: int,
    selector_top_n: int,
) -> list[ToolSpec]:
    async def semantic_search(tool_input: Mapping[str, object], _: ToolContext) -> ToolOutcome:
        query = tool_input.get("query")
        if not isinstance(query, str) or not query.strip():
            return ToolOutcome(text="semantic_search needs a non-empty 'query'", is_error=True)
        [embedding] = await embedding_client.embed([query])
        hits = await document_search.search(embedding, rag_top_k)
        if not hits:
            return ToolOutcome(text="No catalog products match.")
        return ToolOutcome(text="\n".join(_line(hit) for hit in hits), retrieved=tuple(hits))

    async def get_product_by_sku(tool_input: Mapping[str, object], _: ToolContext) -> ToolOutcome:
        sku = tool_input.get("sku")
        if not isinstance(sku, str) or not sku.strip():
            return ToolOutcome(text="get_product_by_sku needs a non-empty 'sku'", is_error=True)
        product = await document_search.find_by_sku(sku.strip())
        if product is None:
            return ToolOutcome(text=f"No catalog product has SKU {sku.strip()}.")
        return ToolOutcome(text=product.content)

    async def recommend(_: Mapping[str, object], context: ToolContext) -> ToolOutcome:
        [embedding] = await embedding_client.embed([context.question])
        hits = await document_search.search(embedding, selector_top_n)
        candidates = [candidate for hit in hits if (candidate := _candidate(hit)) is not None]
        result = await recommend_candidate.execute(context.question, candidates)
        recommendation = AgentRecommendation(
            product_id=result.product_id, sku=result.sku, score=result.score, reason=result.reason
        )
        if result.reason is SelectionReason.CHOSEN:
            chosen = next(c for c in result.candidates if c.product_id == result.product_id)
            text = f"Recommended: {_summary(chosen)}."
        else:
            listed = "\n".join(f"- {_summary(c)}" for c in result.candidates)
            text = f"No clear recommendation ({result.reason.value}). Candidates:\n{listed}"
        return ToolOutcome(text=text, retrieved=tuple(hits), recommendation=recommendation)

    return [
        ToolSpec(
            name="semantic_search",
            description="Search the product catalog by meaning. Returns the closest products.",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "What to look for."}},
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=semantic_search,
        ),
        ToolSpec(
            name="get_product_by_sku",
            description="Get one catalog product by its exact SKU.",
            input_schema={
                "type": "object",
                "properties": {"sku": {"type": "string", "description": "Exact product SKU."}},
                "required": ["sku"],
                "additionalProperties": False,
            },
            handler=get_product_by_sku,
        ),
        ToolSpec(
            name="recommend_candidate",
            description=(
                "Recommend one product for the user's question, or report that there is no "
                "clear recommendation. The choice is made by rules, not by you: report it as is."
            ),
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=recommend,
        ),
    ]


def _candidate(hit: RetrievedDocument) -> Candidate | None:
    if hit.sku is None or hit.name is None or hit.price_cents is None or hit.currency is None:
        return None
    return Candidate(
        product_id=hit.product_id,
        sku=hit.sku,
        name=hit.name,
        price_cents=hit.price_cents,
        currency=hit.currency,
        content=hit.content,
        retrieval_score=hit.score,
    )


def _line(hit: RetrievedDocument) -> str:
    return "- " + hit.content.replace("\n", " | ")


def _summary(candidate: CandidateDTO) -> str:
    price = _price(candidate.price_cents, candidate.currency)
    return f"{candidate.name} | SKU {candidate.sku} | {price}"


def _price(price_cents: int, currency: str) -> str:
    units, cents = divmod(price_cents, 100)
    return f"{units}.{cents:02d} {currency}"
