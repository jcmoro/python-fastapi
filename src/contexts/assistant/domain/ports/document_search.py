from abc import ABC, abstractmethod

from contexts.assistant.domain.retrieved_document import RetrievedDocument


class DocumentSearch(ABC):
    @abstractmethod
    async def search(self, embedding: list[float], k: int) -> list[RetrievedDocument]:
        """Returns at most ``k`` documents, most similar first. ``score`` is the cosine
        similarity (higher is closer). An empty index returns an empty list.
        """

    @abstractmethod
    async def find_by_sku(self, sku: str, embedding: list[float]) -> RetrievedDocument | None:
        """Exact SKU match. ``score`` is the cosine similarity to ``embedding``, as in ``search``.
        ``None`` if the SKU is not indexed or its catalog fields are missing.
        """
