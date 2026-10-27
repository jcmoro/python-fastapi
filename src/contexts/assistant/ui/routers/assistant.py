from typing import Annotated

from fastapi import APIRouter, Depends, status

from contexts.assistant.application.dtos import AskCommand
from contexts.assistant.application.use_cases.ask_assistant import AskAssistant
from contexts.assistant.ui.dependencies import get_ask_assistant_use_case
from contexts.assistant.ui.schemas import AnswerResponse, AskRequest

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post(
    "/ask",
    response_model=AnswerResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask the assistant",
    description="Answers a natural-language question using the configured LLM.",
    responses={
        422: {"description": "Invalid question."},
        503: {"description": "The language model is unavailable."},
    },
)
async def ask_endpoint(
    body: AskRequest,
    use_case: Annotated[AskAssistant, Depends(get_ask_assistant_use_case)],
) -> AnswerResponse:
    dto = await use_case.execute(AskCommand(question=body.question))
    return AnswerResponse.from_dto(dto)
