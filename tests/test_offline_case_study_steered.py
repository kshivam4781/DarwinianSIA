"""Case-study extractor must score H2 DNA skew after delay-all steering (gen≥3)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "SIA"))

from offline_bvd_case_study import (  # noqa: E402
    FIRST_STEERED_GEN,
    extract_case_study,
    preferred_share,
)


def _write_agent(run_dir: Path, gen: int, agent_id: int, *, trait: str, fitness: float) -> None:
    agent = run_dir / f"gen_{gen}" / f"agent_{agent_id}"
    agent.mkdir(parents=True, exist_ok=True)
    (agent / "agent_dna.json").write_text(
        json.dumps(
            {
                "planning_style": trait,
                "reflection": True,
                "tool_strategy": "selective",
                "retry_policy": "generic",
                "memory": "short_summary",
                "confidence_threshold": 0.75,
                "prompt_structure": "detailed",
                "technique_seeds": [],
            }
        ),
        encoding="utf-8",
    )
    (agent / "results.json").write_text(
        json.dumps({"accuracy": fitness, "eval_subset": 3}),
        encoding="utf-8",
    )


def test_preferred_share_helper():
    traits = [{"trait": "stepwise"}, {"trait": "direct"}, {"trait": "stepwise"}, {"trait": "hierarchical"}]
    assert preferred_share(traits, "stepwise") == 0.5
    assert preferred_share([], "stepwise") is None


def test_extract_case_study_measures_post_steering_skew(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run_1833"
    store = run_dir / "belief_store"
    store.mkdir(parents=True)

    # Gen1: contradiction sides present; gen2 fair (low preferred); gen3 steered (high preferred).
    _write_agent(run_dir, 1, 0, trait="direct", fitness=0.17)
    _write_agent(run_dir, 1, 1, trait="stepwise", fitness=0.22)
    _write_agent(run_dir, 1, 2, trait="hierarchical", fitness=0.26)
    _write_agent(run_dir, 1, 3, trait="direct", fitness=0.18)

    _write_agent(run_dir, 2, 0, trait="direct", fitness=0.20)
    _write_agent(run_dir, 2, 1, trait="hierarchical", fitness=0.27)
    _write_agent(run_dir, 2, 2, trait="hierarchical", fitness=0.25)
    _write_agent(run_dir, 2, 3, trait="stepwise", fitness=0.24)  # share 0.25

    _write_agent(run_dir, 3, 0, trait="stepwise", fitness=0.30)
    _write_agent(run_dir, 3, 1, trait="stepwise", fitness=0.31)
    _write_agent(run_dir, 3, 2, trait="stepwise", fitness=0.29)
    _write_agent(run_dir, 3, 3, trait="direct", fitness=0.21)  # share 0.75

    (store / "contradictions.json").write_text(
        json.dumps(
            {
                "contradictions": [
                    {
                        "topic": "planning",
                        "belief_a": "Agent 1: planning_style=stepwise achieved fitness 0.22",
                        "belief_b": "Agent 0: planning_style=direct achieved fitness 0.17",
                        "priority": 0.9,
                        "status": "open",
                        "metadata": {"agents": [1, 0]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (store / "beliefs.json").write_text(json.dumps({"beliefs": []}), encoding="utf-8")
    (store / "research_questions.json").write_text(
        json.dumps({"research_questions": []}), encoding="utf-8"
    )

    monkeypatch.setattr(
        "offline_bvd_case_study.load_mutation_bias",
        lambda _run: {"planning_style": ["stepwise", "direct"]},
    )

    case = extract_case_study(run_dir)
    assert case is not None
    assert case["first_steered_gen"] == FIRST_STEERED_GEN == 3
    assert case["steered_gen"] == 3
    assert case["gen2_preferred_share"] == 0.25
    assert case["steered_preferred_share"] == 0.75
    assert case["preferred_share_by_gen"]["2"] == 0.25
    assert case["preferred_share_by_gen"]["3"] == 0.75
    # Lift uses steered preferred mean vs gen1 loser mean.
    assert case["fitness_lift"] is not None
    assert case["fitness_lift"] > 0
