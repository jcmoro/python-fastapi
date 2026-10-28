import time
from dataclasses import dataclass

import pytest
import pytest_asyncio
from tests.evals.harness import (
    ApiCalls,
    ClientFactory,
    EvalCatalog,
    RecordingAssessor,
    SelectorRun,
    Tokens,
    assessment_tokens,
    baseline_lines,
    candidate_of,
    latency_line,
    outcome_of,
    shuffled,
    threshold_table,
)

from contexts.assistant.application.use_cases.recommend_candidate import RecommendCandidate
from contexts.assistant.domain.selection import SelectionReason
from contexts.assistant.infrastructure.llm.claude_candidate_assessor import (
    ClaudeCandidateAssessor,
)
from shared.infrastructure.settings import Settings

pytestmark = pytest.mark.eval

E1_MEASURES = (
    "E1 · Selector — measures how often the real selector (Claude assessor, top 10 candidates "
    "x 3 samples) ends in an acceptable outcome, by the scoring rule."
)
E2_MEASURES = (
    "E2 · Shuffled order — measures how often the selector repeats E1's outcome when the "
    "candidates arrive shuffled."
)
E3_MEASURES = (
    "E3 · Repeat — measures how often the selector repeats E1's outcome on an identical rerun "
    "(model run-to-run variability)."
)


@dataclass(frozen=True, slots=True)
class SelectorReport:
    runs: tuple[SelectorRun, ...]
    calls: ApiCalls
    model: str


async def _run_selector(
    title: str,
    catalog: EvalCatalog,
    clients: ClientFactory,
    settings: Settings,
    *,
    shuffle: bool,
) -> SelectorReport:
    client, calls = clients()
    recorder = RecordingAssessor(
        ClaudeCandidateAssessor(
            client=client,
            model=settings.llm_model,
            timeout_s=settings.llm_timeout_s,
            max_retries=settings.llm_max_retries,
            samples=settings.selector_samples,
            max_tokens=settings.selector_max_tokens,
            max_concurrency=settings.selector_max_concurrency,
        )
    )
    recommend = RecommendCandidate(
        recorder,
        top_n=settings.selector_top_n,
        timeout_s=settings.selector_timeout_s,
        requirements_threshold=settings.selector_requirements_threshold,
        min_score=settings.selector_min_score,
    )
    runs: list[SelectorRun] = []
    for question in catalog.dataset.questions:
        [embedding] = await catalog.embeddings.embed([question.text])
        hits = await catalog.search.search(embedding, settings.selector_top_n)
        candidates = [c for hit in hits if (c := candidate_of(hit)) is not None]
        if shuffle:
            candidates = shuffled(candidates, question.id)
        started = time.perf_counter()
        result = await recommend.execute(question.text, candidates)
        runs.append(
            SelectorRun(
                question=question,
                outcome=outcome_of(result.reason, result.sku),
                latency_ms=round((time.perf_counter() - started) * 1000),
                candidates=tuple(candidates),
                assessments=recorder.take(),
                unassessed=len(result.candidates) - result.assessed,
            )
        )
        if calls.too_many_rate_limits():
            report = SelectorReport(runs=tuple(runs), calls=calls, model=settings.llm_model)
            _print(title, report)
            pytest.fail(f"stopped after {question.id}: too many 429s. {calls.line()}")
    return SelectorReport(runs=tuple(runs), calls=calls, model=settings.llm_model)


def _print(title: str, report: SelectorReport, baseline: SelectorReport | None = None) -> None:
    runs = report.runs
    print(f"\n{title}")
    for line in baseline_lines(runs):
        print(f"  {line}")
    if baseline is not None:
        same = sum(
            run.outcome == base.outcome for run, base in zip(runs, baseline.runs, strict=True)
        )
        print(f"  same outcome as E1: {same}/{len(runs)}")
    for run in runs:
        verdict = "ok" if run.correct else "WRONG"
        print(
            f"  {run.question.id} {run.question.kind:<17} {run.outcome:<22} {verdict:<5} "
            f"reachable={'yes' if run.reachable else 'no'} unassessed={run.unassessed} "
            f"latency_ms={run.latency_ms}"
        )
    no_assessments = sum(r.outcome == SelectionReason.NO_ASSESSMENTS.value for r in runs)
    print(f"  no_assessments (model failure, not a judgement): {no_assessments}")
    print(f"  unassessed candidates: {sum(r.unassessed for r in runs)}")
    print(f"  {latency_line([r.latency_ms for r in runs])} (per selection)")
    tokens = sum((assessment_tokens(r.assessments) for r in runs), Tokens(0, 0))
    print(f"  {tokens.line(report.model)}")
    print(f"  {report.calls.line()}")


@pytest_asyncio.fixture(scope="session")
async def e1(
    eval_catalog: EvalCatalog, anthropic_clients: ClientFactory, settings: Settings
) -> SelectorReport:
    return await _run_selector(
        E1_MEASURES, eval_catalog, anthropic_clients, settings, shuffle=False
    )


async def test_e1_selector(e1: SelectorReport) -> None:
    _print(E1_MEASURES, e1)
    print("  thresholds recomputed from the same assessments (no new calls):")
    for row in threshold_table(e1.runs):
        print(
            f"    requirements_threshold={row.requirements_threshold:.2f} "
            f"min_score={row.min_score:.2f}: correct {row.correct}/{len(e1.runs)}, "
            f"recommends {row.recommended}/{len(e1.runs)}"
        )


async def test_e2_shuffled_order(
    e1: SelectorReport,
    eval_catalog: EvalCatalog,
    anthropic_clients: ClientFactory,
    settings: Settings,
) -> None:
    e2 = await _run_selector(E2_MEASURES, eval_catalog, anthropic_clients, settings, shuffle=True)
    _print(E2_MEASURES, e2, baseline=e1)


async def test_e3_repeat(
    e1: SelectorReport,
    eval_catalog: EvalCatalog,
    anthropic_clients: ClientFactory,
    settings: Settings,
) -> None:
    e3 = await _run_selector(E3_MEASURES, eval_catalog, anthropic_clients, settings, shuffle=False)
    _print(E3_MEASURES, e3, baseline=e1)
