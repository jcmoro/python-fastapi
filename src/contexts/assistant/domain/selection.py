from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from contexts.assistant.domain.candidate import Assessment, Candidate, RubricAnswers


class SelectionReason(str, Enum):
    CHOSEN = "chosen"
    BELOW_THRESHOLD = "below_threshold"
    NO_ASSESSMENTS = "no_assessments"


@dataclass(frozen=True, slots=True)
class Selection:
    product_id: UUID | None
    score: float | None
    fallback_used: bool
    reason: SelectionReason


def select(
    candidates: Sequence[Candidate],
    assessments: Sequence[Assessment],
    requirements_threshold: float,
    min_score: float,
) -> Selection:
    by_id = {candidate.product_id: candidate for candidate in candidates}
    answered = [
        (by_id[assessment.product_id], assessment.answers)
        for assessment in assessments
        if assessment.product_id in by_id and assessment.answers is not None
    ]
    if not answered:
        return Selection(None, None, fallback_used=True, reason=SelectionReason.NO_ASSESSMENTS)

    eligible = [
        (candidate, answers)
        for candidate, answers in answered
        if answers.meets_requirements >= requirements_threshold
    ]
    ranked = sorted(eligible, key=_ranking_key)
    if not ranked or ranked[0][1].suitable_for_use < min_score:
        return Selection(None, None, fallback_used=False, reason=SelectionReason.BELOW_THRESHOLD)

    best, answers = ranked[0]
    return Selection(
        product_id=best.product_id,
        score=answers.suitable_for_use,
        fallback_used=False,
        reason=SelectionReason.CHOSEN,
    )


def _ranking_key(pair: tuple[Candidate, RubricAnswers]) -> tuple[float, float, UUID]:
    candidate, answers = pair
    return (-answers.suitable_for_use, -candidate.retrieval_score, candidate.product_id)
