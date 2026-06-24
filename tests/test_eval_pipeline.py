import json

import pytest

from evals.portfolio_rag_eval import (
    PORTFOLIO_DOCUMENTS,
    PORTFOLIO_QUESTIONS,
    build_report,
    run_deterministic_eval,
)


@pytest.mark.eval
def test_eval_dataset_has_25_portfolio_safe_questions():
    assert len(PORTFOLIO_QUESTIONS) == 25
    assert len(PORTFOLIO_DOCUMENTS) >= 10
    assert all(question.question_id for question in PORTFOLIO_QUESTIONS)
    assert all(question.relevant_doc_ids for question in PORTFOLIO_QUESTIONS)


@pytest.mark.eval
def test_deterministic_eval_reports_precision_and_recall_at_5():
    result = run_deterministic_eval()

    assert result["dataset"]["question_count"] == 25
    assert result["dataset"]["portfolio_safe"] is True
    assert result["baseline_metrics"]["precision_at_5"] == 0.192
    assert result["baseline_metrics"]["recall_at_5"] == 0.92
    assert result["metrics"]["precision_at_5"] >= 0.2
    assert result["metrics"]["recall_at_5"] == 1.0
    assert result["improvement"]["recall_at_5_delta"] == 0.08
    assert all("precision_at_5" in row and "recall_at_5" in row for row in result["rows"])


@pytest.mark.eval
def test_llm_judge_skips_without_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = build_report(include_llm_judge=True)

    assert result["llm_judge"]["status"] == "skipped"
    assert "OPENAI_API_KEY" in result["llm_judge"]["reason"]
    json.dumps(result)
