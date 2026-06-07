"""Tests for CABS bridge (JSON-only merge with SIA2)."""

import json
from pathlib import Path

from sia.evolution.cabs_bridge import load_cabs_agenda, load_mutation_bias
from sia.evolution.evolution_prompts import cabs_feedback_addon


def test_load_cabs_agenda(tmp_path):
    store = tmp_path / "belief_store"
    store.mkdir()
    (store / "contradictions.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "contradictions": [
                    {
                        "id": "c1",
                        "topic": "memory",
                        "belief_a": "memory helps",
                        "belief_b": "memory hurts",
                        "priority": 0.9,
                        "status": "open",
                        "metadata": {"agents": [0, 1], "cross_agent": True},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (store / "approved_techniques.json").write_text(
        json.dumps(
            {
                "techniques": [
                    {
                        "technique": "stratified_memory",
                        "implementation_hint": "Gate memory by difficulty",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    agenda = load_cabs_agenda(str(tmp_path))
    assert "memory" in agenda
    assert "stratified_memory" in agenda
    assert "MUST implement" in agenda

    addon = cabs_feedback_addon(agenda)
    assert addon.startswith("\n## CABS")


def test_mutation_bias_from_research_questions(tmp_path):
    store = tmp_path / "belief_store"
    store.mkdir()
    (store / "research_questions.json").write_text(
        json.dumps(
            {
                "research_questions": [
                    {
                        "id": "rq1",
                        "question": "When does memory help?",
                        "dna_field": "memory",
                        "status": "open",
                        "priority": 0.8,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    bias = load_mutation_bias(str(tmp_path))
    assert "memory" in bias
    assert "failure_based" in bias["memory"]
