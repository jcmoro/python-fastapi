from abc import ABC, abstractmethod

from contexts.assistant.domain.candidate import Assessment, Candidate


class CandidateAssessor(ABC):
    @property
    @abstractmethod
    def provider(self) -> str: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    async def assess(self, question: str, candidate: Candidate) -> Assessment:
        """Assesses one candidate against the rubric; it never sees the other candidates.
        Answers are probabilities of yes in [0, 1]. Returns an ``Assessment`` with
        ``answers=None`` when the model's output cannot be used. Raises
        ``LLMUnavailableError`` only for transient failures; configuration errors propagate.
        """
