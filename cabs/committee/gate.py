"""Run committee reviews on Tavily-grounded technique candidates."""

from __future__ import annotations

from typing import Any

from cabs.belief_store import BeliefStore
from cabs.committee.agents import CommitteeDecision, deliberate
from cabs.committee.techniques import extract_technique_candidates
from cabs.committee_store import CommitteeStore
from cabs.evidence_store import EvidenceStore


def _decision_to_record(decision: CommitteeDecision, candidate: dict[str, Any], generation: int) -> dict[str, Any]:
    vote_map = {v.role: v.vote for v in decision.votes}
    rationales = {v.role: v.rationale for v in decision.votes}
    return {
        "technique": decision.technique,
        "task": decision.task,
        "topic": candidate.get("topic"),
        "research_question_id": decision.research_question_id,
        "generation": generation,
        "status": decision.status,
        "belief": decision.belief_text,
        "implementation_hint": decision.implementation_hint,
        "confidence": candidate.get("confidence", 0.7),
        "committee_vote": vote_map,
        "rationales": rationales,
        "evidence_summary": candidate.get("evidence_summary", ""),
    }


def run_committee_reviews(
    belief_store_root: str,
    *,
    generation: int = 0,
    max_reviews: int = 5,
    task_hint: str = "",
    use_llm: bool = True,
    require_evidence: bool = True,
) -> dict[str, Any]:
    """
    Review technique candidates derived from Tavily evidence.

    Writes approved_techniques.json / rejected_techniques.json and
    promotes approvals into beliefs.json.
    """
    store = BeliefStore(belief_store_root)
    committee_store = CommitteeStore(belief_store_root)
    evidence_store = EvidenceStore(belief_store_root)

    evidence_files = evidence_store.load_all()
    if require_evidence and not evidence_files:
        return {"enabled": False, "reason": "no Tavily evidence — run ground first", "approved": [], "rejected": []}

    questions = {q["id"]: q for q in store.load_research_questions()}
    approved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    reviews_run = 0

    for evidence in evidence_files:
        if reviews_run >= max_reviews:
            break
        rq_id = evidence.get("research_question_id")
        rq = questions.get(rq_id, {})
        candidates = extract_technique_candidates(evidence, research_question=rq, task_hint=task_hint)

        for candidate in candidates:
            if reviews_run >= max_reviews:
                break
            technique = candidate.get("technique")
            if committee_store.already_reviewed(technique, rq_id):
                continue

            decision = deliberate(candidate, task_hint=task_hint, use_llm=use_llm)
            record = _decision_to_record(decision, candidate, generation)
            committee_store.record_review(technique, rq_id, decision.status)
            reviews_run += 1

            if decision.status == "approved":
                committee_store.append_approved(record)
                committee_store.promote_to_beliefs(store, record, generation)
                approved.append(record)
            else:
                committee_store.append_rejected(record)
                rejected.append(record)

    return {
        "enabled": True,
        "reviews_run": reviews_run,
        "max_reviews": max_reviews,
        "approved": approved,
        "rejected": rejected,
        "approved_count": len(committee_store.load_approved()),
        "rejected_count": len(committee_store.load_rejected()),
    }
