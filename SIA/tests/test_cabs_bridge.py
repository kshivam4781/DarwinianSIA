"""Tests for CABS bridge (JSON-only merge with SIA2)."""

import json
import random
from pathlib import Path

from sia.evolution.cabs_bridge import load_cabs_agenda, load_mutation_bias
from sia.evolution.dna import AgentDNA, MEMORY_MODES
from sia.evolution.evolution_prompts import cabs_feedback_addon
from sia.evolution.operators import mutate


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


def _write_memory_contradiction_store(tmp_path: Path) -> Path:
    """Shared fixture: open memory contradiction with two concrete DNA values."""
    store = tmp_path / "belief_store"
    store.mkdir()
    (store / "research_questions.json").write_text(
        json.dumps(
            {
                "research_questions": [
                    {
                        "id": "rq1",
                        "question": "When does memory help?",
                        "contradiction_id": "c1",
                        "dna_field": "memory",
                        "status": "open",
                        "priority": 0.8,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (store / "contradictions.json").write_text(
        json.dumps(
            {
                "contradictions": [
                    {
                        "id": "c1",
                        "topic": "memory",
                        "belief_a": "Agent 0: memory=full_history achieved fitness 0.13",
                        "belief_b": "Agent 1: memory=failure_based achieved fitness 0.20",
                        "status": "open",
                        "detected_at_gen": 2,
                        "priority": 0.9,
                        "metadata": {"agents": [0, 1], "cross_agent": True},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (store / "beliefs.json").write_text(
        json.dumps(
            {
                "beliefs": [
                    {
                        "id": "b1",
                        "belief": "Agent 0: memory=full_history",
                        "topic": "memory",
                        "status": "active",
                        "metadata": {
                            "agent_id": 0,
                            "trait": "memory",
                            "value": "full_history",
                        },
                    },
                    {
                        "id": "b2",
                        "belief": "Agent 1: memory=failure_based",
                        "topic": "memory",
                        "status": "active",
                        "metadata": {
                            "agent_id": 1,
                            "trait": "memory",
                            "value": "failure_based",
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return store


def test_mutation_bias_from_contradiction_not_full_enum(tmp_path):
    """Bias must be contradiction-scoped values, not the entire MEMORY_MODES enum."""
    _write_memory_contradiction_store(tmp_path)

    bias = load_mutation_bias(str(tmp_path))
    assert "memory" in bias
    assert set(bias["memory"]) == {"full_history", "failure_based"}
    assert set(bias["memory"]) != set(MEMORY_MODES)
    assert "short_summary" not in bias["memory"]


def test_cabs_agenda_includes_scoped_dna_feedback_targets(tmp_path):
    """Scoped feedback must list contradiction-scoped DNA candidates (not full enums)."""
    _write_memory_contradiction_store(tmp_path)

    agenda = load_cabs_agenda(str(tmp_path))
    assert "Scoped DNA Feedback Targets" in agenda
    assert "`memory`" in agenda
    assert "`full_history`" in agenda
    assert "`failure_based`" in agenda
    # Must not dump the rest of MEMORY_MODES into feedback targets
    assert "`short_summary`" not in agenda
    assert "`none`" not in agenda

    addon = cabs_feedback_addon(agenda)
    assert "Scoped DNA Feedback Targets" in addon
    assert "consistent with at least one listed candidate" in addon


def test_mutation_bias_rq_only_without_values_is_empty(tmp_path):
    """Open RQ with dna_field but no concrete values must NOT dump the full enum."""
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
    assert bias == {}


def test_mutation_bias_reads_agent_dna_files(tmp_path):
    store = tmp_path / "belief_store"
    store.mkdir()
    (store / "research_questions.json").write_text(
        json.dumps(
            {
                "research_questions": [
                    {
                        "id": "rq1",
                        "question": "Tool strategy disagreement",
                        "contradiction_id": "c1",
                        "dna_field": "tool_strategy",
                        "status": "open",
                        "priority": 0.7,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (store / "contradictions.json").write_text(
        json.dumps(
            {
                "contradictions": [
                    {
                        "id": "c1",
                        "topic": "tool_use",
                        "belief_a": "tools help",
                        "belief_b": "tools hurt",
                        "status": "open",
                        "detected_at_gen": 1,
                        "metadata": {"agents": [0, 1], "cross_agent": True},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "gen_1" / "agent_0").mkdir(parents=True)
    (tmp_path / "gen_1" / "agent_1").mkdir(parents=True)
    AgentDNA(tool_strategy="aggressive").save(str(tmp_path / "gen_1" / "agent_0" / "agent_dna.json"))
    AgentDNA(tool_strategy="minimal").save(str(tmp_path / "gen_1" / "agent_1" / "agent_dna.json"))

    bias = load_mutation_bias(str(tmp_path))
    assert set(bias["tool_strategy"]) == {"aggressive", "minimal"}


def test_biased_mutate_skews_memory_vs_uniform():
    """H2 gate: contradiction bias must skew trait distribution vs unbiased mutation."""
    bias = {"memory": ["failure_based", "full_history"]}
    biased_counts = {m: 0 for m in MEMORY_MODES}
    uniform_counts = {m: 0 for m in MEMORY_MODES}
    n = 200
    for i in range(n):
        dna = AgentDNA(memory="short_summary")
        biased = mutate(dna, mutation_rate=1.0, rng=random.Random(1000 + i), bias=bias)
        uniform = mutate(dna, mutation_rate=1.0, rng=random.Random(1000 + i), bias=None)
        biased_counts[biased.memory] += 1
        uniform_counts[uniform.memory] += 1

    biased_mass = biased_counts["failure_based"] + biased_counts["full_history"]
    uniform_mass = uniform_counts["failure_based"] + uniform_counts["full_history"]
    assert biased_mass == n
    assert biased_counts["short_summary"] == 0
    assert biased_mass > uniform_mass
