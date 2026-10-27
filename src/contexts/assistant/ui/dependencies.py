from functools import lru_cache
from typing import Annotated

from anthropic import AsyncAnthropic
from fastapi import Depends

from contexts.assistant.application.use_cases.ask_assistant import AskAssistant
from contexts.assistant.domain.ports.llm_client import LLMClient
from contexts.assistant.infrastructure.llm.anthropic_llm_client import AnthropicLLMClient
from shared.infrastructure.settings import get_settings


@lru_cache
def get_llm_client() -> LLMClient:
    settings = get_settings()
    api_key = settings.anthropic_api_key
    return AnthropicLLMClient(
        client=AsyncAnthropic(api_key=api_key.get_secret_value() if api_key else None),
        model=settings.llm_model,
        timeout_s=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
    )


def get_ask_assistant_use_case(
    llm_client: Annotated[LLMClient, Depends(get_llm_client)],
) -> AskAssistant:
    return AskAssistant(llm_client, max_tokens=get_settings().llm_max_tokens)
