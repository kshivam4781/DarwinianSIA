"""Tests for Condition D --cabs-inline analyze hook."""

import json
from pathlib import Path

import pytest

from sia.evolution.cabs_bridge import load_mutation_bias
from sia.evolution.cabs_inline import (
    _epistemic_value,
    ensure_cabs_importable,
    run_cabs_inline,
)
from sia.evolution.dna import MEMORY_MODES


def _make_darwinian_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "runs" / "run_1401"
    gen_dir = run_dir / "gen_1"
    for agent_id, memory, fitness in ((0, "full_history", 0.10), (1, "failure_based", 0.25)):
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
            f"# agent {agent_id}\n# memory={memory} helps when failures recur\n",
            encoding="utf-8",
        )
        (agent_dir / "improvement.md").write_text(
            f"Agent {agent_id}: memory={memory} is useful because errors recur on hard items.\n",
            encoding="utf-8",
        )
    return run_dir


@pytest.mark.skipif(not ensure_cabs_importable(), reason="cabs package not available in this env")
def test_cabs_inline_writes_belief_store_and_epistemic_value(tmp_path):
    run_dir = _make_darwinian_run(tmp_path)
    summary = run_cabs_inline(str(run_dir), generation=1, task_hint="gpqa")

    assert summary["mode"] == "inprocess"
    assert summary["beliefs_added"] >= 1
    store = run_dir / "belief_store"
    assert (store / "beliefs.json").exists()
    assert (store / "epistemic_value.jsonl").exists()
    line = (store / "epistemic_value.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1]
    row = json.loads(line)
    assert row["generation"] == 1
    assert "epistemic_value" in row

    # Cross-agent DNA disagreement should yield contradictions / RQs on a second pass if needed
    if summary["contradictions_added"] == 0:
        # DNA-derived beliefs may need opposing polarities; ensure store is non-empty either way
        beliefs = json.loads((store / "beliefs.json").read_text(encoding="utf-8"))
        assert len(beliefs.get("beliefs", [])) >= 1


@pytest.mark.skipif(not ensure_cabs_importable(), reason="cabs package not available in this env")
def test_cabs_inline_enables_scoped_mutation_bias(tmp_path):
    """After inline analyze, open RQs + contradiction DNA should scope bias ≠ full enum."""
    run_dir = _make_darwinian_run(tmp_path)
    # Seed an explicit contradiction + RQ so bias is deterministic even if extractor is sparse
    store = run_dir / "belief_store"
    store.mkdir(parents=True)
    (store / "contradictions.json").write_text(
        json.dumps(
            {
                "contradictions": [
                    {
                        "id": "c1",
                        "topic": "memory",
                        "belief_a": "memory=full_history helps",
                        "belief_b": "memory=failure_based helps",
                        "priority": 0.9,
                        "status": "open",
                        "detected_at_gen": 1,
                        "metadata": {"agents": [0, 1], "cross_agent": True},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (store / "research_questions.json").write_text(
        json.dumps(
            {
                "research_questions": [
                    {
                        "id": "rq1",
                        "question": "Which memory mode wins under contradiction?",
                        "contradiction_id": "c1",
                        "dna_field": "memory",
                        "status": "open",
                        "priority": 0.85,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (store / "beliefs.json").write_text(json.dumps({"beliefs": []}), encoding="utf-8")

    summary = run_cabs_inline(str(run_dir), generation=1)
    assert summary["mode"] == "inprocess"

    bias = load_mutation_bias(str(run_dir))
    assert "memory" in bias
    assert set(bias["memory"]).issubset(set(MEMORY_MODES))
    assert set(bias["memory"]) != set(MEMORY_MODES)
    assert "full_history" in bias["memory"] or "failure_based" in bias["memory"]


def test_epistemic_value_varies_with_age_and_knowledge_gain(tmp_path):
    """Offline H5 needs non-constant epistemic_value across gens (age decay + flow)."""
    store = tmp_path / "belief_store"
    store.mkdir(parents=True)
    (store / "contradictions.json").write_text(
        json.dumps(
            {
                "contradictions": [
                    {
                        "id": "c1",
                        "topic": "memory",
                        "priority": 1.0,
                        "status": "open",
                        "detected_at_gen": 1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (store / "research_questions.json").write_text(
        json.dumps(
            {
                "research_questions": [
                    {
                        "id": "rq1",
                        "priority": 0.8,
                        "status": "open",
                        # No detected_at_gen — must inherit age from contradiction c1
                        "contradiction_id": "c1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    g1 = _epistemic_value(store, 1, knowledge_gain=0.5)
    g2 = _epistemic_value(store, 2, knowledge_gain=0.0)
    g3 = _epistemic_value(store, 3, knowledge_gain=0.0)

    assert g1["epistemic_value"] != g2["epistemic_value"]
    assert g2["epistemic_value"] != g3["epistemic_value"]
    # Stale open stock decays without new knowledge_gain
    assert g3["epistemic_value"] < g2["epistemic_value"] < g1["epistemic_value"]
    # RQ without detected_at_gen inherits contradiction age (both sides decay)
    assert g2["rq_priority_sum"] < g1["rq_priority_sum"]
    assert g2["contradiction_priority_sum"] < g1["contradiction_priority_sum"]
    assert g2["rq_priority_sum"] == pytest.approx(0.8 * 0.85)
    # Knowledge gain must move the series (gen1 includes flow); stock is soft-weighted
    assert g1["knowledge_gain_score"] == pytest.approx(0.5)
    soft_stock_g1 = 0.35 * (
        g1["contradiction_priority_sum"] + g1["rq_priority_sum"]
    )
    assert g1["epistemic_value"] == pytest.approx(soft_stock_g1 + 0.5, abs=1e-9)
    # No run_dir → steering/discovery stay zero (age/flow-only path)
    assert g1["steering_opportunity"] == pytest.approx(0.0)
    assert g1["discovery_opportunity"] == pytest.approx(0.0)


def test_epistemic_value_includes_steering_opportunity(tmp_path):
    """H5 epi should rise when preferred DNA is under-adopted and fall as it dominates."""
    run_dir = tmp_path / "run_steer"
    store = run_dir / "belief_store"
    store.mkdir(parents=True)
    (store / "contradictions.json").write_text(
        json.dumps(
            {
                "contradictions": [
                    {
                        "id": "c_tool",
                        "topic": "tool_use",
                        "priority": 1.0,
                        "status": "open",
                        "detected_at_gen": 1,
                        "belief_a": (
                            "Agent 0: tool_strategy=selective achieved fitness 0.80 "
                            "(population mean 0.40)"
                        ),
                        "belief_b": (
                            "Agent 1: tool_strategy=aggressive achieved fitness 0.20 "
                            "(population mean 0.40)"
                        ),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (store / "research_questions.json").write_text(
        json.dumps({"research_questions": []}),
        encoding="utf-8",
    )

    # Gen1: preferred selective under-adopted (1/4)
    gen1 = run_dir / "gen_1"
    for agent_id, tool in (
        (0, "selective"),
        (1, "aggressive"),
        (2, "aggressive"),
        (3, "minimal"),
    ):
        agent_dir = gen1 / f"agent_{agent_id}"
        agent_dir.mkdir(parents=True)
        (agent_dir / "agent_dna.json").write_text(
            json.dumps(
                {
                    "planning_style": "stepwise",
                    "reflection": True,
                    "tool_strategy": tool,
                    "retry_policy": "generic",
                    "memory": "none",
                    "confidence_threshold": 0.5,
                    "prompt_structure": "single",
                }
            ),
            encoding="utf-8",
        )

    # Gen2: preferred selective dominates (3/4) → less remaining opportunity
    gen2 = run_dir / "gen_2"
    for agent_id, tool in (
        (0, "selective"),
        (1, "selective"),
        (2, "selective"),
        (3, "aggressive"),
    ):
        agent_dir = gen2 / f"agent_{agent_id}"
        agent_dir.mkdir(parents=True)
        (agent_dir / "agent_dna.json").write_text(
            json.dumps(
                {
                    "planning_style": "stepwise",
                    "reflection": True,
                    "tool_strategy": tool,
                    "retry_policy": "generic",
                    "memory": "none",
                    "confidence_threshold": 0.5,
                    "prompt_structure": "single",
                }
            ),
            encoding="utf-8",
        )

    g1 = _epistemic_value(store, 1, knowledge_gain=0.0, run_dir=str(run_dir))
    g2 = _epistemic_value(store, 2, knowledge_gain=0.0, run_dir=str(run_dir))

    assert g1["steering_opportunity"] > g2["steering_opportunity"] > 0.0
    # gap=0.60, under_g1=0.75 → steer≈0.45; under_g2=0.25 → steer≈0.15*0.85
    assert g1["steering_opportunity"] == pytest.approx(1.0 * 0.60 * 0.75, abs=1e-9)
    assert g2["steering_opportunity"] == pytest.approx(0.85 * 0.60 * 0.25, abs=1e-9)
    assert g1["epistemic_value"] > g2["epistemic_value"]
    # Steering term must move epistemic_value beyond age-weighted open stock alone
    stock_flow_g1 = (
        g1["contradiction_priority_sum"]
        + g1["rq_priority_sum"]
        + g1["epistemic_flow"]
    )
    assert g1["epistemic_value"] > stock_flow_g1 + 1e-9
