import itertools
from uuid import UUID, uuid4

import pytest

from contexts.assistant.domain.candidate import Assessment, Candidate, RubricAnswers
from contexts.assistant.domain.exceptions import InvalidAssessmentError
from contexts.assistant.domain.rubric import (
    MEETS_REQUIREMENTS,
    RUBRIC,
    SUITABLE_FOR_USE,
    RubricQuestion,
)
from contexts.assistant.domain.selection import Selection, SelectionReason, select

REQUIREMENTS = 0.5
MIN_SCORE = 0.5


def _candidate(retrieval_score: float = 0.5, product_id: UUID | None = None) -> Candidate:
    return Candidate(
        product_id=product_id or uuid4(),
        sku="SKU",
        name="Name",
        price_cents=100,
        currency="EUR",
        content="SKU: SKU | Name: Name | Price: 1.00 EUR",
        retrieval_score=retrieval_score,
    )


def _assessed(candidate: Candidate, meets: float, suitable: float) -> Assessment:
    return Assessment(
        product_id=candidate.product_id,
        answers=RubricAnswers(meets_requirements=meets, suitable_for_use=suitable),
    )


def _not_assessed(candidate: Candidate) -> Assessment:
    return Assessment(product_id=candidate.product_id, answers=None)


def _select(candidates: list[Candidate], assessments: list[Assessment]) -> Selection:
    return select(candidates, assessments, REQUIREMENTS, MIN_SCORE)


class TestRanking:
    def test_a1_highest_suitability_wins(self) -> None:
        low, high = _candidate(), _candidate()

        selection = _select([low, high], [_assessed(low, 1, 0.67), _assessed(high, 1, 1)])

        assert selection.product_id == high.product_id
        assert selection.score == 1
        assert selection.reason is SelectionReason.CHOSEN
        assert selection.fallback_used is False

    def test_a1_a_tie_goes_to_the_higher_retrieval_score(self) -> None:
        weaker, stronger = _candidate(retrieval_score=0.4), _candidate(retrieval_score=0.9)

        selection = _select(
            [weaker, stronger], [_assessed(weaker, 1, 1), _assessed(stronger, 1, 1)]
        )

        assert selection.product_id == stronger.product_id

    def test_a1_a_double_tie_goes_to_the_lower_product_id(self) -> None:
        first = _candidate(product_id=UUID("00000000-0000-0000-0000-000000000001"))
        second = _candidate(product_id=UUID("00000000-0000-0000-0000-000000000002"))

        selection = _select(
            [second, first], [_assessed(second, 1, 1), _assessed(first, 1, 1)]
        )

        assert selection.product_id == first.product_id


class TestThresholds:
    def test_a1_requirements_filter_excludes_even_the_most_suitable(self) -> None:
        unmet, met = _candidate(), _candidate()

        selection = _select([unmet, met], [_assessed(unmet, 0.33, 1), _assessed(met, 0.67, 0.67)])

        assert selection.product_id == met.product_id

    def test_a1_exactly_at_both_thresholds_passes(self) -> None:
        candidate = _candidate()

        selection = _select([candidate], [_assessed(candidate, 0.5, 0.5)])

        assert selection.product_id == candidate.product_id

    def test_a1_all_below_min_score_recommends_nothing(self) -> None:
        a, b = _candidate(), _candidate()

        selection = _select([a, b], [_assessed(a, 1, 0.33), _assessed(b, 1, 0)])

        assert selection.product_id is None
        assert selection.reason is SelectionReason.BELOW_THRESHOLD
        assert selection.fallback_used is False

    def test_a1_all_failing_requirements_recommends_nothing(self) -> None:
        a = _candidate()

        selection = _select([a], [_assessed(a, 0, 1)])

        assert selection.product_id is None
        assert selection.reason is SelectionReason.BELOW_THRESHOLD


class TestUnassessed:
    def test_a6_a_failed_candidate_is_skipped(self) -> None:
        failed, ok = _candidate(retrieval_score=0.99), _candidate()

        selection = _select([failed, ok], [_not_assessed(failed), _assessed(ok, 1, 1)])

        assert selection.product_id == ok.product_id

    def test_a6_no_assessment_at_all_falls_back(self) -> None:
        a, b = _candidate(), _candidate()

        selection = _select([a, b], [_not_assessed(a), _not_assessed(b)])

        assert selection.product_id is None
        assert selection.reason is SelectionReason.NO_ASSESSMENTS
        assert selection.fallback_used is True


class TestSafety:
    def test_a2_never_returns_a_product_outside_the_candidates(self) -> None:
        candidate, stranger = _candidate(), _candidate()

        selection = _select([candidate], [_assessed(stranger, 1, 1), _assessed(candidate, 1, 0.67)])

        assert selection.product_id == candidate.product_id

    def test_a2_shuffled_input_gives_the_same_selection(self) -> None:
        candidates = [_candidate(retrieval_score=s) for s in (0.2, 0.9, 0.5, 0.9)]
        assessments = [
            _assessed(candidates[0], 1, 1),
            _assessed(candidates[1], 1, 1),
            _assessed(candidates[2], 0.33, 1),
            _assessed(candidates[3], 1, 1),
        ]
        expected = _select(candidates, assessments)

        for order in itertools.permutations(range(len(candidates))):
            shuffled = [candidates[i] for i in order]
            assert _select(shuffled, list(reversed(assessments))) == expected


class TestRubric:
    def test_rubric_has_the_two_questions_in_order(self) -> None:
        assert [question.id for question in RUBRIC] == ["meets_requirements", "suitable_for_use"]

    def test_requirements_question_says_yes_when_there_are_no_explicit_requirements(self) -> None:
        assert "no explicit requirements" in MEETS_REQUIREMENTS.yes_means.lower()

    @pytest.mark.parametrize("question", RUBRIC)
    def test_every_question_explains_yes_and_no(self, question: RubricQuestion) -> None:
        assert question.instructions
        assert question.yes_means
        assert question.no_means

    def test_suitability_is_the_ranking_question(self) -> None:
        assert SUITABLE_FOR_USE.id == "suitable_for_use"


class TestRubricAnswers:
    @pytest.mark.parametrize("value", [-0.01, 1.01])
    def test_rejects_values_that_are_not_probabilities(self, value: float) -> None:
        with pytest.raises(InvalidAssessmentError, match="probability"):
            RubricAnswers(meets_requirements=value, suitable_for_use=0.5)
