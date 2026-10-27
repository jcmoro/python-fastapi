from contexts.assistant.application.dtos import AnswerDTO, AskCommand
from contexts.assistant.domain.ports.llm_client import LLMClient
from contexts.assistant.domain.question import Question

SYSTEM_PROMPT = (
    "You are the assistant of a product catalog. "
    "Answer the user's question concisely. "
    "If you do not know the answer, say so instead of guessing."
)


class AskAssistant:
    def __init__(self, llm_client: LLMClient, max_tokens: int) -> None:
        self._llm_client = llm_client
        self._max_tokens = max_tokens

    async def execute(self, command: AskCommand) -> AnswerDTO:
        question = Question.create(command.question)
        completion = await self._llm_client.complete(
            system=SYSTEM_PROMPT,
            prompt=question.text,
            max_tokens=self._max_tokens,
        )
        return AnswerDTO.from_completion(completion)
