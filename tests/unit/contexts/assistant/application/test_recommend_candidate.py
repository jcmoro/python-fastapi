import asyncio
import logging
import random
import time
from uuid import uuid4

import pytest
from tests.fakes.candidate_assessor import FakeCandidateAssessor

from contexts.assistant.application.use_cases.recommend_candidate import RecommendCandidate
from contexts.assistant.domain.candidate import AssessmentUsage, Candidate, RubricAnswers
from contexts.assistant.domain.exceptions import AssessmentUnavailableError, LLMUnavailableError
from contexts.assistant.domain.selection import SelectionReason

QUESTION = "Which of these do you recommend for hiking?"
YES = RubricAnswers(meets_requirements=1.0, suitable_for_use=1.0)
WEAK = RubricAnswers(meets_requirements=1.0, suitable_for_use=0.67)


def _candidates(count: int) -> list[Candidate]:
    return [
        Candidate(
            product_id=uuid4(),
            sku=f"SECRET-SKU-{i}",
            name=f"Secret name {i}",
            price_cents=1000 + i,
            currency="EUR",
            content=f"SKU: SECRET-SKU-{i}",
            retrieval_score=round(1.0 - i / 100, 2),
        )
        for i in range(count)
    ]


def _use_case(
    assessor: FakeCandidateAssessor, top_n: int = 10, timeout_s: float = 5.0
) -> RecommendCandidate:
    return RecommendCandidate(
        assessor,
        top_n=top_n,
        timeout_s=timeout_s,
        requirements_threshold=0.5,
        min_score=0.5,
    )


class TestCandidatesAssessed:
    async def test_a5_only_the_top_n_by_retrieval_score_are_assessed(self) -> None:
        candidates = _candidates(12)
        assessor = FakeCandidateAssessor(default=WEAK)

        await _use_case(assessor, top_n=10).execute(QUESTION, list(reversed(candidates)))

        assert sorted(assessor.assessed) == sorted(c.product_id for c in candidates[:10])

    async def test_a5_a_candidate_past_the_deadline_counts_as_not_assessed(self) -> None:
        slow, fast = _candidates(2)
        assessor = FakeCandidateAssessor(
            outcomes={slow.product_id: YES, fast.product_id: WEAK},
            delays={slow.product_id: 1.0},
        )

        result = await _use_case(assessor, timeout_s=0.2).execute(QUESTION, [slow, fast])

        assert result.product_id == fast.product_id
        assert result.assessed == 1


class TestFailures:
    async def test_a6_a_transient_failure_skips_only_that_candidate(self) -> None:
        failing, ok = _candidates(2)
        assessor = FakeCandidateAssessor(
            outcomes={failing.product_id: LLMUnavailableError("down"), ok.product_id: WEAK}
        )

        result = await _use_case(assessor).execute(QUESTION, [failing, ok])

        assert result.product_id == ok.product_id
        assert result.reason is SelectionReason.CHOSEN

    async def test_a6_all_failing_falls_back_to_retrieval_order(self) -> None:
        candidates = _candidates(3)
        assessor = FakeCandidateAssessor(default=LLMUnavailableError("down"))

        result = await _use_case(assessor).execute(QUESTION, list(reversed(candidates)))

        assert result.product_id is None
        assert result.fallback_used is True
        assert result.reason is SelectionReason.NO_ASSESSMENTS
        assert [c.product_id for c in result.candidates] == [c.product_id for c in candidates]

    async def test_a6_a_configuration_error_propagates(self) -> None:
        assessor = FakeCandidateAssessor(default=PermissionError("bad key"))

        with pytest.raises(PermissionError):
            await _use_case(assessor).execute(QUESTION, _candidates(2))


class TestResult:
    async def test_candidates_are_returned_in_retrieval_order(self) -> None:
        candidates = _candidates(4)
        shuffled = random.Random(7).sample(candidates, k=4)
        assessor = FakeCandidateAssessor(default=WEAK)

        result = await _use_case(assessor).execute(QUESTION, shuffled)

        assert [c.product_id for c in result.candidates] == [c.product_id for c in candidates]
        first = result.candidates[0]
        assert (first.sku, first.name, first.price_cents) == ("SECRET-SKU-0", "Secret name 0", 1000)

    async def test_a2_shuffled_input_gives_the_same_recommendation(self) -> None:
        candidates = _candidates(6)
        outcomes = {c.product_id: WEAK for c in candidates}
        outcomes[candidates[3].product_id] = YES

        results = {
            (await _use_case(FakeCandidateAssessor(outcomes=dict(outcomes))).execute(
                QUESTION, random.Random(seed).sample(candidates, k=6)
            )).product_id
            for seed in range(5)
        }

        assert results == {candidates[3].product_id}


class TestLogging:
    async def test_a9_one_line_per_selection_with_ids_only(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        failing, chosen, other = _candidates(3)
        assessor = FakeCandidateAssessor(
            outcomes={
                failing.product_id: LLMUnavailableError("429"),
                chosen.product_id: YES,
                other.product_id: WEAK,
            }
        )
        caplog.set_level(logging.INFO, logger="contexts.assistant")

        await _use_case(assessor).execute(QUESTION, [failing, chosen, other])

        lines = [r.getMessage() for r in caplog.records if r.name.startswith("contexts.assistant")]
        assert len(lines) == 1
        line = lines[0]
        for expected in (
            "provider=fake",
            "model=fake-assessor",
            "candidates=3",
            "assessed=2",
            "api_calls=6",
            "input_tokens=200",
            "output_tokens=20",
            "cost_usd=None",
            "reason=chosen",
            f"product_id={chosen.product_id}",
            "latency_ms=",
        ):
            assert expected in line
        for leaked in ("SECRET", "Secret name", "hiking"):
            assert leaked not in line


class TestReviewFixes:
    async def test_cr3_a_configuration_error_does_not_wait_for_the_deadline(self) -> None:
        broken, slow = _candidates(2)
        assessor = FakeCandidateAssessor(
            outcomes={broken.product_id: PermissionError("bad key"), slow.product_id: WEAK},
            delays={slow.product_id: 5.0},
        )
        started = time.perf_counter()

        with pytest.raises(PermissionError):
            await _use_case(assessor, timeout_s=3.0).execute(QUESTION, [broken, slow])

        assert time.perf_counter() - started < 1.0
        assert assessor.cancelled == 1

    async def test_cr3_cancelling_the_request_cancels_every_assessment(self) -> None:
        candidates = _candidates(3)
        assessor = FakeCandidateAssessor(
            default=WEAK, delays={c.product_id: 5.0 for c in candidates}
        )
        task = asyncio.create_task(_use_case(assessor).execute(QUESTION, candidates))
        await asyncio.sleep(0.05)

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert assessor.cancelled == 3

    async def test_cr4_usage_of_a_failed_assessment_is_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        failing, ok = _candidates(2)
        partial = AssessmentUsage(api_calls=3, input_tokens=80, output_tokens=20)
        assessor = FakeCandidateAssessor(
            outcomes={
                failing.product_id: AssessmentUnavailableError(partial),
                ok.product_id: WEAK,
            }
        )
        caplog.set_level(logging.INFO, logger="contexts.assistant")

        await _use_case(assessor).execute(QUESTION, [failing, ok])

        [line] = [r.getMessage() for r in caplog.records if r.name.startswith("contexts.assistant")]
        assert "api_calls=6" in line
        assert "input_tokens=180" in line
        assert "output_tokens=30" in line

    async def test_cr2_unassessed_candidates_are_logged_with_their_reason(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        failing, slow, invalid, ok = _candidates(4)
        assessor = FakeCandidateAssessor(
            outcomes={
                failing.product_id: LLMUnavailableError("429"),
                slow.product_id: WEAK,
                invalid.product_id: None,
                ok.product_id: WEAK,
            },
            delays={slow.product_id: 5.0},
        )
        caplog.set_level(logging.INFO, logger="contexts.assistant")

        result = await _use_case(assessor, timeout_s=0.3).execute(
            QUESTION, [failing, slow, invalid, ok]
        )

        assert result.product_id == ok.product_id
        [line] = [r.getMessage() for r in caplog.records if r.name.startswith("contexts.assistant")]
        assert f"{failing.product_id}:error" in line
        assert f"{slow.product_id}:deadline" in line
        assert f"{invalid.product_id}:invalid_sample" in line
