import json
import random
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import product as grid
from pathlib import Path
from statistics import median
from uuid import UUID, uuid5

import anthropic
import httpx2

from contexts.assistant.domain.agent import AgentResult, AgentUnavailableError
from contexts.assistant.domain.candidate import Assessment, Candidate
from contexts.assistant.domain.ports.candidate_assessor import CandidateAssessor
from contexts.assistant.domain.ports.catalog_agent import CatalogAgent
from contexts.assistant.domain.ports.document_search import DocumentSearch
from contexts.assistant.domain.ports.embedding_client import EmbeddingClient
from contexts.assistant.domain.retrieved_document import RetrievedDocument
from contexts.assistant.domain.selection import SelectionReason, select

DATASET_PATH = Path(__file__).with_name("dataset.json")
EVAL_DATABASE = "catalog_eval"
PRODUCT_NAMESPACE = UUID("6f1c2a52-5d0e-4c8e-9a51-0e7f3b1d9c40")
LOADED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)
RATE_LIMIT_ABORT_SHARE = 0.05
THRESHOLD_GRID = (1 / 3, 2 / 3, 1.0)
LIST_PRICE_USD_PER_MTOK = {"claude-haiku-5-5": (0.10, 0.50)}

NULL = "null"
CHOSEN_PREFIX = "chosen:"


@dataclass(frozen=True, slots=True)
class EvalProduct:
    sku: str
    name: str
    price_cents: int
    currency: str

    @property
    def product_id(self) -> UUID:
        return uuid5(PRODUCT_NAMESPACE, self.sku)


@dataclass(frozen=True, slots=True)
class EvalQuestion:
    id: str
    kind: str
    text: str
    acceptable_skus: frozenset[str]
    accept_no_recommendation: bool


@dataclass(frozen=True, slots=True)
class Dataset:
    version: int
    products: tuple[EvalProduct, ...]
    questions: tuple[EvalQuestion, ...]


@dataclass(frozen=True, slots=True)
class EvalCatalog:
    dataset: Dataset
    embeddings: EmbeddingClient
    search: DocumentSearch
    indexed: int


def load_dataset(path: Path = DATASET_PATH) -> Dataset:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Dataset(
        version=raw["version"],
        products=tuple(
            EvalProduct(
                sku=item["sku"],
                name=item["name"],
                price_cents=item["price_cents"],
                currency=item["currency"],
            )
            for item in raw["products"]
        ),
        questions=tuple(
            EvalQuestion(
                id=item["id"],
                kind=item["kind"],
                text=item["text"],
                acceptable_skus=frozenset(item["acceptable_skus"]),
                accept_no_recommendation=item["accept_no_recommendation"],
            )
            for item in raw["questions"]
        ),
    )


def outcome_of(reason: SelectionReason | None, sku: str | None) -> str:
    if reason is None:
        return NULL
    if reason is SelectionReason.CHOSEN:
        return f"{CHOSEN_PREFIX}{sku}"
    return reason.value


def is_correct(question: EvalQuestion, outcome: str) -> bool:
    if outcome.startswith(CHOSEN_PREFIX):
        return outcome.removeprefix(CHOSEN_PREFIX) in question.acceptable_skus
    if outcome in (SelectionReason.BELOW_THRESHOLD.value, NULL):
        return question.accept_no_recommendation
    return False


def accuracy_line(questions: Sequence[EvalQuestion], outcomes: Sequence[str]) -> str:
    hits: Counter[str] = Counter()
    totals: Counter[str] = Counter()
    for question, outcome in zip(questions, outcomes, strict=True):
        totals[question.kind] += 1
        hits[question.kind] += is_correct(question, outcome)
    by_kind = ", ".join(f"{kind} {hits[kind]}/{totals[kind]}" for kind in totals)
    return f"{sum(hits.values())}/{len(questions)}: {by_kind}"


def candidate_of(hit: RetrievedDocument) -> Candidate | None:
    if hit.sku is None or hit.name is None or hit.price_cents is None or hit.currency is None:
        return None
    return Candidate(
        product_id=hit.product_id,
        sku=hit.sku,
        name=hit.name,
        price_cents=hit.price_cents,
        currency=hit.currency,
        content=hit.content,
        retrieval_score=hit.score,
    )


def shuffled(candidates: Sequence[Candidate], seed: str) -> list[Candidate]:
    copy = list(candidates)
    random.Random(seed).shuffle(copy)
    return copy


@dataclass(frozen=True, slots=True)
class ThresholdRow:
    requirements_threshold: float
    min_score: float
    correct: int
    recommended: int


@dataclass(frozen=True, slots=True)
class SelectorRun:
    question: EvalQuestion
    outcome: str
    latency_ms: int
    candidates: tuple[Candidate, ...]
    assessments: tuple[Assessment, ...]
    unassessed: int

    @property
    def correct(self) -> bool:
        return is_correct(self.question, self.outcome)

    @property
    def reachable(self) -> bool:
        return self.question.accept_no_recommendation or any(
            candidate.sku in self.question.acceptable_skus for candidate in self.candidates
        )


def baseline_lines(runs: Sequence[SelectorRun]) -> tuple[str, str]:
    reachable = [run for run in runs if run.reachable]
    unreachable = [run.question.id for run in runs if not run.reachable]
    ceiling = f"retrieval ceiling {len(reachable)}/{len(runs)}"
    if unreachable:
        ceiling += f" ({', '.join(unreachable)}: no acceptable SKU among the candidates)"
    end_to_end = accuracy_line([r.question for r in runs], [r.outcome for r in runs])
    selector_only = accuracy_line([r.question for r in reachable], [r.outcome for r in reachable])
    return (
        f"end-to-end {end_to_end}; {ceiling}",
        f"selector only {selector_only} (questions with an acceptable SKU among the candidates)",
    )


def threshold_table(runs: Sequence[SelectorRun]) -> list[ThresholdRow]:
    rows = []
    for requirements_threshold, min_score in grid(THRESHOLD_GRID, THRESHOLD_GRID):
        outcomes = []
        for run in runs:
            selection = select(run.candidates, run.assessments, requirements_threshold, min_score)
            chosen = next(
                (c.sku for c in run.candidates if c.product_id == selection.product_id), None
            )
            outcomes.append((run.question, outcome_of(selection.reason, chosen)))
        rows.append(
            ThresholdRow(
                requirements_threshold=requirements_threshold,
                min_score=min_score,
                correct=sum(is_correct(question, outcome) for question, outcome in outcomes),
                recommended=sum(outcome.startswith(CHOSEN_PREFIX) for _, outcome in outcomes),
            )
        )
    return rows


@dataclass
class ApiCalls:
    requests: int = 0
    statuses: Counter[int] = field(default_factory=Counter)

    async def on_request(self, _request: httpx2.Request) -> None:
        self.requests += 1

    async def on_response(self, response: httpx2.Response) -> None:
        self.statuses[response.status_code] += 1

    @property
    def answered(self) -> int:
        return self.statuses[200]

    @property
    def rate_limited(self) -> int:
        return self.statuses[429]

    def too_many_rate_limits(self) -> bool:
        return self.rate_limited > RATE_LIMIT_ABORT_SHARE * self.requests

    def line(self) -> str:
        others = {code: n for code, n in sorted(self.statuses.items()) if code not in (200, 429)}
        return (
            f"api calls: {self.answered} answered of {self.requests} made, "
            f"429={self.rate_limited}, other statuses={others or 'none'}"
        )


ClientFactory = Callable[[], tuple[anthropic.AsyncAnthropic, ApiCalls]]


class RecordingAssessor(CandidateAssessor):
    def __init__(self, inner: CandidateAssessor) -> None:
        self._inner = inner
        self.assessments: list[Assessment] = []

    @property
    def provider(self) -> str:
        return self._inner.provider

    @property
    def model_name(self) -> str:
        return self._inner.model_name

    async def assess(self, question: str, candidate: Candidate) -> Assessment:
        assessment = await self._inner.assess(question, candidate)
        self.assessments.append(assessment)
        return assessment

    def take(self) -> tuple[Assessment, ...]:
        taken = tuple(self.assessments)
        self.assessments.clear()
        return taken


@dataclass(frozen=True, slots=True)
class Tokens:
    input: int
    output: int

    def __add__(self, other: "Tokens") -> "Tokens":
        return Tokens(self.input + other.input, self.output + other.output)

    def line(self, model: str) -> str:
        prices = LIST_PRICE_USD_PER_MTOK.get(model)
        cost = (
            f"~{(self.input * prices[0] + self.output * prices[1]) / 1_000_000:.4f} USD "
            "(estimated at list price)"
            if prices is not None
            else "cost unknown for this model"
        )
        return f"tokens: input={self.input} output={self.output}, {cost}"


def assessment_tokens(assessments: Sequence[Assessment]) -> Tokens:
    return Tokens(
        input=sum(a.usage.input_tokens for a in assessments),
        output=sum(a.usage.output_tokens for a in assessments),
    )


class RecordingAgent(CatalogAgent):
    def __init__(self, inner: CatalogAgent) -> None:
        self._inner = inner
        self.result: AgentResult | None = None
        self.error: AgentUnavailableError | None = None

    async def run(self, question: str) -> AgentResult:
        self.result, self.error = None, None
        try:
            self.result = await self._inner.run(question)
        except AgentUnavailableError as error:
            self.error = error
            raise
        return self.result


def latency_line(latencies_ms: Sequence[int]) -> str:
    ordered = sorted(latencies_ms)
    return f"latency_ms: median={median(ordered):.0f} max={ordered[-1]} total={sum(ordered)}"
