import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import replace
from uuid import uuid4

import anthropic
import httpx2
import pytest

from contexts.assistant.domain.candidate import AssessmentFailure, Candidate
from contexts.assistant.domain.exceptions import AssessmentUnavailableError, LLMUnavailableError
from contexts.assistant.domain.rubric import RUBRIC
from contexts.assistant.infrastructure.llm.claude_candidate_assessor import (
    ClaudeCandidateAssessor,
)

QUESTION = "Which of these do you recommend for hiking?"
CANDIDATE = Candidate(
    product_id=uuid4(),
    sku="BOOT-1",
    name="Trail boot",
    price_cents=8900,
    currency="EUR",
    content="SKU: BOOT-1\nName: Trail boot\nPrice: 89.00 EUR",
    retrieval_score=0.8,
)

Handler = Callable[[httpx2.Request], httpx2.Response]
AsyncHandler = Callable[[httpx2.Request], Awaitable[httpx2.Response]]


def _message(text: str, stop_reason: str = "end_turn") -> httpx2.Response:
    return httpx2.Response(
        200,
        json={
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-test",
            "content": [{"type": "text", "text": text}],
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 40, "output_tokens": 10},
        },
    )


def _verdict(meets: bool, suitable: bool) -> str:
    return json.dumps({"meets_requirements": meets, "suitable_for_use": suitable})


class Scripted:
    def __init__(self, *responses: httpx2.Response) -> None:
        self._responses = list(responses)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return self._responses.pop(0)


def _assessor(
    handler: Handler | AsyncHandler, samples: int = 3, max_concurrency: int = 10
) -> ClaudeCandidateAssessor:
    client = anthropic.AsyncAnthropic(
        api_key="test-key",
        max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return ClaudeCandidateAssessor(
        client=client,
        model="claude-test",
        timeout_s=1.0,
        max_retries=0,
        samples=samples,
        max_tokens=64,
        max_concurrency=max_concurrency,
    )


def _error(status_code: int) -> httpx2.Response:
    return httpx2.Response(
        status_code, json={"type": "error", "error": {"type": "api_error", "message": "boom"}}
    )


class TestSelfConsistency:
    @pytest.mark.parametrize(
        ("suitable_votes", "expected"),
        [((True, True, True), 1.0), ((True, True, False), 2 / 3), ((True, False, False), 1 / 3)],
    )
    async def test_a3_probability_is_the_frequency_of_yes(
        self, suitable_votes: tuple[bool, bool, bool], expected: float
    ) -> None:
        handler = Scripted(*(_message(_verdict(True, vote)) for vote in suitable_votes))

        assessment = await _assessor(handler).assess(QUESTION, CANDIDATE)

        assert assessment.answers is not None
        assert assessment.answers.suitable_for_use == pytest.approx(expected)
        assert assessment.answers.meets_requirements == 1.0

    async def test_cr2_one_invalid_sample_leaves_the_candidate_unassessed(self) -> None:
        handler = Scripted(
            _message(_verdict(True, True)),
            _message("not json"),
            _message(_verdict(True, True)),
        )

        assessment = await _assessor(handler).assess(QUESTION, CANDIDATE)

        assert assessment.answers is None
        assert assessment.failure is AssessmentFailure.INVALID_SAMPLE

    async def test_cr2_a_response_cut_by_max_tokens_is_an_invalid_sample(self) -> None:
        handler = Scripted(
            _message(_verdict(True, True)),
            _message(_verdict(True, True), stop_reason="max_tokens"),
            _message(_verdict(True, True)),
        )

        assessment = await _assessor(handler).assess(QUESTION, CANDIDATE)

        assert assessment.answers is None
        assert assessment.failure is AssessmentFailure.INVALID_SAMPLE

    async def test_a3_all_samples_invalid_means_no_assessment(self) -> None:
        handler = Scripted(*(_message('{"unexpected": 1}') for _ in range(3)))

        assessment = await _assessor(handler).assess(QUESTION, CANDIDATE)

        assert assessment.answers is None
        assert assessment.product_id == CANDIDATE.product_id

    async def test_makes_exactly_one_call_per_sample_and_reports_usage(self) -> None:
        handler = Scripted(*(_message(_verdict(True, True)) for _ in range(3)))

        assessment = await _assessor(handler).assess(QUESTION, CANDIDATE)

        assert len(handler.requests) == 3
        assert assessment.usage.api_calls == 3
        assert assessment.usage.input_tokens == 120
        assert assessment.usage.output_tokens == 30

    async def test_sends_only_this_candidate_and_the_rubric_with_a_strict_schema(self) -> None:
        handler = Scripted(*(_message(_verdict(True, True)) for _ in range(3)))

        await _assessor(handler).assess(QUESTION, CANDIDATE)

        body = json.loads(handler.requests[0].content)
        sent = json.dumps(body)
        assert QUESTION in sent
        assert "BOOT-1" in sent
        for question in RUBRIC:
            assert question.instructions in sent
        schema = body["output_config"]["format"]["schema"]
        assert schema["required"] == ["meets_requirements", "suitable_for_use"]
        assert schema["additionalProperties"] is False
        assert "temperature" not in body
        assert body["output_config"]["effort"] == "low"


class TestErrors:
    @pytest.mark.parametrize("status_code", [429, 500, 529])
    async def test_a4_transient_status_raises_llm_unavailable(self, status_code: int) -> None:
        with pytest.raises(LLMUnavailableError):
            await _assessor(Scripted(_error(status_code))).assess(QUESTION, CANDIDATE)

    async def test_a4_connection_failure_raises_llm_unavailable(self) -> None:
        def handler(_request: httpx2.Request) -> httpx2.Response:
            raise httpx2.ConnectError("refused")

        with pytest.raises(LLMUnavailableError):
            await _assessor(handler).assess(QUESTION, CANDIDATE)

    @pytest.mark.parametrize(
        ("status_code", "sdk_error"),
        [(400, anthropic.BadRequestError), (401, anthropic.AuthenticationError)],
    )
    async def test_a4_configuration_error_propagates(
        self, status_code: int, sdk_error: type[anthropic.APIStatusError]
    ) -> None:
        with pytest.raises(sdk_error):
            await _assessor(Scripted(_error(status_code))).assess(QUESTION, CANDIDATE)


class TestUsageOnFailure:
    async def test_cr4_a_failing_sample_carries_the_usage_of_the_others(self) -> None:
        handler = Scripted(
            _message(_verdict(True, True)), _message(_verdict(True, True)), _error(529)
        )

        with pytest.raises(AssessmentUnavailableError) as raised:
            await _assessor(handler).assess(QUESTION, CANDIDATE)

        assert isinstance(raised.value, LLMUnavailableError)
        assert raised.value.usage.api_calls == 3
        assert raised.value.usage.input_tokens == 80
        assert raised.value.usage.output_tokens == 20


class TestCallConcurrency:
    async def test_cr1_never_more_calls_in_flight_than_the_limit(self) -> None:
        in_flight = 0
        peak = 0

        async def handler(_request: httpx2.Request) -> httpx2.Response:
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.05)
            in_flight -= 1
            return _message(_verdict(True, True))

        assessor = _assessor(handler, max_concurrency=2)
        others = [replace(CANDIDATE, product_id=uuid4()) for _ in range(3)]

        await asyncio.gather(*(assessor.assess(QUESTION, c) for c in others))

        assert peak == 2


class TestIdentity:
    def test_reports_provider_and_model(self) -> None:
        assessor = _assessor(Scripted())

        assert (assessor.provider, assessor.model_name) == ("claude", "claude-test")
