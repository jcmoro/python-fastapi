import time

import pytest
from tests.evals.harness import (
    ClientFactory,
    EvalCatalog,
    RecordingAgent,
    RecordingAssessor,
    Tokens,
    accuracy_line,
    assessment_tokens,
    is_correct,
    latency_line,
    outcome_of,
)

from contexts.assistant.application.dtos import AskCommand
from contexts.assistant.application.use_cases.ask_assistant import AskAssistant
from contexts.assistant.application.use_cases.recommend_candidate import RecommendCandidate
from contexts.assistant.infrastructure.agent.anthropic_agent_model import AnthropicAgentModel
from contexts.assistant.infrastructure.agent.langgraph_catalog_agent import LangGraphCatalogAgent
from contexts.assistant.infrastructure.agent.tools import build_tools
from contexts.assistant.infrastructure.llm.anthropic_llm_client import AnthropicLLMClient
from contexts.assistant.infrastructure.llm.claude_candidate_assessor import (
    ClaudeCandidateAssessor,
)
from shared.infrastructure.settings import Settings

pytestmark = pytest.mark.eval

E4_MEASURES = (
    "E4 · Full agent — measures how often AskAssistant in agent mode, end to end, returns an "
    "acceptable recommendation, by the scoring rule."
)


async def test_e4_full_agent(
    eval_catalog: EvalCatalog, anthropic_clients: ClientFactory, settings: Settings
) -> None:
    client, calls = anthropic_clients()
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
    tools = build_tools(
        embedding_client=eval_catalog.embeddings,
        document_search=eval_catalog.search,
        recommend_candidate=RecommendCandidate(
            recorder,
            top_n=settings.selector_top_n,
            timeout_s=settings.selector_timeout_s,
            requirements_threshold=settings.selector_requirements_threshold,
            min_score=settings.selector_min_score,
        ),
        rag_top_k=settings.rag_top_k,
        selector_top_n=settings.selector_top_n,
    )
    agent = RecordingAgent(
        LangGraphCatalogAgent(
            model=AnthropicAgentModel(
                client=client,
                model=settings.llm_model,
                timeout_s=settings.llm_timeout_s,
                max_retries=settings.llm_max_retries,
                max_tokens=settings.llm_max_tokens,
            ),
            tools=tools,
            embedding_client=eval_catalog.embeddings,
            max_tool_calls=settings.agent_max_tool_calls,
        )
    )
    use_case = AskAssistant(
        AnthropicLLMClient(
            client=client,
            model=settings.llm_model,
            timeout_s=settings.llm_timeout_s,
            max_retries=settings.llm_max_retries,
        ),
        eval_catalog.embeddings,
        eval_catalog.search,
        max_tokens=settings.llm_max_tokens,
        top_k=settings.rag_top_k,
        agent=agent,
    )

    questions = eval_catalog.dataset.questions
    outcomes: list[str] = []
    latencies: list[int] = []
    tokens = Tokens(0, 0)
    lines: list[str] = []
    for question in questions:
        started = time.perf_counter()
        answer = await use_case.execute(AskCommand(question=question.text))
        latencies.append(round((time.perf_counter() - started) * 1000))
        recommendation = answer.recommendation
        outcome = outcome_of(
            recommendation.reason if recommendation is not None else None,
            recommendation.sku if recommendation is not None else None,
        )
        outcomes.append(outcome)
        usage = agent.result.usage if agent.result is not None else None
        if usage is None and agent.error is not None:
            usage = agent.error.usage
        if usage is not None:
            tokens += Tokens(usage.input_tokens, usage.output_tokens)
        tokens += assessment_tokens(recorder.take())
        verdict = "ok" if is_correct(question, outcome) else "WRONG"
        stop = answer.stop_reason.value if answer.stop_reason is not None else "unavailable"
        lines.append(
            f"  {question.id} {question.kind:<17} {outcome:<22} {verdict:<5} stop={stop} "
            f"model_stop={answer.model_stop_reason} "
            f"tool_calls={usage.tool_calls if usage is not None else 0} "
            f"fallback={answer.fallback_used} latency_ms={latencies[-1]}"
        )
        if calls.too_many_rate_limits():
            print(f"\n{E4_MEASURES}", *lines, f"  {calls.line()}", sep="\n")
            pytest.fail(f"stopped after {question.id}: too many 429s. {calls.line()}")

    print(f"\n{E4_MEASURES}")
    print(f"  result {accuracy_line(questions, outcomes)}")
    print(*lines, sep="\n")
    print(f"  {latency_line(latencies)} (per question)")
    print(f"  {tokens.line(settings.llm_model)}")
    print(f"  {calls.line()}")
