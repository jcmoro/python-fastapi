from abc import ABC, abstractmethod
from uuid import UUID

from contexts.assistant.domain.product_document import EmbeddedDocument


class DocumentIndex(ABC):
    @abstractmethod
    async def content_hashes(self) -> dict[UUID, str | None]:
        """Maps every indexed ``product_id`` to its ``content_hash``. ``None`` marks a document
        that lacks catalog fields (indexed before they existed): it must be indexed again.
        """

    @abstractmethod
    async def upsert(self, documents: list[EmbeddedDocument]) -> None:
        """Inserts new documents and replaces existing ones with the same ``product_id``."""

    @abstractmethod
    async def delete(self, product_ids: list[UUID]) -> None:
        """Ids that are not indexed are ignored."""
