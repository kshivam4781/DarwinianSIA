"""Tests for Condition D --cabs-inline analyze hook."""

import json
from pathlib import Path

import pytest

from sia.evolution.cabs_bridge import load_mutation_bias
from sia.evolution.cabs_inline import ensure_cabs_importable, run_cabs_inline
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
