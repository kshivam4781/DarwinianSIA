"""Ground open research questions with Tavily web search."""

from __future__ import annotations

from typing import Any

from cabs.belief_store import BeliefStore
from cabs.evidence_store import EvidenceStore
from cabs.tavily_client import TavilyClient


def build_search_query(question: dict[str, Any], task_hint: str = "") -> str:
    """Turn a research question into a Tavily-friendly query."""
    topic = question.get("topic") or "AI agent"
    base = question.get("question") or f"When does {topic} help self-improving AI agents?"
    # Keep queries short for cost control
    short = base.split("Contradiction:")[0].strip()
    if task_hint:
        return f"{short} ({task_hint})"
    return short[:240]


def apply_evidence_to_beliefs(
    store: BeliefStore,
    research_question_id: str,
    topic: str,
    evidence_summary: str,
) -> int:
    """Boost confidence on beliefs matching the grounded topic."""
    beliefs = store.load_beliefs()
    updated = 0
    for belief in beliefs:
        if belief.get("topic") != topic or belief.get("status") != "active":
            continue
        meta = dict(belief.get("metadata") or {})
        if meta.get("tavily_rq_id") == research_question_id:
            continue
        confidence = float(belief.get("confidence", 0.5))
        belief["confidence"] = round(min(confidence + 0.08, 0.98), 3)
        meta["tavily_rq_id"] = research_question_id
        meta["external_evidence"] = evidence_summary[:400]
        belief["metadata"] = meta
        updated += 1
    if updated:
        store.save_beliefs(beliefs)
    return updated


def ground_open_questions(
    belief_store_root: str,
    *,
    generation: int,
    max_calls: int = 10,
    task_hint: str = "",
    client: TavilyClient | None = None,
) -> dict[str, Any]:
    """
    Search Tavily for open research questions without existing evidence.

    Returns summary dict for cabs_report.json.
    """
    store = BeliefStore(belief_store_root)
    evidence_store = EvidenceStore(belief_store_root)
    tavily = client or TavilyClient()

    if not tavily.configured:
        return {"enabled": False, "reason": "TAVILY_API_KEY not set", "calls": 0, "grounded": []}

    open_questions = store.get_open_research_questions()
    calls_before = evidence_store.calls_used()
    remaining = max(0, max_calls - calls_before)
    grounded: list[dict[str, Any]] = []

    for question in open_questions:
        if remaining <= 0:
            break
        rq_id = question.get("id")
        if not rq_id or evidence_store.has_evidence(rq_id):
            continue

        query = build_search_query(question, task_hint=task_hint)
        try:
            result = tavily.search(query, max_results=3)
        except RuntimeError as exc:
            grounded.append({"research_question_id": rq_id, "error": str(exc)})
            break

        evidence_store.record_call(rq_id, query, generation)
        evidence_store.save_evidence(
            rq_id,
            query=query,
            generation=generation,
            answer=result.answer,
            results=result.results,
        )
        remaining -= 1

        summary_parts = []
        if result.answer:
            summary_parts.append(result.answer)
        for snippet in result.results[:2]:
            if snippet.get("content"):
                summary_parts.append(snippet["content"][:200])
        summary = " | ".join(summary_parts)[:500]

        beliefs_updated = apply_evidence_to_beliefs(
            store,
            rq_id,
            question.get("topic") or "planning",
            summary,
        )

        # Attach evidence pointer on the research question
        questions = store.load_research_questions()
        for q in questions:
            if q.get("id") == rq_id:
                q["tavily_grounded"] = True
                q["evidence_file"] = f"evidence/{rq_id}.json"
                if summary:
                    q["external_summary"] = summary[:300]
        store.save_research_questions(questions)

        grounded.append(
            {
                "research_question_id": rq_id,
                "query": query,
                "snippets": len(result.results),
                "beliefs_updated": beliefs_updated,
                "has_answer": bool(result.answer),
            }
        )

    calls_after = evidence_store.calls_used()
    return {
        "enabled": True,
        "calls_this_step": calls_after - calls_before,
        "calls_total": calls_after,
        "max_calls": max_calls,
        "grounded": grounded,
    }
