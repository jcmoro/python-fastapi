from __future__ import annotations

from dataclasses import dataclass

from contexts.assistant.domain.exceptions import InvalidQuestionError

_MAX_QUESTION_LENGTH = 1000


@dataclass(frozen=True, slots=True)
class Question:
    text: str

    def __post_init__(self) -> None:
        _validate_text(self.text)

    @classmethod
    def create(cls, text: str) -> Question:
        return cls(text=text.strip())


def _validate_text(value: str) -> None:
    stripped = value.strip()
    if not stripped:
        raise InvalidQuestionError("question must not be empty")
    if len(stripped) > _MAX_QUESTION_LENGTH:
        raise InvalidQuestionError(
            f"question must be at most {_MAX_QUESTION_LENGTH} characters"
        )
