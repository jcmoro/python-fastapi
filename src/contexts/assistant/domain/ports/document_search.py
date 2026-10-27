from abc import ABC, abstractmethod

from contexts.assistant.domain.retrieved_document import RetrievedDocument


class DocumentSearch(ABC):
    @abstractmethod
    async def search(self, embedding: list[float], k: int) -> list[RetrievedDocument]:
        """Returns at most ``k`` documents, most similar first. ``score`` is the cosine
        similarity (higher is closer). An empty index returns an empty list.
        """
