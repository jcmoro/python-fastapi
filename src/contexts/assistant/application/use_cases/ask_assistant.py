from contexts.assistant.application.dtos import AnswerDTO, AskCommand, SourceDTO
from contexts.assistant.domain.exceptions import LLMUnavailableError
from contexts.assistant.domain.ports.document_search import DocumentSearch
from contexts.assistant.domain.ports.embedding_client import EmbeddingClient
from contexts.assistant.domain.ports.llm_client import LLMClient
from contexts.assistant.domain.question import Question

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
        max_tokens: int,
        top_k: int,
    ) -> None:
        self._llm_client = llm_client
        self._embedding_client = embedding_client
        self._document_search = document_search
        self._max_tokens = max_tokens
        self._top_k = top_k

    async def execute(self, command: AskCommand) -> AnswerDTO:
        question = Question.create(command.question)
        [embedding] = await self._embedding_client.embed([question.text])
        documents = await self._document_search.search(embedding, self._top_k)
        sources = tuple(SourceDTO.from_retrieved(document) for document in documents)

        try:
            completion = await self._llm_client.complete(
                system=SYSTEM_PROMPT,
                prompt=_build_prompt(question.text, sources),
                max_tokens=self._max_tokens,
            )
        except LLMUnavailableError:
            return AnswerDTO.fallback(_fallback_text(sources), sources)
        return AnswerDTO.from_completion(completion, sources)


def _build_prompt(question: str, sources: tuple[SourceDTO, ...]) -> str:
    if not sources:
        return question
    products = "\n\n".join(source.content for source in sources)
    return f"Catalog products:\n\n{products}\n\nQuestion: {question}"


def _fallback_text(sources: tuple[SourceDTO, ...]) -> str:
    if not sources:
        return FALLBACK_WITHOUT_SOURCES
    lines = "\n".join(f"- {_single_line(source.content)}" for source in sources)
    return f"{FALLBACK_WITH_SOURCES}\n{lines}"


def _single_line(content: str) -> str:
    return content.replace("\n", " | ")
