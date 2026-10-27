import asyncio
import json
from uuid import uuid4

import anthropic
import httpx2

from contexts.assistant.application.use_cases.recommend_candidate import RecommendCandidate
from contexts.assistant.domain.candidate import Candidate
from contexts.assistant.infrastructure.llm.claude_candidate_assessor import (
    ClaudeCandidateAssessor,
)

CALL_SECONDS = 0.2


async def _slow_yes(_request: httpx2.Request) -> httpx2.Response:
    await asyncio.sleep(CALL_SECONDS)
    return httpx2.Response(
        200,
        json={
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-test",
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({"meets_requirements": True, "suitable_for_use": True}),
                }
            ],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 40, "output_tokens": 10},
        },
    )


def _candidates(count: int) -> list[Candidate]:
    return [
        Candidate(
            product_id=uuid4(),
            sku=f"SKU-{i}",
            name=f"Name {i}",
            price_cents=100,
            currency="EUR",
            content=f"SKU: SKU-{i}",
            retrieval_score=1.0 - i / 10,
        )
        for i in range(count)
    ]


async def test_cr1_slow_calls_still_assess_some_candidates_before_the_deadline() -> None:
    client = anthropic.AsyncAnthropic(
        api_key="test-key",
        max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(_slow_yes)),
    )
    assessor = ClaudeCandidateAssessor(
        client=client,
        model="claude-test",
        timeout_s=5.0,
        max_retries=0,
        samples=3,
        max_tokens=64,
        max_concurrency=3,
    )
    use_case = RecommendCandidate(
        assessor,
        top_n=10,
        timeout_s=CALL_SECONDS * 2.5,
        requirements_threshold=0.5,
        min_score=0.5,
    )

    result = await use_case.execute("Which do you recommend for hiking?", _candidates(3))

    assert result.assessed >= 1
    assert result.product_id is not None
