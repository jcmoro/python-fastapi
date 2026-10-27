from collections.abc import Callable

import anthropic
import httpx2
import pytest

from contexts.assistant.domain.exceptions import LLMUnavailableError
from contexts.assistant.infrastructure.llm.anthropic_llm_client import AnthropicLLMClient

Handler = Callable[[httpx2.Request], httpx2.Response]


def _error_response(status_code: int) -> httpx2.Response:
    return httpx2.Response(
        status_code,
        json={"type": "error", "error": {"type": "api_error", "message": "boom"}},
    )


def _adapter(handler: Handler, *, client_max_retries: int = 0) -> AnthropicLLMClient:
    client = anthropic.AsyncAnthropic(
        api_key="test-key",
        max_retries=client_max_retries,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return AnthropicLLMClient(client=client, model="claude-test", timeout_s=1.0, max_retries=0)


async def _complete(adapter: AnthropicLLMClient) -> None:
    await adapter.complete(system="system", prompt="question", max_tokens=16)


class TestErrorClassification:
    @pytest.mark.parametrize("status_code", [429, 500, 529])
    async def test_transient_status_raises_llm_unavailable(self, status_code: int) -> None:
        adapter = _adapter(lambda _request: _error_response(status_code))

        with pytest.raises(LLMUnavailableError):
            await _complete(adapter)

    @pytest.mark.parametrize(
        "exception", [httpx2.ConnectError("refused"), httpx2.ReadTimeout("slow")]
    )
    async def test_transport_failure_raises_llm_unavailable(self, exception: Exception) -> None:
        def handler(_request: httpx2.Request) -> httpx2.Response:
            raise exception

        with pytest.raises(LLMUnavailableError):
            await _complete(_adapter(handler))

    @pytest.mark.parametrize(
        ("status_code", "sdk_error"),
        [
            (400, anthropic.BadRequestError),
            (401, anthropic.AuthenticationError),
            (403, anthropic.PermissionDeniedError),
            (404, anthropic.NotFoundError),
        ],
    )
    async def test_configuration_error_propagates(
        self, status_code: int, sdk_error: type[anthropic.APIStatusError]
    ) -> None:
        adapter = _adapter(lambda _request: _error_response(status_code))

        with pytest.raises(sdk_error):
            await _complete(adapter)


class TestTimeoutBound:
    async def test_timing_out_upstream_is_attempted_once(self) -> None:
        attempts: list[httpx2.Request] = []

        def handler(request: httpx2.Request) -> httpx2.Response:
            attempts.append(request)
            raise httpx2.ReadTimeout("slow")

        adapter = _adapter(handler, client_max_retries=2)

        with pytest.raises(LLMUnavailableError):
            await _complete(adapter)

        assert len(attempts) == 1
