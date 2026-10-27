from abc import ABC, abstractmethod


class EmbeddingClient(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Identifies the model. Vectors from different models are not comparable."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Returns exactly one embedding per text, in the same order as ``texts``. Every
        embedding has the same dimension, fixed by the configured model.
        """
