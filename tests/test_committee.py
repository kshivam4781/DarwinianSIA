"""Tests for committee gating."""

import json
from pathlib import Path
from unittest.mock import patch

from cabs.committee.agents import CommitteeDecision, CommitteeVote, deliberate
from cabs.committee.gate import run_committee_reviews
from cabs.committee.techniques import extract_technique_candidates
from cabs.committee_store import CommitteeStore
from cabs.prompt_injection import format_cabs_context


SAMPLE_EVIDENCE = {
    "research_question_id": "rq_mem",
    "query": "memory help hurt",
    "answer": "Working memory and proactive interference affect chess task performance on easy vs hard slices.",
    "results": [
        {
            "title": "Working Memory in Chess",
            "url": "https://example.com",
            "content": "Stratified evaluation on easy and hard tasks with episodic memory controls.",
            "score": 0.9,
        }
    ],
}


def test_extract_technique_candidates_from_memory_evidence():
    candidates = extract_technique_candidates(
        SAMPLE_EVIDENCE,
        research_question={"id": "rq_mem", "topic": "memory"},
        task_hint="longcot-chess",
    )
    names = {c["technique"] for c in candidates}
    assert "stratified_memory" in names or "working_memory_split" in names


def test_deliberate_heuristic_offline():
    candidate = {
        "technique": "stratified_memory",
        "title": "Stratified memory",
        "topic": "memory",
        "task": "longcot-chess",
        "confidence": 0.8,
        "implementation_hint": "Disable memory on easy slice; enable on hard slice.",
        "research_question_id": "rq_mem",
    }
    decision = deliberate(candidate, task_hint="longcot-chess", use_llm=False)
    assert decision.status in ("approved", "rejected")
    assert len(decision.votes) == 3


def test_run_committee_reviews_writes_approved_and_beliefs(tmp_path):
    store_root = tmp_path / "belief_store"
    store_root.mkdir()
    (store_root / "evidence").mkdir()
    (store_root / "evidence" / "rq_mem.json").write_text(json.dumps(SAMPLE_EVIDENCE), encoding="utf-8")
    (store_root / "research_questions.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "research_questions": [
                    {
                        "id": "rq_mem",
                        "question": "When does memory help?",
                        "topic": "memory",
                        "status": "open",
                        "contradiction_id": "c1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (store_root / "beliefs.json").write_text(
        json.dumps({"schema_version": "1.0", "beliefs": []}),
        encoding="utf-8",
    )

    fake_decision = CommitteeDecision(
        technique="stratified_memory",
        status="approved",
        votes=[
            CommitteeVote("proponent", "approve", "yes"),
            CommitteeVote("skeptic", "approve", "ok"),
            CommitteeVote("replicator", "approve", "ok"),
        ],
        implementation_hint="Disable memory on easy tasks.",
        task="longcot-chess",
        research_question_id="rq_mem",
        belief_text="Technique stratified_memory may help on longcot-chess.",
    )

    with patch("cabs.committee.gate.deliberate", return_value=fake_decision):
        summary = run_committee_reviews(
            str(store_root),
            generation=3,
            max_reviews=3,
            task_hint="longcot-chess",
            use_llm=False,
        )

    assert summary["enabled"] is True
    assert len(summary["approved"]) >= 1
    committee = CommitteeStore(store_root)
    assert len(committee.load_approved()) >= 1
    assert len(committee.load_rejected()) >= 0


def test_prompt_includes_approved_techniques():
    agenda = {
        "active_contradictions": [],
        "research_questions": [],
        "approved_techniques": [
            {
                "technique": "stratified_memory",
                "task": "longcot-chess",
                "belief": "Stratified memory may help on longcot-chess.",
                "implementation_hint": "Disable on easy slice.",
                "committee_vote": {
                    "proponent": "approve",
                    "skeptic": "approve",
                    "replicator": "approve",
                },
            }
        ],
    }
    text = format_cabs_context(agenda)
    assert "Committee-Approved Techniques" in text
    assert "stratified_memory" in text
