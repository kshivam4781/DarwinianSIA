"""Research Agent: rank contradictions and attach experiment plans."""

from __future__ import annotations

from typing import Any

from pathlib import Path

from cabs.committee_store import CommitteeStore
from cabs.evidence_store import EvidenceStore
from cabs.experiment_planner import plan_experiments


def rank_contradictions(contradictions: list[dict]) -> list[dict]:
    return sorted(contradictions, key=lambda c: float(c.get("priority", 0)), reverse=True)


def rank_research_questions(questions: list[dict]) -> list[dict]:
    return sorted(questions, key=lambda q: float(q.get("priority", 0)), reverse=True)


def enrich_research_questions(questions: list[dict], belief_store_root: str | Path | None = None) -> list[dict]:
    evidence_store = EvidenceStore(belief_store_root) if belief_store_root else None
    enriched = []
    for question in questions:
        item = dict(question)
        if not item.get("experiments"):
            item["experiments"] = plan_experiments(item)
        if evidence_store and item.get("id"):
            ev = evidence_store.load_for_question(item["id"])
            if ev:
                item["external_evidence"] = {
                    "answer": ev.get("answer"),
                    "snippets": ev.get("results", [])[:2],
                    "query": ev.get("query"),
                }
        enriched.append(item)
    return enriched


def build_research_agenda(
    contradictions: list[dict],
    questions: list[dict],
    top_k: int = 3,
    belief_store_root: str | Path | None = None,
) -> dict[str, Any]:
    ranked_contradictions = rank_contradictions([c for c in contradictions if c.get("status") == "open"])
    ranked_questions = rank_research_questions([q for q in questions if q.get("status") == "open"])
    enriched_questions = enrich_research_questions(ranked_questions[:top_k], belief_store_root)

    external = []
    approved_techniques: list[dict] = []
    if belief_store_root:
        external = EvidenceStore(belief_store_root).load_all()
        approved_techniques = CommitteeStore(belief_store_root).load_approved()

    return {
        "active_contradictions": ranked_contradictions[:top_k],
        "research_questions": enriched_questions,
        "external_evidence_count": len(external),
        "approved_techniques": approved_techniques[:top_k],
        "guidance": (
            "Prioritize experiments that reduce uncertainty, not only benchmark score. "
            "Resolve contradictions before applying broad architectural changes."
        ),
    }
