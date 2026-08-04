"""Offline H5 / epistemic_results helpers (no API)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from epistemic_results import (  # noqa: E402
    compute_h5,
    gens_to_threshold,
    spearman_rho,
    summarize_run,
)
from sia.evolution.dna import AgentDNA
from sia.evolution.dry_run import deterministic_fitness, parse_agent_coords


def test_parse_agent_coords():
    agent_id, gen = parse_agent_coords("/tmp/runs/run_1/gen_3/agent_2")
    assert agent_id == 2
    assert gen == 3


def test_deterministic_fitness_varies_by_dna():
    a = AgentDNA(memory="failure_based", tool_strategy="aggressive")
    b = AgentDNA(memory="none", tool_strategy="minimal")
    fa = deterministic_fitness(0, a, 1)
    fb = deterministic_fitness(0, b, 1)
    assert 0.05 <= fa <= 0.95
    assert 0.05 <= fb <= 0.95
    assert fa != fb


def test_deterministic_fitness_transfers_with_dna_traits():
    """Same DNA must score the same across agent_id/generation (offline case study)."""
    dna = AgentDNA(memory="failure_based", tool_strategy="aggressive", planning_style="react")
    f00 = deterministic_fitness(0, dna, 1)
    f17 = deterministic_fitness(1, dna, 7)
    assert f00 == f17
    # Mutating a transferred trait must change fitness (bias can select for it).
    other = AgentDNA(
        memory="full_history",
        tool_strategy=dna.tool_strategy,
        planning_style=dna.planning_style,
        reflection=dna.reflection,
        retry_policy=dna.retry_policy,
        confidence_threshold=dna.confidence_threshold,
        prompt_structure=dna.prompt_structure,
    )
    assert deterministic_fitness(0, other, 1) != f00


def test_spearman_rho_perfect():
    xs = [1.0, 2.0, 3.0, 4.0]
    ys = [10.0, 20.0, 30.0, 40.0]
    rho = spearman_rho(xs, ys)
    assert rho is not None
    assert rho == pytest.approx(1.0, abs=1e-9)


def test_compute_h5_from_synthetic_run(tmp_path: Path):
    run_dir = tmp_path / "run_1501"
    store = run_dir / "belief_store"
    store.mkdir(parents=True)
    civ = {
        "generations": [
            {"gen": 1, "best_fitness": 0.10, "mean_fitness": 0.08},
            {"gen": 2, "best_fitness": 0.20, "mean_fitness": 0.15},
            {"gen": 3, "best_fitness": 0.35, "mean_fitness": 0.25},
            {"gen": 4, "best_fitness": 0.40, "mean_fitness": 0.30},
        ]
    }
    (run_dir / "civilization.json").write_text(json.dumps(civ), encoding="utf-8")
    # Higher epistemic value precedes larger Δfitness → positive ρ
    epi_lines = [
        {"generation": 1, "epistemic_value": 1.0},
        {"generation": 2, "epistemic_value": 5.0},
        {"generation": 3, "epistemic_value": 8.0},
        {"generation": 4, "epistemic_value": 2.0},
    ]
    (store / "epistemic_value.jsonl").write_text(
        "\n".join(json.dumps(r) for r in epi_lines) + "\n",
        encoding="utf-8",
    )
    # Δ: g1→2 = +0.10, g2→3 = +0.15, g3→4 = +0.05
    # epi: 1, 5, 8  vs deltas 0.10, 0.15, 0.05 → not perfect but computable
    h5 = compute_h5(run_dir)
    assert h5["n_pairs"] == 3
    assert h5["spearman_rho"] is not None

    # Construct a perfect series for pass check
    civ2 = {
        "generations": [
            {"gen": 1, "best_fitness": 0.10, "mean_fitness": 0.10},
            {"gen": 2, "best_fitness": 0.12, "mean_fitness": 0.12},
            {"gen": 3, "best_fitness": 0.20, "mean_fitness": 0.20},
            {"gen": 4, "best_fitness": 0.40, "mean_fitness": 0.40},
        ]
    }
    run2 = tmp_path / "run_1502"
    store2 = run2 / "belief_store"
    store2.mkdir(parents=True)
    (run2 / "civilization.json").write_text(json.dumps(civ2), encoding="utf-8")
    perfect = [
        {"generation": 1, "epistemic_value": 1.0},
        {"generation": 2, "epistemic_value": 2.0},
        {"generation": 3, "epistemic_value": 4.0},
        {"generation": 4, "epistemic_value": 0.0},
    ]
    (store2 / "epistemic_value.jsonl").write_text(
        "\n".join(json.dumps(r) for r in perfect) + "\n",
        encoding="utf-8",
    )
    # deltas: 0.02, 0.08, 0.20 — monotone with epi 1,2,4 → ρ=1 > 0.3
    h5_pass = compute_h5(run2)
    assert h5_pass["spearman_rho"] == pytest.approx(1.0, abs=1e-9)
    assert h5_pass["pass"] is True
    assert gens_to_threshold(run2, 0.25) == 4
    assert gens_to_threshold(run2, 0.30) == 4
    summary = summarize_run(run2)
    assert summary["h5"]["pass"] is True
