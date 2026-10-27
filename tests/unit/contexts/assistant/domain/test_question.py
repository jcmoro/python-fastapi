import pytest

from contexts.assistant.domain.exceptions import InvalidQuestionError
from contexts.assistant.domain.question import Question


class TestCreate:
    def test_strips_whitespace(self) -> None:
        question = Question.create("  What is a widget?  ")

        assert question.text == "What is a widget?"

    def test_accepts_max_length(self) -> None:
        question = Question.create("X" * 1000)

        assert len(question.text) == 1000


class TestInvariants:
    @pytest.mark.parametrize("text", ["", "   ", "\n\t"])
    def test_rejects_empty_question(self, text: str) -> None:
        with pytest.raises(InvalidQuestionError, match="empty"):
            Question.create(text)

    def test_rejects_question_too_long(self) -> None:
        with pytest.raises(InvalidQuestionError, match="1000"):
            Question.create("X" * 1001)

    def test_validates_on_direct_construction(self) -> None:
        with pytest.raises(InvalidQuestionError):
            Question(text="   ")
