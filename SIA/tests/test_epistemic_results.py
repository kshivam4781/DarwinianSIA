"""Offline H5 / epistemic_results helpers (no API)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from epistemic_results import (  # noqa: E402
    _cost_win,
    compare_b_vs_d,
    compute_h5,
    cost_to_threshold,
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
    a = AgentDNA(memory="failure_based", tool_strategy="selective")
    b = AgentDNA(memory="none", tool_strategy="aggressive")
    fa = deterministic_fitness(0, a, 1)
    fb = deterministic_fitness(0, b, 1)
    assert 0.02 <= fa <= 0.34
    assert 0.02 <= fb <= 0.34
    assert fa != fb
    # Additive latent: selective + failure_based must beat aggressive + none
    assert fa > fb


def test_deterministic_fitness_scale_keeps_mid_dna_under_threshold():
    """Compressed scale: mid DNA <30%; near-optimal preferred DNA can cross 30%.

    Tick 15 saturation: old [0.02, 0.38] mapping put ~42% of gen-1 best-of-4
    seeds already ≥30%. Ceiling 0.34 keeps early gens discriminative.
    """
    mid = AgentDNA(
        planning_style="stepwise",
        reflection=True,
        tool_strategy="selective",
        retry_policy="generic",
        memory="short_summary",
        confidence_threshold=0.70,
        prompt_structure="detailed",
    )
    almost = AgentDNA(
        planning_style="stepwise",
        reflection=True,
        tool_strategy="selective",
        retry_policy="generic",
        memory="failure_based",
        confidence_threshold=0.75,
        prompt_structure="detailed",
    )
    perfect = AgentDNA(
        planning_style="hierarchical",
        reflection=True,
        tool_strategy="selective",
        retry_policy="error_specific",
        memory="failure_based",
        confidence_threshold=0.75,
        prompt_structure="chain_of_thought",
    )
    f_mid = deterministic_fitness(0, mid, 1)
    f_almost = deterministic_fitness(0, almost, 1)
    f_perfect = deterministic_fitness(0, perfect, 1)
    assert f_mid < 0.30
    assert f_almost >= 0.30
    assert f_perfect <= 0.34
    assert f_perfect > f_almost > f_mid


def test_deterministic_fitness_transfers_with_dna_traits():
    """Same DNA must score the same across agent_id/generation (offline case study)."""
    dna = AgentDNA(memory="failure_based", tool_strategy="aggressive", planning_style="stepwise")
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
    # Preferring the higher-latent tool_strategy side must raise fitness.
    better = AgentDNA(
        memory=dna.memory,
        tool_strategy="selective",
        planning_style=dna.planning_style,
        reflection=dna.reflection,
        retry_policy=dna.retry_policy,
        confidence_threshold=dna.confidence_threshold,
        prompt_structure=dna.prompt_structure,
    )
    assert deterministic_fitness(0, better, 1) > f00


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
    # Default min_generation=2 skips gen1→gen2 (delay-all: steering inactive).
    # Default delta_horizon=2: g2 uses mean(g3,g4)-g2; g3 uses g4-g3.
    h5 = compute_h5(run_dir)
    assert h5["n_pairs"] == 2
    assert h5["min_generation"] == 2
    assert h5["delta_horizon"] == 2
    assert h5["spearman_rho"] is not None
    h5_all = compute_h5(run_dir, min_generation=1)
    assert h5_all["n_pairs"] == 3
    h5_step = compute_h5(run_dir, delta_horizon=1)
    assert h5_step["delta_horizon"] == 1
    assert h5_step["n_pairs"] == 2

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
    # horizon=2 forward means still monotone with epi 2,4 → ρ=1 > 0.3
    h5_pass = compute_h5(run2)
    assert h5_pass["spearman_rho"] == pytest.approx(1.0, abs=1e-9)
    assert h5_pass["pass"] is True
    assert gens_to_threshold(run2, 0.25) == 4
    assert gens_to_threshold(run2, 0.30) == 4
    summary = summarize_run(run2)
    assert summary["h5"]["pass"] is True


def test_compute_h5_horizon_recovers_delayed_gain(tmp_path: Path):
    """ε-lag: peak gain one gen late zeros single-step ρ; horizon=2 recovers."""
    run = tmp_path / "run_1503"
    store = run / "belief_store"
    store.mkdir(parents=True)
    # Seed-11-shaped: high epi at g2 but small next step; peak at g3→g4.
    civ = {
        "generations": [
            {"gen": 1, "best_fitness": 0.22, "mean_fitness": 0.22},
            {"gen": 2, "best_fitness": 0.24, "mean_fitness": 0.23585},
            {"gen": 3, "best_fitness": 0.28, "mean_fitness": 0.249575},
            {"gen": 4, "best_fitness": 0.31, "mean_fitness": 0.28375},
            {"gen": 5, "best_fitness": 0.28, "mean_fitness": 0.266225},
            {"gen": 6, "best_fitness": 0.30, "mean_fitness": 0.28705},
        ]
    }
    (run / "civilization.json").write_text(json.dumps(civ), encoding="utf-8")
    epi = [
        {"generation": 1, "epistemic_value": 13.2},
        {"generation": 2, "epistemic_value": 11.36},
        {"generation": 3, "epistemic_value": 9.70},
        {"generation": 4, "epistemic_value": 8.44},
        {"generation": 5, "epistemic_value": 7.33},
        {"generation": 6, "epistemic_value": 6.39},
    ]
    (store / "epistemic_value.jsonl").write_text(
        "\n".join(json.dumps(r) for r in epi) + "\n",
        encoding="utf-8",
    )
    step = compute_h5(run, delta_horizon=1)
    assert step["spearman_rho"] == pytest.approx(0.0, abs=1e-9)
    assert step["pass"] is False
    smooth = compute_h5(run)  # default horizon=2
    assert smooth["delta_horizon"] == 2
    assert smooth["spearman_rho"] is not None
    assert smooth["spearman_rho"] > 0.3
    assert smooth["pass"] is True


def _mk_run(
    tmp_path: Path,
    run_id: int,
    bests: list[float],
    *,
    pop: int = 2,
    eval_subset: int = 3,
    tokens_per_agent: int | None = None,
) -> Path:
    run = tmp_path / f"run_{run_id}"
    civ = {
        "generations": [
            {"gen": i + 1, "best_fitness": b, "mean_fitness": b}
            for i, b in enumerate(bests)
        ]
    }
    run.mkdir(parents=True)
    (run / "civilization.json").write_text(json.dumps(civ), encoding="utf-8")
    store = run / "belief_store"
    store.mkdir()
    (store / "epistemic_value.jsonl").write_text("", encoding="utf-8")
    for g in range(1, len(bests) + 1):
        for a in range(pop):
            agent = run / f"gen_{g}" / f"agent_{a}"
            agent.mkdir(parents=True)
            payload: dict = {
                "accuracy": bests[g - 1],
                "eval_subset": eval_subset,
                "n_total": eval_subset,
            }
            if tokens_per_agent is not None:
                payload["total_input_tokens"] = tokens_per_agent
                payload["total_output_tokens"] = 0
            (agent / "results.json").write_text(json.dumps(payload), encoding="utf-8")
    return run


def test_compare_b_vs_d_counts_gens30_reach(tmp_path: Path):
    """D reaching 30% when B never does counts as a gens30 win."""
    b_runs = [_mk_run(tmp_path, 1, [0.20, 0.22, 0.24, 0.24])]
    d_runs = [_mk_run(tmp_path, 2, [0.20, 0.28, 0.31, 0.33])]
    out = compare_b_vs_d(b_runs, d_runs)
    assert out["d_wins_gens30"] == 1
    assert out["b_wins_gens30"] == 0
    # B never hits 30% → D also wins cost-to-30 (PRIMARY b).
    assert out["d_wins_cost30"] == 1
    assert out["b_wins_cost30"] == 0


def test_compare_b_vs_d_emits_mean_final_gap(tmp_path: Path):
    """Tick 360: mean_final_* + primary_final_pass for PRIMARY (c) / G3 promising."""
    # Five pairs: D wins final on all with ~6pp mean gap.
    b_runs = [
        _mk_run(tmp_path, 100 + i, [0.20, 0.22, 0.24]) for i in range(5)
    ]
    d_runs = [
        _mk_run(tmp_path, 200 + i, [0.20, 0.26, 0.30]) for i in range(5)
    ]
    out = compare_b_vs_d(b_runs, d_runs)
    assert out["n_pairs"] == 5
    assert out["d_wins_final"] == 5
    assert out["mean_final_b"] == pytest.approx(0.24)
    assert out["mean_final_d"] == pytest.approx(0.30)
    assert out["mean_final_gap"] == pytest.approx(0.06)
    assert out["primary_final_pass"] is True
    # ≥3/5 seed wins but mean gap ≤1pp → criterion (c) fails (noise).
    mix_b = [
        _mk_run(tmp_path, 500 + i, [0.20, 0.250 if i < 3 else 0.300])
        for i in range(5)
    ]
    mix_d = [
        _mk_run(tmp_path, 600 + i, [0.20, 0.265 if i < 3 else 0.301])
        for i in range(5)
    ]
    mix = compare_b_vs_d(mix_b, mix_d)
    assert mix["d_wins_final"] == 3
    assert mix["mean_final_gap"] == pytest.approx(0.0094, abs=1e-4)
    assert mix["primary_final_pass"] is False

def test_cost_to_threshold_prefers_tokens_and_savings(tmp_path: Path):
    """Live token fields beat call fallback; ≥15% fewer tokens → D cost win."""
    b = _mk_run(tmp_path, 10, [0.20, 0.31], pop=2, tokens_per_agent=1000)
    d = _mk_run(tmp_path, 11, [0.20, 0.31], pop=2, tokens_per_agent=800)
    b_c = cost_to_threshold(b, 0.30)
    d_c = cost_to_threshold(d, 0.30)
    assert b_c["unit"] == "tokens"
    assert d_c["unit"] == "tokens"
    # 2 agents × 2 gens × 1000 = 4000 vs 3200 → 20% savings
    assert b_c["cost"] == pytest.approx(4000.0)
    assert d_c["cost"] == pytest.approx(3200.0)
    assert _cost_win(d_c["cost"], b_c["cost"]) == "D"
    out = compare_b_vs_d([b], [d])
    assert out["d_wins_cost30"] == 1


def test_cost_win_requires_fifteen_percent():
    assert _cost_win(85.0, 100.0) == "D"
    assert _cost_win(90.0, 100.0) is None  # only 10% savings
    assert _cost_win(100.0, 85.0) == "B"
    assert _cost_win(50.0, None) == "D"
    assert _cost_win(None, 50.0) == "B"


def test_cost_to_threshold_reads_submission_json_fallback(tmp_path: Path):
    """Tick 290: accuracy-only results.json + metered submission.json → tokens unit."""
    from epistemic_results import load_gen_cost

    run = tmp_path / "run_legacy_cost"
    for g, best in enumerate([0.20, 0.32], start=1):
        agent = run / f"gen_{g}" / "agent_0"
        results_dir = agent / "results"
        results_dir.mkdir(parents=True)
        (agent / "results.json").write_text(
            json.dumps(
                {
                    "accuracy": best,
                    "n_correct": 1,
                    "n_total": 5,
                    "eval_subset": 5,
                }
            ),
            encoding="utf-8",
        )
        (results_dir / "submission.json").write_text(
            json.dumps(
                {
                    "total_input_tokens": 500,
                    "total_output_tokens": 50,
                    "total_reasoning_tokens": 0,
                    "total_cost_usd": 0.01,
                    "details": [
                        {
                            "question_id": 0,
                            "model_answer": "A",
                            "input_tokens": 500,
                            "output_tokens": 50,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
    (run / "civilization.json").write_text(
        json.dumps(
            {
                "generations": [
                    {"gen": 1, "best_fitness": 0.20, "mean_fitness": 0.20},
                    {"gen": 2, "best_fitness": 0.32, "mean_fitness": 0.32},
                ]
            }
        ),
        encoding="utf-8",
    )
    costs = load_gen_cost(run)
    assert costs[1]["unit"] == "tokens"
    assert costs[1]["cost"] == pytest.approx(550.0)
    hit = cost_to_threshold(run, 0.30)
    assert hit["generation"] == 2
    assert hit["unit"] == "tokens"
    assert hit["cost"] == pytest.approx(1100.0)

def test_resolve_h2_bias_field_prefers_tool_strategy(tmp_path: Path, monkeypatch):
    """Tick 361: live H2 must score the DNA field CABS actually biased."""
    from epistemic_results import compute_h2, resolve_h2_bias_field

    monkeypatch.setattr(
        "epistemic_results._load_mutation_bias_map",
        lambda _run_dir: {
            "tool_strategy": ["selective", "aggressive"],
            "memory": ["none"],
        },
    )
    assert resolve_h2_bias_field(tmp_path) == "tool_strategy"

    # Empty bias → memory fallback.
    monkeypatch.setattr(
        "epistemic_results._load_mutation_bias_map",
        lambda _run_dir: {},
    )
    assert resolve_h2_bias_field(tmp_path) == "memory"

    # Multi-allele pool preferred over singleton preferred-name field.
    monkeypatch.setattr(
        "epistemic_results._load_mutation_bias_map",
        lambda _run_dir: {
            "memory": ["failure_based", "none", "success_based"],
            "tool_strategy": ["selective"],
        },
    )
    assert resolve_h2_bias_field(tmp_path) == "memory"

    # compute_h2(field=None) follows resolve + loads bias for that field.
    run = tmp_path / "run_h2_auto"
    agent = run / "gen_3" / "agent_0"
    agent.mkdir(parents=True)
    (agent / "agent_dna.json").write_text(
        json.dumps({"tool_strategy": "selective", "memory": "none"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "epistemic_results._load_mutation_bias_map",
        lambda _run_dir: {"tool_strategy": ["selective", "aggressive"]},
    )
    h2 = compute_h2(run, field=None)
    assert h2["field"] == "tool_strategy"
    assert h2["bias_values"] == ["selective", "aggressive"]
    assert h2["preferred_value"] == "selective"
    assert h2["in_bias_share"] == pytest.approx(1.0)
    assert h2["preferred_share"] == pytest.approx(1.0)

    # Default field=None (Tick 364) matches explicit None.
    h2_default = compute_h2(run)
    assert h2_default["field"] == "tool_strategy"
    assert h2_default["preferred_share"] == pytest.approx(1.0)
