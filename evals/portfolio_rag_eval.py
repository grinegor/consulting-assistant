from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_TOP_K = 5
DEFAULT_RESULT_PATH = Path("evals/latest_local_result.json")


@dataclass(frozen=True)
class EvalDocument:
    doc_id: str
    title: str
    category: str
    text: str


@dataclass(frozen=True)
class EvalQuestion:
    question_id: str
    question: str
    relevant_doc_ids: tuple[str, ...]


PORTFOLIO_DOCUMENTS: tuple[EvalDocument, ...] = (
    EvalDocument(
        "support_chatbot",
        "AI support chatbot for an online school",
        "Customer Support",
        "Online school support automation with an AI chatbot for FAQ answers, ticket triage, escalation rules, response quality checks, and learner satisfaction tracking.",
    ),
    EvalDocument(
        "document_processing",
        "Consulting document processing assistant",
        "Operations",
        "Document processing workflow for a consulting company: extract requirements from PDFs, classify contracts, summarize client files, and route exceptions to analysts.",
    ),
    EvalDocument(
        "sales_crm_agent",
        "CRM sales follow-up agent",
        "Sales",
        "Sales team CRM agent that scores leads, drafts follow-up emails, summarizes calls, updates pipeline stages, and alerts managers about stalled deals.",
    ),
    EvalDocument(
        "marketing_content",
        "Marketing agency content workflow",
        "Marketing",
        "Marketing agency workflow for campaign briefs, content drafts, SEO clustering, creative variants, approval checklists, and budget-aware AI use cases.",
    ),
    EvalDocument(
        "call_summary",
        "Client call summary and tasks",
        "Productivity",
        "Client call transcription, meeting summary, decision extraction, follow-up task creation, CRM notes, and quality review for consulting teams.",
    ),
    EvalDocument(
        "finance_forecast",
        "Finance forecast copilot",
        "Finance",
        "Finance forecasting assistant that reviews revenue data, flags anomalies, explains cost drivers, prepares monthly variance notes, and keeps humans in approval loops.",
    ),
    EvalDocument(
        "hr_screening",
        "HR screening assistant",
        "HR",
        "HR recruiting assistant for resume screening, interview question suggestions, candidate shortlists, bias review, and recruiter handoff policies.",
    ),
    EvalDocument(
        "manufacturing_quality",
        "Manufacturing quality inspection",
        "Manufacturing",
        "Manufacturing quality inspection with computer vision, defect detection, production line alerts, root-cause notes, and operator review before rejection.",
    ),
    EvalDocument(
        "legal_contract_review",
        "Legal contract review copilot",
        "Legal",
        "Legal contract review copilot that identifies risky clauses, compares templates, summarizes obligations, and routes high-risk agreements to counsel.",
    ),
    EvalDocument(
        "inventory_demand",
        "Retail inventory demand planning",
        "Retail",
        "Retail inventory planning using demand forecasting, stockout alerts, replenishment suggestions, seasonal trends, and store manager review.",
    ),
    EvalDocument(
        "customer_feedback",
        "Customer feedback analytics",
        "Analytics",
        "Customer feedback analytics for survey comments, sentiment clusters, churn signals, feature requests, and executive summary dashboards.",
    ),
    EvalDocument(
        "knowledge_base",
        "Internal knowledge base search",
        "Knowledge Management",
        "Internal knowledge base search over policies, playbooks, case notes, onboarding guides, permissions, citations, and answer confidence warnings.",
    ),
)


PORTFOLIO_QUESTIONS: tuple[EvalQuestion, ...] = (
    EvalQuestion("q01", "How can an online school reduce support tickets without hurting learner response quality?", ("support_chatbot",)),
    EvalQuestion("q02", "Which AI case fits FAQ automation, ticket triage, and escalation rules for customer support?", ("support_chatbot",)),
    EvalQuestion("q03", "What should we retrieve for document processing in a consulting company?", ("document_processing",)),
    EvalQuestion("q04", "Find a case about extracting requirements from PDFs and classifying contracts.", ("document_processing",)),
    EvalQuestion("q05", "What is a practical CRM agent pilot for a small sales team?", ("sales_crm_agent",)),
    EvalQuestion("q06", "Which case covers lead scoring, follow-up emails, and stalled deals?", ("sales_crm_agent",)),
    EvalQuestion("q07", "Which AI workflow is realistic for a marketing agency with limited budget?", ("marketing_content",)),
    EvalQuestion("q08", "Find a case for campaign briefs, SEO clustering, and creative variants.", ("marketing_content",)),
    EvalQuestion("q09", "How can consultants summarize client calls and create follow-up tasks?", ("call_summary",)),
    EvalQuestion("q10", "Which case covers transcription, meeting summary, and CRM notes?", ("call_summary",)),
    EvalQuestion("q11", "What AI assistant helps finance teams with revenue forecasts and variance notes?", ("finance_forecast",)),
    EvalQuestion("q12", "Find a case for anomaly flags, cost drivers, and monthly financial review.", ("finance_forecast",)),
    EvalQuestion("q13", "Which AI case supports HR resume screening and interview question suggestions?", ("hr_screening",)),
    EvalQuestion("q14", "Find the recruiting workflow with candidate shortlists and bias review.", ("hr_screening",)),
    EvalQuestion("q15", "What AI use case detects manufacturing defects on a production line?", ("manufacturing_quality",)),
    EvalQuestion("q16", "Which case covers computer vision quality inspection and operator review?", ("manufacturing_quality",)),
    EvalQuestion("q17", "Find a legal AI case for risky clauses and contract obligations.", ("legal_contract_review",)),
    EvalQuestion("q18", "Which copilot compares contract templates and routes high-risk agreements to counsel?", ("legal_contract_review",)),
    EvalQuestion("q19", "What case helps retail teams forecast demand and prevent stockouts?", ("inventory_demand",)),
    EvalQuestion("q20", "Find inventory replenishment suggestions using seasonal trends.", ("inventory_demand",)),
    EvalQuestion("q21", "Which case analyzes customer feedback, sentiment clusters, and churn signals?", ("customer_feedback",)),
    EvalQuestion("q22", "Find a workflow for survey comments, feature requests, and executive dashboards.", ("customer_feedback",)),
    EvalQuestion("q23", "What RAG case searches internal policies, playbooks, and onboarding guides?", ("knowledge_base",)),
    EvalQuestion("q24", "Which knowledge base workflow includes citations and answer confidence warnings?", ("knowledge_base",)),
    EvalQuestion("q25", "Which cases are relevant to support automation and internal knowledge base search?", ("support_chatbot", "knowledge_base")),
)


STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "can",
    "case",
    "covers",
    "find",
    "for",
    "how",
    "is",
    "the",
    "to",
    "what",
    "which",
    "with",
}


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in STOPWORDS
    }


def _score_by_overlap(question: str, document_text: str) -> tuple[float, list[str]]:
    query_tokens = tokenize(question)
    document_tokens = tokenize(document_text)
    overlap = query_tokens & document_tokens
    score = len(overlap) / max(len(query_tokens), 1)
    return score, sorted(overlap)


def retrieve_baseline(
    question: str,
    documents: Iterable[EvalDocument] = PORTFOLIO_DOCUMENTS,
    top_k: int = DEFAULT_TOP_K,
) -> list[dict[str, object]]:
    """Title/category-only baseline used to show retrieval lift."""
    scored = []
    for document in documents:
        score, matched_terms = _score_by_overlap(question, f"{document.title} {document.category}")
        scored.append(
            {
                "doc_id": document.doc_id,
                "title": document.title,
                "category": document.category,
                "score": round(score, 4),
                "matched_terms": matched_terms,
            }
        )
    return sorted(scored, key=lambda item: (-float(item["score"]), str(item["doc_id"])))[:top_k]


def retrieve(question: str, documents: Iterable[EvalDocument] = PORTFOLIO_DOCUMENTS, top_k: int = DEFAULT_TOP_K) -> list[dict[str, object]]:
    """Hybrid-style deterministic retriever over title, category, and full text."""
    scored = []
    for document in documents:
        document_text = f"{document.title} {document.category} {document.text}"
        score, matched_terms = _score_by_overlap(question, document_text)
        scored.append(
            {
                "doc_id": document.doc_id,
                "title": document.title,
                "category": document.category,
                "score": round(score, 4),
                "matched_terms": matched_terms,
            }
        )
    return sorted(scored, key=lambda item: (-float(item["score"]), str(item["doc_id"])))[:top_k]


def precision_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    return len(set(retrieved_ids[:k]) & relevant_ids) / k


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    return len(set(retrieved_ids[:k]) & relevant_ids) / len(relevant_ids)


def _evaluate_retriever(retriever, top_k: int) -> tuple[dict[str, float], list[dict[str, object]]]:
    rows = []
    precision_total = 0.0
    recall_total = 0.0
    for item in PORTFOLIO_QUESTIONS:
        retrieved = retriever(item.question, top_k=top_k)
        retrieved_ids = [str(result["doc_id"]) for result in retrieved]
        relevant_ids = set(item.relevant_doc_ids)
        row_precision = precision_at_k(retrieved_ids, relevant_ids, top_k)
        row_recall = recall_at_k(retrieved_ids, relevant_ids, top_k)
        precision_total += row_precision
        recall_total += row_recall
        rows.append(
            {
                "question_id": item.question_id,
                "question": item.question,
                "relevant_doc_ids": list(item.relevant_doc_ids),
                "retrieved_doc_ids": retrieved_ids,
                "precision_at_5": round(row_precision, 4),
                "recall_at_5": round(row_recall, 4),
                "top_matches": retrieved,
            }
        )

    question_count = len(PORTFOLIO_QUESTIONS)
    return (
        {
            "precision_at_5": round(precision_total / question_count, 4),
            "recall_at_5": round(recall_total / question_count, 4),
        },
        rows,
    )


def run_deterministic_eval(top_k: int = DEFAULT_TOP_K) -> dict[str, object]:
    baseline_metrics, baseline_rows = _evaluate_retriever(retrieve_baseline, top_k)
    hybrid_metrics, hybrid_rows = _evaluate_retriever(retrieve, top_k)
    question_count = len(PORTFOLIO_QUESTIONS)
    return {
        "dataset": {
            "name": "synthetic_portfolio_rag_v1",
            "question_count": question_count,
            "document_count": len(PORTFOLIO_DOCUMENTS),
            "portfolio_safe": True,
        },
        "metrics": hybrid_metrics,
        "baseline_metrics": baseline_metrics,
        "improvement": {
            "precision_at_5_delta": round(hybrid_metrics["precision_at_5"] - baseline_metrics["precision_at_5"], 4),
            "recall_at_5_delta": round(hybrid_metrics["recall_at_5"] - baseline_metrics["recall_at_5"], 4),
        },
        "retrievers": {
            "baseline": "title_category_overlap",
            "improved": "full_text_hybrid_style_overlap",
        },
        "baseline_rows": baseline_rows,
        "rows": hybrid_rows,
    }


def run_llm_judge(eval_result: dict[str, object], model: str | None = None) -> dict[str, object]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"status": "skipped", "reason": "OPENAI_API_KEY is not set"}

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model_name = model or os.getenv("EVAL_JUDGE_MODEL", "gpt-4.1-mini")
        judge_items = [
            {
                "question_id": row["question_id"],
                "question": row["question"],
                "expected": row["relevant_doc_ids"],
                "top_retrieved": row["retrieved_doc_ids"][:1],
            }
            for row in eval_result["rows"]
        ]
        response = client.responses.create(
            model=model_name,
            input=[
                {
                    "role": "system",
                    "content": "Return compact JSON with keys: judged_count, pass_count, notes. Mark pass when the top retrieved id is semantically relevant to the question.",
                },
                {
                    "role": "user",
                    "content": json.dumps(judge_items, ensure_ascii=False),
                },
            ],
        )
        return {
            "status": "completed",
            "model": model_name,
            "summary": response.output_text,
        }
    except Exception as exc:  # pragma: no cover - only used for optional live judging
        return {"status": "skipped", "reason": f"LLM judge unavailable: {exc}"}


def build_report(include_llm_judge: bool = True, top_k: int = DEFAULT_TOP_K) -> dict[str, object]:
    deterministic = run_deterministic_eval(top_k=top_k)
    deterministic["generated_at"] = datetime.now(timezone.utc).isoformat()
    deterministic["llm_judge"] = run_llm_judge(deterministic) if include_llm_judge else {"status": "skipped", "reason": "disabled by --skip-llm"}
    return deterministic


def write_report(report: dict[str, object], output_path: Path = DEFAULT_RESULT_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the offline portfolio RAG eval.")
    parser.add_argument("--output", type=Path, default=DEFAULT_RESULT_PATH, help="Path for the JSON eval report.")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Retrieval depth for precision/recall.")
    parser.add_argument("--skip-llm", action="store_true", help="Disable optional OpenAI LLM-as-judge even when OPENAI_API_KEY exists.")
    args = parser.parse_args()

    report = build_report(include_llm_judge=not args.skip_llm, top_k=args.top_k)
    write_report(report, args.output)
    metrics = report["metrics"]
    judge = report["llm_judge"]
    print(
        json.dumps(
            {
                "dataset": report["dataset"],
                "baseline_metrics": report["baseline_metrics"],
                "metrics": metrics,
                "improvement": report["improvement"],
                "llm_judge": judge,
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
