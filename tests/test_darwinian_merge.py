"""Tests for CABS + Darwinian merge (Section 20)."""

import json
from pathlib import Path

from cabs.belief_engine import BeliefEngine
from cabs.belief_extractor import (
    ingest_civilization,
    is_population_layout,
    load_generation_context,
)
from cabs.contradiction_detector import detect_population_contradictions
from cabs.dna_mapping import topic_to_dna_field
from cabs.research_question_generator import generate_research_questions


def _make_darwinian_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "runs" / "run_311"
    gen_dir = run_dir / "gen_2"
    for agent_id, memory, fitness in ((0, "full_history", 0.133), (1, "failure_based", 0.20)):
        agent_dir = gen_dir / f"agent_{agent_id}"
        agent_dir.mkdir(parents=True)
        (agent_dir / "agent_dna.json").write_text(
            json.dumps(
                {
                    "planning_style": "stepwise",
                    "reflection": True,
                    "tool_strategy": "minimal",
                    "retry_policy": "generic",
                    "memory": memory,
                    "confidence_threshold": 0.75,
                    "prompt_structure": "detailed",
                }
            ),
            encoding="utf-8",
        )
        (agent_dir / "results.json").write_text(
            json.dumps({"accuracy": fitness}),
            encoding="utf-8",
        )
        (agent_dir / "target_agent.py").write_text(
            f"# agent {agent_id}\nmemory = '{memory}'\n",
            encoding="utf-8",
        )
    (run_dir / "civilization.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "mode": "darwinian",
                "trait_insights": {
                    "memory": [["failure_based", 2]],
                    "tool_strategy": [["minimal", 1]],
                },
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def test_topic_to_dna_field_mapping():
    assert topic_to_dna_field("tool_use") == "tool_strategy"
    assert topic_to_dna_field("planning") == "planning_style"
    assert topic_to_dna_field("memory") == "memory"


def test_population_layout_detection(tmp_path):
    run_dir = _make_darwinian_run(tmp_path)
    assert is_population_layout(run_dir / "gen_2")


def test_cross_agent_contradiction(tmp_path):
    run_dir = _make_darwinian_run(tmp_path)
    ctx = load_generation_context(run_dir, 2)
    assert ctx.is_population
    assert len(ctx.agents) == 2

    engine = BeliefEngine.for_run(run_dir)
    result = engine.process_generation(run_dir, 2)

    assert result.beliefs_added > 0
    assert result.contradictions_added >= 1

    contradictions = engine.store.load_contradictions()
    cross = [c for c in contradictions if (c.get("metadata") or {}).get("cross_agent")]
    assert len(cross) >= 1
    cross_topics = {c["topic"] for c in cross}
    assert "memory" in cross_topics


def test_research_question_dna_field():
    beliefs = [
        {
            "id": "b1",
            "belief": "Agent 0: memory=full_history good",
            "topic": "memory",
            "polarity": "positive",
            "confidence": 0.8,
            "status": "active",
            "metadata": {"agent_id": 0},
        },
        {
            "id": "b2",
            "belief": "Agent 1: memory=failure_based bad for full_history",
            "topic": "memory",
            "polarity": "negative",
            "confidence": 0.8,
            "status": "active",
            "metadata": {"agent_id": 1},
        },
    ]
    contradictions = detect_population_contradictions(beliefs, generation=2)
    assert len(contradictions) == 1
    questions = generate_research_questions([contradictions[0].to_dict()])
    assert questions[0].dna_field == "memory"


def test_civilization_ingest_dict_format(tmp_path):
    run_dir = _make_darwinian_run(tmp_path)
    beliefs = ingest_civilization(run_dir)
    assert any("failure_based" in b.belief for b in beliefs)
    assert beliefs[0].metadata.get("source") == "civilization.json"


def test_merge_contract_schema_version(tmp_path):
    run_dir = _make_darwinian_run(tmp_path)
    engine = BeliefEngine.for_run(run_dir)
    engine.process_generation(run_dir, 2)
    beliefs_doc = json.loads((run_dir / "belief_store" / "beliefs.json").read_text(encoding="utf-8"))
    assert beliefs_doc.get("schema_version") == "1.0"
