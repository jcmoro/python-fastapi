from dataclasses import replace
from uuid import uuid4

import pytest
from tests.evals.harness import (
    ApiCalls,
    EvalQuestion,
    SelectorRun,
    accuracy_line,
    baseline_lines,
    is_correct,
    load_dataset,
    outcome_of,
    shuffled,
    threshold_table,
)

from contexts.assistant.domain.candidate import Assessment, Candidate, RubricAnswers
from contexts.assistant.domain.selection import SelectionReason

RECOMMEND = EvalQuestion(
    id="q01",
    kind="recommend",
    text="?",
    acceptable_skus=frozenset({"MT-0002"}),
    accept_no_recommendation=False,
)
NO_RECOMMENDATION = EvalQuestion(
    id="q07",
    kind="no_recommendation",
    text="?",
    acceptable_skus=frozenset(),
    accept_no_recommendation=True,
)
AMBIGUOUS = EvalQuestion(
    id="q09",
    kind="ambiguous",
    text="?",
    acceptable_skus=frozenset({"MT-0016", "MT-0015"}),
    accept_no_recommendation=True,
)


class TestScoringRule:
    @pytest.mark.parametrize(
        ("question", "outcome", "correct"),
        [
            (RECOMMEND, "chosen:MT-0002", True),
            (RECOMMEND, "chosen:MT-0001", False),
            (RECOMMEND, "below_threshold", False),
            (RECOMMEND, "null", False),
            (RECOMMEND, "no_assessments", False),
            (NO_RECOMMENDATION, "below_threshold", True),
            (NO_RECOMMENDATION, "null", True),
            (NO_RECOMMENDATION, "chosen:MT-0002", False),
            (NO_RECOMMENDATION, "no_assessments", False),
            (AMBIGUOUS, "chosen:MT-0015", True),
            (AMBIGUOUS, "chosen:MT-0001", False),
            (AMBIGUOUS, "below_threshold", True),
        ],
    )
    def test_follows_the_agreed_rule(
        self, question: EvalQuestion, outcome: str, correct: bool
    ) -> None:
        assert is_correct(question, outcome) is correct

    def test_outcome_records_what_happened(self) -> None:
        assert outcome_of(None, None) == "null"
        assert outcome_of(SelectionReason.CHOSEN, "MT-0002") == "chosen:MT-0002"
        assert outcome_of(SelectionReason.BELOW_THRESHOLD, None) == "below_threshold"

    def test_accuracy_is_reported_in_counts_by_kind(self) -> None:
        line = accuracy_line(
            [RECOMMEND, NO_RECOMMENDATION, AMBIGUOUS],
            ["chosen:MT-0002", "chosen:MT-0002", "below_threshold"],
        )

        assert line == "2/3: recommend 1/1, no_recommendation 0/1, ambiguous 1/1"


class TestHarness:
    def test_dataset_loads_with_unique_opaque_skus(self) -> None:
        dataset = load_dataset()

        skus = [product.sku for product in dataset.products]
        assert len(skus) == len(set(skus)) == 20
        assert all(sku.startswith("MT-") for sku in skus)
        assert len(dataset.questions) == 10
        known = set(skus)
        assert all(q.acceptable_skus <= known for q in dataset.questions)

    def test_product_ids_are_deterministic(self) -> None:
        assert [p.product_id for p in load_dataset().products] == [
            p.product_id for p in load_dataset().products
        ]

    def test_shuffle_is_seeded_by_question(self) -> None:
        candidates = [_candidate(f"MT-{n:04d}", 0.5) for n in range(10)]

        assert shuffled(candidates, "q01") == shuffled(candidates, "q01")
        assert sorted(shuffled(candidates, "q01"), key=lambda c: c.sku) == candidates

    def test_threshold_table_recomputes_selection_without_calls(self) -> None:
        good, weak = _candidate("MT-0002", 0.9), _candidate("MT-0001", 0.8)
        run = SelectorRun(
            question=RECOMMEND,
            outcome="chosen:MT-0002",
            latency_ms=1,
            candidates=(good, weak),
            assessments=(
                Assessment(good.product_id, RubricAnswers(1.0, 2 / 3)),
                Assessment(weak.product_id, RubricAnswers(1.0, 1 / 3)),
            ),
            unassessed=0,
        )

        rows = {(r.requirements_threshold, r.min_score): r for r in threshold_table([run])}

        assert (rows[(2 / 3, 2 / 3)].correct, rows[(2 / 3, 2 / 3)].recommended) == (1, 1)
        assert (rows[(2 / 3, 1.0)].correct, rows[(2 / 3, 1.0)].recommended) == (0, 0)

    def test_an_acceptable_sku_outside_the_candidates_is_unreachable(self) -> None:
        run = SelectorRun(
            question=RECOMMEND,
            outcome="below_threshold",
            latency_ms=1,
            candidates=(_candidate("MT-0001", 0.9),),
            assessments=(),
            unassessed=0,
        )

        assert run.reachable is False
        assert replace(run, question=NO_RECOMMENDATION).reachable is True

    def test_baseline_gives_end_to_end_and_selector_only(self) -> None:
        good = _candidate("MT-0002", 0.9)
        missing = _candidate("MT-0001", 0.9)
        runs = [
            _run(RECOMMEND, "chosen:MT-0002", good),
            _run(replace(RECOMMEND, id="q06"), "chosen:MT-0001", missing),
            _run(NO_RECOMMENDATION, "below_threshold", missing),
        ]

        end_to_end, selector_only = baseline_lines(runs)

        assert end_to_end == (
            "end-to-end 2/3: recommend 1/2, no_recommendation 1/1; "
            "retrieval ceiling 2/3 (q06: no acceptable SKU among the candidates)"
        )
        assert selector_only == (
            "selector only 2/2: recommend 1/1, no_recommendation 1/1 "
            "(questions with an acceptable SKU among the candidates)"
        )

    async def test_api_calls_flag_many_rate_limits(self) -> None:
        calls = ApiCalls(requests=20)
        calls.statuses[200] = 19
        calls.statuses[429] = 1
        assert calls.too_many_rate_limits() is False

        calls.statuses[429] = 2
        assert calls.too_many_rate_limits() is True


def _candidate(sku: str, score: float) -> Candidate:
    return Candidate(
        product_id=uuid4(),
        sku=sku,
        name=sku,
        price_cents=1000,
        currency="EUR",
        content=sku,
        retrieval_score=score,
    )


def _run(question: EvalQuestion, outcome: str, candidate: Candidate) -> SelectorRun:
    return SelectorRun(
        question=question,
        outcome=outcome,
        latency_ms=1,
        candidates=(candidate,),
        assessments=(),
        unassessed=0,
    )
