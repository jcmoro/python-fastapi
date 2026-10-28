import asyncio
import logging
import time
from collections.abc import Sequence

from contexts.assistant.application.dtos import CandidateDTO, RecommendationDTO
from contexts.assistant.domain.candidate import Assessment, AssessmentFailure, Candidate
from contexts.assistant.domain.exceptions import AssessmentUnavailableError, LLMUnavailableError
from contexts.assistant.domain.ports.candidate_assessor import CandidateAssessor
from contexts.assistant.domain.selection import Selection, select

logger = logging.getLogger(__name__)


class RecommendCandidate:
    def __init__(
        self,
        assessor: CandidateAssessor,
        *,
        top_n: int,
        timeout_s: float,
        requirements_threshold: float,
        min_score: float,
    ) -> None:
        self._assessor = assessor
        self._top_n = top_n
        self._timeout_s = timeout_s
        self._requirements_threshold = requirements_threshold
        self._min_score = min_score

    async def execute(self, question: str, candidates: Sequence[Candidate]) -> RecommendationDTO:
        started = time.perf_counter()
        top = sorted(candidates, key=lambda c: (-c.retrieval_score, c.product_id))[: self._top_n]
        assessments = await self._assess_all(question, top)
        selection = select(top, assessments, self._requirements_threshold, self._min_score)
        self._log(top, assessments, selection, started)
        chosen = next((c for c in top if c.product_id == selection.product_id), None)
        return RecommendationDTO(
            product_id=selection.product_id,
            sku=chosen.sku if chosen is not None else None,
            score=selection.score,
            reason=selection.reason,
            fallback_used=selection.fallback_used,
            candidates=tuple(CandidateDTO.from_candidate(candidate) for candidate in top),
            assessed=_assessed(assessments),
        )

    async def _assess_all(
        self, question: str, candidates: Sequence[Candidate]
    ) -> list[Assessment]:
        if not candidates:
            return []
        tasks = {
            asyncio.create_task(self._assess_one(question, candidate)): candidate
            for candidate in candidates
        }
        try:
            done, _ = await asyncio.wait(
                tasks, timeout=self._timeout_s, return_when=asyncio.FIRST_EXCEPTION
            )
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        finished = [task for task in tasks if task in done]
        errors = [error for task in finished if (error := task.exception()) is not None]
        if errors:
            raise errors[0]
        return [
            task.result()
            if task in done
            else Assessment(
                product_id=candidate.product_id,
                answers=None,
                failure=AssessmentFailure.DEADLINE,
            )
            for task, candidate in tasks.items()
        ]

    async def _assess_one(self, question: str, candidate: Candidate) -> Assessment:
        try:
            return await self._assessor.assess(question, candidate)
        except AssessmentUnavailableError as error:
            return Assessment(
                product_id=candidate.product_id,
                answers=None,
                usage=error.usage,
                failure=AssessmentFailure.ERROR,
            )
        except LLMUnavailableError:
            return Assessment(
                product_id=candidate.product_id, answers=None, failure=AssessmentFailure.ERROR
            )

    def _log(
        self,
        candidates: Sequence[Candidate],
        assessments: Sequence[Assessment],
        selection: Selection,
        started: float,
    ) -> None:
        costs = [a.usage.cost_usd for a in assessments]
        cost_usd = sum(c for c in costs if c is not None) if costs and None not in costs else None
        unassessed = ",".join(
            f"{a.product_id}:{a.failure.value}"
            for a in sorted(assessments, key=lambda a: a.product_id)
            if a.answers is None and a.failure is not None
        )
        logger.info(
            "candidate_selection provider=%s model=%s candidates=%d assessed=%d api_calls=%d "
            "input_tokens=%d output_tokens=%d cost_usd=%s latency_ms=%d reason=%s product_id=%s "
            "unassessed=%s",
            self._assessor.provider,
            self._assessor.model_name,
            len(candidates),
            _assessed(assessments),
            sum(a.usage.api_calls for a in assessments),
            sum(a.usage.input_tokens for a in assessments),
            sum(a.usage.output_tokens for a in assessments),
            cost_usd,
            round((time.perf_counter() - started) * 1000),
            selection.reason.value,
            selection.product_id,
            unassessed,
        )


def _assessed(assessments: Sequence[Assessment]) -> int:
    return sum(1 for assessment in assessments if assessment.answers is not None)
