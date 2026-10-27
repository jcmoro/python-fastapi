from collections.abc import Iterator
from contextlib import contextmanager

from anthropic import APIConnectionError, APIStatusError, RateLimitError

from contexts.assistant.domain.exceptions import LLMUnavailableError

UNAVAILABLE_MESSAGE = "the language model is unavailable"


@contextmanager
def transient_errors_as_unavailable() -> Iterator[None]:
    try:
        yield
    except (APIConnectionError, RateLimitError) as exc:
        raise LLMUnavailableError(UNAVAILABLE_MESSAGE) from exc
    except APIStatusError as exc:
        if exc.status_code < 500:
            raise
        raise LLMUnavailableError(UNAVAILABLE_MESSAGE) from exc
