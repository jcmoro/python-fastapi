import pytest
from tests.unit.contexts.assistant.application.conftest import FakeLLMClient

from contexts.assistant.application.dtos import AnswerDTO, AskCommand, UsageDTO
from contexts.assistant.application.use_cases.ask_assistant import SYSTEM_PROMPT, AskAssistant
from contexts.assistant.domain.completion import Completion
from contexts.assistant.domain.exceptions import InvalidQuestionError, LLMUnavailableError


@pytest.fixture
def use_case(llm_client: FakeLLMClient) -> AskAssistant:
    return AskAssistant(llm_client, max_tokens=256)


class TestExecute:
    async def test_returns_completion_text(self, use_case: AskAssistant) -> None:
        result = await use_case.execute(AskCommand(question="What is a widget?"))

        assert isinstance(result, AnswerDTO)
        assert result.text == "An answer."

    async def test_propagates_usage_to_dto(self) -> None:
        completion = Completion(
            text="Answer.",
            model="claude-test",
            input_tokens=100,
            output_tokens=20,
            latency_ms=350,
        )
        use_case = AskAssistant(FakeLLMClient(completion), max_tokens=256)

        result = await use_case.execute(AskCommand(question="What is a widget?"))

        assert result.usage == UsageDTO(
            model="claude-test", input_tokens=100, output_tokens=20, latency_ms=350
        )

    async def test_sends_stripped_question_with_system_prompt_and_max_tokens(
        self, use_case: AskAssistant, llm_client: FakeLLMClient
    ) -> None:
        await use_case.execute(AskCommand(question="  What is a widget?  "))

        assert len(llm_client.requests) == 1
        request = llm_client.requests[0]
        assert request.prompt == "What is a widget?"
        assert request.system == SYSTEM_PROMPT
        assert request.max_tokens == 256

    async def test_rejects_invalid_question_without_calling_llm(
        self, use_case: AskAssistant, llm_client: FakeLLMClient
    ) -> None:
        with pytest.raises(InvalidQuestionError):
            await use_case.execute(AskCommand(question="   "))

        assert llm_client.requests == []

    async def test_propagates_llm_unavailable(self) -> None:
        use_case = AskAssistant(FakeLLMClient(fail=True), max_tokens=256)

        with pytest.raises(LLMUnavailableError):
            await use_case.execute(AskCommand(question="What is a widget?"))
