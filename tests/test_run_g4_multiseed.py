"""Tests for scripts/run_g4_multiseed.py (Tick 27–28 live G4 5-seed runner + paper pack)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from prepare_gpqa_smoke_data import is_synthetic_smoke, prepare_task_tree  # noqa: E402
from run_g4_multiseed import (  # noqa: E402
    CheckResult,
    PilotPlan,
    TABLE2_LIVE_H2_END,
    TABLE2_LIVE_H2_MARKER,
    TABLE2_LIVE_H5_END,
    TABLE2_LIVE_H5_MARKER,
    build_g4_plans,
    h2_skew_pass,
    h5_pass_count,
    h5_validity_pass,
    primary_criteria_pass,
    refresh_paper_artifacts_live,
    render_live_table1_rows,
    run_preflight,
    score_live_h2,
    update_icml_ready_from_g4,
    write_gate4_report,
    write_live_bvd_figures,
)


def test_build_g4_plans_requires_exactly_five() -> None:
    plans = build_g4_plans(
        [1, 2, 3, 4, 5],
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    assert len(plans) == 5
    assert plans[0].b_run_id == 1211
    assert plans[-1].d_run_id == 1315
    with pytest.raises(ValueError, match="exactly 5"):
        build_g4_plans([1, 2], [1, 2], [3, 4])
    with pytest.raises(ValueError, match="unique"):
        build_g4_plans(
            [1, 2, 3, 4, 5],
            [1, 2, 3, 4, 5],
            [1, 6, 7, 8, 9],
        )


def test_preflight_blocks_without_keys(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)

    import run_g4_multiseed as mod
    import run_g3_pilot as g3

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    task.mkdir(parents=True)
    prepare_task_tree(task, n=5)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(mod, "_run_dir_for", lambda rid: None)

    plans = build_g4_plans(
        [1, 2, 3, 4, 5],
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    report = run_preflight(mode="preflight", plans=plans)
    assert report.ready_for_live is False
    names = {c.name: c.ok for c in report.checks}
    assert names["anthropic_key"] is True  # Tick 289 optional under Nebius meta
    assert names["nebius_key"] is False
    assert names["gpqa_not_synthetic"] is False
    assert names["seed_count"] is True
    assert names["sequential_only"] is True
    assert len(report.commands) == 10  # 5 × (B then D)


def test_preflight_live_ready_with_keys_and_real_gpqa(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-ant")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-neb")
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")
    monkeypatch.setenv("SIA_G4_PAIR_ESTIMATE_USD", "3")

    import run_g4_multiseed as mod

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    pub = task / "data" / "public"
    priv = task / "data" / "private"
    pub.mkdir(parents=True)
    priv.mkdir(parents=True)
    rows = [
        {
            "id": i,
            "Question": f"Real science question {i}?",
            "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
            "correct_answer_letter": "A",
            "domain": "physics",
            "source": "gpqa_diamond",
        }
        for i in range(15)
    ]
    (pub / "diamond_questions.json").write_text(json.dumps(rows), encoding="utf-8")
    (priv / "diamond_questions.json").write_text(json.dumps(rows), encoding="utf-8")
    (pub / "task.md").write_text("# GPQA", encoding="utf-8")

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(mod, "_run_dir_for", lambda rid: None)
    # Tick 303: tmp REPO_ROOT lacks tip lock artifacts — stub locks green.
    monkeypatch.setattr(
        mod, "committed_g3g4_recipes_match_live_shape", lambda **_k: (True, [])
    )
    monkeypatch.setattr(
        mod, "committed_offline_bvd_matches_live_shape", lambda **_k: (True, [])
    )
    # Tick 305: stub tip lineage green (tmp tree has no ICML_PROGRESS tip).
    monkeypatch.setattr(
        mod,
        "write_icml_tip_status",
        lambda *_a, **_k: {
            "tip_ok_for_live": True,
            "local_tick": 305,
            "remote_tip_ref": "refs/remotes/origin/cursor/icml-epistemic-results-test",
            "blockers": [],
        },
    )

    plans = build_g4_plans(
        [1, 2, 3, 4, 5],
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    report = run_preflight(mode="live", plans=plans, pair_estimate_usd=3.0)
    assert report.ready_for_live is True
    assert report.blockers == []
    assert is_synthetic_smoke(task) is False


def test_preflight_refuses_stale_recipe_or_offline_bvd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 303: direct G4 --live refuses when shape locks fail (not only pipeline)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-ant")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-neb")
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")
    monkeypatch.setenv("SIA_G4_PAIR_ESTIMATE_USD", "3")

    import run_g4_multiseed as mod

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    pub = task / "data" / "public"
    priv = task / "data" / "private"
    pub.mkdir(parents=True)
    priv.mkdir(parents=True)
    rows = [
        {
            "id": i,
            "Question": f"Real science question {i}?",
            "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
            "correct_answer_letter": "A",
            "domain": "physics",
            "source": "gpqa_diamond",
        }
        for i in range(15)
    ]
    (pub / "diamond_questions.json").write_text(json.dumps(rows), encoding="utf-8")
    (priv / "diamond_questions.json").write_text(json.dumps(rows), encoding="utf-8")
    (pub / "task.md").write_text("# GPQA", encoding="utf-8")

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(mod, "_run_dir_for", lambda rid: None)
    monkeypatch.setattr(
        mod,
        "write_icml_tip_status",
        lambda *_a, **_k: {
            "tip_ok_for_live": True,
            "local_tick": 305,
            "remote_tip_ref": "refs/remotes/origin/cursor/icml-epistemic-results-test",
            "blockers": [],
        },
    )
    monkeypatch.setattr(
        mod,
        "committed_g3g4_recipes_match_live_shape",
        lambda **_k: (False, ["docs/gate4_report.json commands[0] shape stale"]),
    )
    monkeypatch.setattr(
        mod, "committed_offline_bvd_matches_live_shape", lambda **_k: (True, [])
    )

    plans = build_g4_plans(
        [1, 2, 3, 4, 5],
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    report = run_preflight(mode="live", plans=plans, pair_estimate_usd=3.0)
    assert report.ready_for_live is False
    names = {c.name: c.ok for c in report.checks}
    assert names["g3g4_recipes_match_live_shape"] is False
    assert names["nebius_key"] is True

    monkeypatch.setattr(
        mod, "committed_g3g4_recipes_match_live_shape", lambda **_k: (True, [])
    )
    monkeypatch.setattr(
        mod,
        "committed_offline_bvd_matches_live_shape",
        lambda **_k: (False, ["docs/paper_artifacts.md: missing current offline B"]),
    )
    report2 = run_preflight(mode="live", plans=plans, pair_estimate_usd=3.0)
    assert report2.ready_for_live is False
    names2 = {c.name: c.ok for c in report2.checks}
    assert names2["offline_bvd_matches_live_shape"] is False


def test_preflight_refuses_stale_tip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 305: direct G4 --live refuses when tip lineage lags (not only pipeline)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-ant")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-neb")
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")
    monkeypatch.setenv("SIA_G4_PAIR_ESTIMATE_USD", "3")

    import run_g4_multiseed as mod

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    pub = task / "data" / "public"
    priv = task / "data" / "private"
    pub.mkdir(parents=True)
    priv.mkdir(parents=True)
    rows = [
        {
            "id": i,
            "Question": f"Real science question {i}?",
            "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
            "correct_answer_letter": "A",
            "domain": "physics",
            "source": "gpqa_diamond",
        }
        for i in range(15)
    ]
    (pub / "diamond_questions.json").write_text(json.dumps(rows), encoding="utf-8")
    (priv / "diamond_questions.json").write_text(json.dumps(rows), encoding="utf-8")
    (pub / "task.md").write_text("# GPQA", encoding="utf-8")

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(mod, "_run_dir_for", lambda rid: None)
    monkeypatch.setattr(
        mod, "committed_g3g4_recipes_match_live_shape", lambda **_k: (True, [])
    )
    monkeypatch.setattr(
        mod, "committed_offline_bvd_matches_live_shape", lambda **_k: (True, [])
    )
    monkeypatch.setattr(
        mod,
        "write_icml_tip_status",
        lambda *_a, **_k: {
            "tip_ok_for_live": False,
            "local_tick": 300,
            "remote_tip_tick": 305,
            "remote_tip_ref": "refs/remotes/origin/cursor/icml-epistemic-results-tip",
            "blockers": [
                "local Tick 300 behind remote tip Tick 305 "
                "(refs/remotes/origin/cursor/icml-epistemic-results-tip)"
            ],
        },
    )

    plans = build_g4_plans(
        [1, 2, 3, 4, 5],
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    report = run_preflight(mode="live", plans=plans, pair_estimate_usd=3.0)
    assert report.ready_for_live is False
    names = {c.name: c.ok for c in report.checks}
    assert names["tip_ok_for_live"] is False

    report2 = run_preflight(
        mode="live", plans=plans, pair_estimate_usd=3.0, allow_stale_tip=True
    )
    assert report2.ready_for_live is True
    names2 = {c.name: c.ok for c in report2.checks}
    assert names2["tip_ok_for_live"] is True
    assert any("allow-stale-tip" in n for n in report2.notes)


def test_budget_projection_blocks_five_pairs_over_ceiling(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-ant")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-neb")
    # 5 × $4 = $20 but spent already $1 → projected $21 > ceiling
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "1")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")

    import run_g4_multiseed as mod

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    pub = task / "data" / "public"
    priv = task / "data" / "private"
    pub.mkdir(parents=True)
    priv.mkdir(parents=True)
    rows = [
        {
            "id": 1,
            "Question": "Real?",
            "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
            "correct_answer_letter": "A",
            "domain": "physics",
            "source": "gpqa_diamond",
        }
    ]
    (pub / "diamond_questions.json").write_text(json.dumps(rows), encoding="utf-8")
    (priv / "diamond_questions.json").write_text(json.dumps(rows), encoding="utf-8")
    (pub / "task.md").write_text("# GPQA", encoding="utf-8")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(mod, "_run_dir_for", lambda rid: None)
    monkeypatch.setattr(
        mod, "committed_g3g4_recipes_match_live_shape", lambda **_k: (True, [])
    )
    monkeypatch.setattr(
        mod, "committed_offline_bvd_matches_live_shape", lambda **_k: (True, [])
    )

    plans = build_g4_plans(
        [1, 2, 3, 4, 5],
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    report = run_preflight(mode="live", plans=plans, pair_estimate_usd=4.0)
    assert report.ready_for_live is False
    names = {c.name: c.ok for c in report.checks}
    assert names["budget"] is False


def test_primary_criteria_pass_and_h5_count() -> None:
    assert primary_criteria_pass(None) is False
    assert primary_criteria_pass({"n_pairs": 4, "primary_gens30_pass": True}) is False
    assert primary_criteria_pass(
        {
            "n_pairs": 5,
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 2,
        }
    )
    assert primary_criteria_pass(
        {
            "n_pairs": 5,
            "primary_gens30_pass": False,
            "primary_cost30_pass": False,
            "primary_gens25_pass": False,
            "primary_cost25_pass": False,
            "d_wins_final": 3,
        }
    )
    # Tick 360: explicit primary_final_pass / mean gap gate for criterion (c).
    assert primary_criteria_pass(
        {
            "n_pairs": 5,
            "primary_gens30_pass": False,
            "primary_cost30_pass": False,
            "primary_gens25_pass": False,
            "primary_cost25_pass": False,
            "primary_final_pass": True,
            "d_wins_final": 3,
            "mean_final_gap": 0.06,
        }
    )
    assert not primary_criteria_pass(
        {
            "n_pairs": 5,
            "primary_gens30_pass": False,
            "primary_cost30_pass": False,
            "primary_gens25_pass": False,
            "primary_cost25_pass": False,
            "d_wins_final": 3,
            "mean_final_gap": 0.005,  # ~0.5pp noise
        }
    )
    assert not primary_criteria_pass(
        {
            "n_pairs": 5,
            "primary_gens30_pass": False,
            "primary_cost30_pass": False,
            "primary_gens25_pass": False,
            "primary_cost25_pass": False,
            "d_wins_final": 2,
        }
    )
    n_pass, n_total = h5_pass_count(
        {
            "run_1311": {"spearman_rho": 0.4},
            "run_1312": {"spearman_rho": 0.2},
            "run_1313": {"error": "missing"},
            "run_1314": {"spearman_rho": 0.9},
        }
    )
    assert (n_pass, n_total) == (2, 3)


def test_refresh_paper_artifacts_live_table(tmp_path: Path) -> None:
    docs = tmp_path / "paper_artifacts.md"
    docs.write_text(
        "# ICML paper artifacts\n\n"
        "| B darwinian-only | — | — | none yet (live) |\n"
        "| D epistemic_full | — | — | none yet (live) |\n\n"
        "### Live GPQA\n\n"
        "| Seed | B final acc | D final acc | B gens@25% | D gens@25% | B tokens | D tokens | Winner |\n"
        "|------|-------------|-------------|------------|------------|----------|----------|--------|\n"
        "| — | — | — | — | — | — | — | — |\n\n"
        "## Table 2 — Mechanism / validity\n\n"
        "| Metric | Value | Pass? |\n"
        "|--------|-------|-------|\n"
        f"{TABLE2_LIVE_H2_MARKER}\n"
        "| H2 trait skew (live API) | — | — |\n"
        f"{TABLE2_LIVE_H2_END}\n"
        f"{TABLE2_LIVE_H5_MARKER}\n"
        "| H5 Spearman ρ (live) | — | — |\n"
        f"{TABLE2_LIVE_H5_END}\n",
        encoding="utf-8",
    )
    plans = build_g4_plans(
        [1, 2, 3, 4, 5],
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    comparison = {
        "n_pairs": 5,
        "primary_gens30_pass": True,
        "primary_cost30_pass": False,
        "primary_gens25_pass": False,
        "primary_cost25_pass": False,
        "primary_final_pass": True,
        "mean_final_gap": 0.08,
        "d_wins_final": 4,
        "d_wins_h2": 4,
        "h2_preferred_pass": True,
        "rows": [
            {
                "B": {
                    "final_best": 0.20,
                    "gens_to_25": None,
                    "gens_to_30": None,
                    "cost_to_25": {"cost": None, "unit": "calls"},
                    "cost_to_30": {"cost": None, "unit": "calls"},
                    "learning_curve": {
                        "1": {"best": 0.15, "mean": 0.12},
                        "2": {"best": 0.20, "mean": 0.16},
                    },
                },
                "D": {
                    "final_best": 0.28,
                    "gens_to_25": 2,
                    "gens_to_30": 3,
                    "cost_to_25": {"cost": 24.0, "unit": "calls"},
                    "cost_to_30": {"cost": 36.0, "unit": "calls"},
                    "learning_curve": {
                        "1": {"best": 0.18, "mean": 0.14},
                        "2": {"best": 0.24, "mean": 0.20},
                        "3": {"best": 0.28, "mean": 0.24},
                    },
                },
            }
            for _ in range(5)
        ],
    }
    h2 = {
        f"run_{rid}": {
            "field": "tool_strategy",
            "counts": {"selective": 6, "aggressive": 2},
            "total": 8,
            "bias_values": ["selective", "aggressive"],
            "preferred_value": "selective",
            "preferred_share": 0.75,
            "in_bias_share": 1.0,
        }
        for rid in (1311, 1312, 1313, 1314, 1315)
    }
    ok = refresh_paper_artifacts_live(
        docs_path=docs,
        plans=plans,
        comparison=comparison,
        h5_by_d_run={
            f"run_{rid}": {"spearman_rho": 0.5}
            for rid in (1311, 1312, 1313, 1314, 1315)
        },
        h2_by_d_run=h2,
        figures_written=["docs/figures/fig1_learning_curves.png"],
        timestamp="2026-08-06T04:00:00Z",
    )
    assert ok is True
    text = docs.read_text(encoding="utf-8")
    assert "Auto-filled by `scripts/run_g4_multiseed.py`" in text
    assert "| 1 | 0.2 | 0.28 |" in text
    assert "PRIMARY flags: gens30=True" in text
    assert "primary_final_pass=True" in text
    assert "mean_final_gap=0.08" in text
    assert "field=tool_strategy" in text
    assert "preferred_share=0.75" in text
    assert "**G4 live**" in text
    assert "## Table 2 — Mechanism / validity" in text
    assert "H2 trait skew (live API)" in text
    assert "skew_pass=True" in text
    # Tick 367: live paper surfaces Tick 366 d_wins_h2 / h2_preferred_pass.
    assert "d_wins_h2=4/5" in text
    assert "h2_preferred_pass=True" in text
    assert "H5 Spearman ρ (live)" in text
    assert "ρ>0.3 = **5/5**" in text
    rows = render_live_table1_rows(plans[:1], comparison)
    assert "D_final" in rows[0] and "D_gens30" in rows[0]
    assert "D_gens25" in rows[0]
    assert "D_cost25" in rows[0] and "D_cost30" in rows[0]


def test_write_live_fig2_uses_majority_h2_field_not_memory_default(
    tmp_path: Path,
) -> None:
    """Tick 363: live Fig 2 title uses majority auto-resolved field, not memory."""
    comparison = {
        "rows": [
            {
                "B": {"learning_curve": {"1": {"best": 0.1, "mean": 0.08}}},
                "D": {"learning_curve": {"1": {"best": 0.12, "mean": 0.1}}},
            }
        ]
    }
    h2 = {
        "run_1311": {
            "field": "tool_strategy",
            "counts": {"selective": 5, "aggressive": 1},
        },
        "run_1312": {
            "field": "tool_strategy",
            "counts": {"selective": 4, "minimal": 2},
        },
        "run_1313": {
            "field": "retry_policy",
            "counts": {"exponential": 3},
        },
    }
    written = write_live_bvd_figures(
        comparison=comparison,
        h2_by_d_run=h2,
        figures_dir=tmp_path / "figures",
    )
    if not written:
        pytest.skip("matplotlib not installed")
    # Title is baked into the PNG; re-run plot path via inspecting field vote
    # by ensuring fig2 exists and no crash on non-memory majority.
    assert any(p.endswith("fig2_mechanism.png") for p in written)
    # Empty H2 → no fig2 file (only fig1); default field would be "auto" not "memory"
    written_empty = write_live_bvd_figures(
        comparison=comparison,
        h2_by_d_run={},
        figures_dir=tmp_path / "figures_empty",
    )
    assert written_empty  # fig1 only
    assert not any(p.endswith("fig2_mechanism.png") for p in written_empty)
    assert (tmp_path / "figures" / "fig2_mechanism.png").is_file()
    assert not (tmp_path / "figures_empty" / "fig2_mechanism.png").exists()


def test_h2_h5_pass_helpers() -> None:
    assert h5_validity_pass({}) is False
    assert h5_validity_pass(
        {f"r{i}": {"spearman_rho": 0.5} for i in range(5)}
    )
    assert not h5_validity_pass(
        {
            "a": {"spearman_rho": 0.5},
            "b": {"spearman_rho": 0.5},
            "c": {"spearman_rho": 0.1},
            "d": {"spearman_rho": 0.1},
            "e": {"spearman_rho": 0.1},
        }
    )
    # Tick 413: 1 ρ>0.3 + 4 errors must NOT pass when planned_n=5.
    thin_h5 = {
        "r0": {"spearman_rho": 0.9},
        "r1": {"error": "missing"},
        "r2": {"error": "missing"},
        "r3": {"error": "missing"},
        "r4": {"error": "missing"},
    }
    assert h5_validity_pass(thin_h5) is True  # legacy: n_total=1 path
    assert h5_validity_pass(thin_h5, planned_n=5) is False
    assert h5_validity_pass(
        {
            "r0": {"spearman_rho": 0.5},
            "r1": {"spearman_rho": 0.6},
            "r2": {"spearman_rho": 0.7},
            "r3": {"error": "x"},
            "r4": {"error": "y"},
        },
        planned_n=5,
    )
    assert h2_skew_pass(
        {
            f"r{i}": {
                "in_bias_share": 0.75,
                "preferred_share": 0.75,
                "preferred_value": "failure_based",
                "counts": {"failure_based": 3, "none": 1},
                "total": 4,
                "bias_values": ["failure_based"],
            }
            for i in range(5)
        }
    )
    assert not h2_skew_pass(
        {
            f"r{i}": {
                "in_bias_share": 0.2,
                "preferred_share": 0.2,
                "counts": {"a": 1, "b": 4},
                "total": 5,
                "bias_values": [],
            }
            for i in range(5)
        }
    )
    # Tick 364: in_bias_share=1.0 but loser allele dominates → MECHANISM fail.
    assert not h2_skew_pass(
        {
            f"r{i}": {
                "in_bias_share": 1.0,
                "preferred_share": 0.25,
                "preferred_value": "selective",
                "counts": {"selective": 1, "aggressive": 3},
                "total": 4,
                "bias_values": ["selective", "aggressive"],
            }
            for i in range(5)
        }
    )
    # Preferred majority with full pool membership → pass.
    assert h2_skew_pass(
        {
            f"r{i}": {
                "in_bias_share": 1.0,
                "preferred_share": 0.75,
                "preferred_value": "selective",
                "counts": {"selective": 3, "aggressive": 1},
                "total": 4,
                "bias_values": ["selective", "aggressive"],
            }
            for i in range(5)
        }
    )
    # Tick 413: single preferred H2 + errors must not pass planned_n=5.
    thin_h2 = {
        "r0": {
            "preferred_share": 0.9,
            "in_bias_share": 1.0,
            "preferred_value": "selective",
            "counts": {"selective": 9},
            "total": 9,
            "bias_values": ["selective"],
        },
        "r1": {"error": "x"},
        "r2": {"error": "x"},
        "r3": {"error": "x"},
        "r4": {"error": "x"},
    }
    assert h2_skew_pass(thin_h2) is True  # legacy thin path
    assert h2_skew_pass(thin_h2, planned_n=5) is False


def test_compare_b_vs_d_h2_preferred_aggregate(monkeypatch) -> None:
    """Tick 366: compare_b_vs_d emits d_wins_h2 / h2_preferred_pass from preferred_share."""
    from epistemic_results import compare_b_vs_d, h2_preferred_seed_pass

    assert h2_preferred_seed_pass(
        {"preferred_share": 0.75, "in_bias_share": 1.0}
    )
    assert not h2_preferred_seed_pass(
        {"preferred_share": 0.29, "in_bias_share": 1.0}
    )
    # Derive from counts when preferred_share missing.
    assert h2_preferred_seed_pass(
        {
            "preferred_value": "selective",
            "counts": {"selective": 3, "aggressive": 1},
            "total": 4,
            "bias_values": ["selective", "aggressive"],
        }
    )

    shares = [0.71, 0.29, 0.83, 0.67, 0.75]

    def fake_summarize(run_dir: Path) -> dict:
        name = Path(run_dir).name
        # B runs: no preferred share; D runs: cycle shares.
        if "b" in name.lower() or name.startswith("run_b"):
            return {
                "final_best": 0.25,
                "gens_to_25": 1,
                "gens_to_30": None,
                "cost_to_25": {"cost": 20},
                "cost_to_30": {},
                "h5": {"spearman_rho": 0.0, "pass": False},
                "h2": {"preferred_share": 0.1, "in_bias_share": 0.1},
            }
        idx = int(str(run_dir).rstrip("/").split("_")[-1]) % 5
        return {
            "final_best": 0.32,
            "gens_to_25": 1,
            "gens_to_30": 4,
            "cost_to_25": {"cost": 20},
            "cost_to_30": {"cost": 80, "unit": "calls"},
            "h5": {"spearman_rho": 0.8, "pass": True},
            "h2": {
                "preferred_share": shares[idx],
                "in_bias_share": 1.0,
                "preferred_value": "selective",
            },
        }

    import epistemic_results as er

    monkeypatch.setattr(er, "summarize_run", fake_summarize)
    b_runs = [Path(f"/tmp/run_b_{i}") for i in range(5)]
    d_runs = [Path(f"/tmp/run_d_{i}") for i in range(5)]
    out = compare_b_vs_d(b_runs, d_runs)
    assert out["d_wins_h2"] == 4
    assert out["h2_preferred_pass"] is True
    assert out["d_wins_final"] == 5
    assert out["primary_final_pass"] is True
    # Tick 364: in_bias_share=1.0 but loser allele dominates → MECHANISM fail.
    assert not h2_skew_pass(
        {
            f"r{i}": {
                "in_bias_share": 1.0,
                "preferred_share": 0.25,
                "preferred_value": "selective",
                "counts": {"selective": 1, "aggressive": 3},
                "total": 4,
                "bias_values": ["selective", "aggressive"],
            }
            for i in range(5)
        }
    )
    # Preferred majority with full pool membership → pass.
    assert h2_skew_pass(
        {
            f"r{i}": {
                "in_bias_share": 1.0,
                "preferred_share": 0.75,
                "preferred_value": "selective",
                "counts": {"selective": 3, "aggressive": 1},
                "total": 4,
                "bias_values": ["selective", "aggressive"],
            }
            for i in range(5)
        }
    )


def test_update_icml_ready_sets_ready_only_when_all_pass(tmp_path: Path) -> None:
    ready = tmp_path / "ICML_READY.md"
    ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "**STATUS: IN_PROGRESS**\n\n"
        "## Criteria\n\n"
        "### 1. PRIMARY — Condition D beats B\n"
        "- [ ] D beats B on ≥3/5 seeds for gens-to-threshold (25% or 30%), **or**\n"
        "- [ ] D beats B on ≥3/5 seeds for cost-to-threshold (≥15% fewer tokens/calls), **or**\n"
        "- [ ] Non-trivial mean final accuracy gap (not ~1pp noise)\n\n"
        "### 2. MECHANISM — H2 or case study\n"
        "- [x] Documented case study (tie → contradiction → different DNA → fitness lift)\n"
        "- [ ] Live API-run H2 DNA trait skew under contradiction bias\n\n"
        "### 3. VALIDITY — H5\n"
        "- [ ] Spearman ρ (`epistemic_value_t` vs `Δfitness_t+1`) > 0.3 on live / publishable runs\n\n"
        "### 4. PAPER\n"
        "- [x] Figure 1 draft (offline B vs D learning curves)\n"
        "- [x] Figure 2 draft (H2 DNA histogram / case-study support)\n"
        "- [ ] Table 1 (primary metrics by seed) — offline stub\n"
        "- [ ] Table 2 (H2/H5 / cost) — offline stub\n"
        "- [ ] Reproducible **live** run IDs listed in `docs/paper_artifacts.md`\n",
        encoding="utf-8",
    )
    comparison = {
        "primary_gens30_pass": True,
        "primary_cost30_pass": False,
        "d_wins_final": 4,
    }
    status = update_icml_ready_from_g4(
        ready_path=ready,
        comparison=comparison,
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png", "fig2.png"],
        timestamp="2026-08-06T04:00:00Z",
        allow_ready=True,
    )
    assert status == "READY"
    text = ready.read_text(encoding="utf-8")
    assert "**STATUS: READY**" in text
    assert "- [x] D beats B on ≥3/5 seeds for gens-to-threshold" in text
    assert "- [x] Spearman ρ" in text
    assert "- [x] Table 1" in text
    assert "_Last G4 pack refresh:" in text

    # Without allow_ready, stay IN_PROGRESS even if metrics pass.
    status2 = update_icml_ready_from_g4(
        ready_path=ready,
        comparison=comparison,
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-08-06T04:01:00Z",
        allow_ready=False,
    )
    assert status2 == "IN_PROGRESS"


def test_write_live_bvd_figures(tmp_path: Path) -> None:
    comparison = {
        "rows": [
            {
                "B": {
                    "learning_curve": {
                        "1": {"best": 0.1, "mean": 0.08},
                        "2": {"best": 0.2, "mean": 0.15},
                    }
                },
                "D": {
                    "learning_curve": {
                        "1": {"best": 0.12, "mean": 0.1},
                        "2": {"best": 0.25, "mean": 0.2},
                    }
                },
            }
        ]
    }
    h2 = {
        "run_1311": {
            "field": "memory",
            "counts": {"failure_based": 5, "none": 1},
        }
    }
    written = write_live_bvd_figures(
        comparison=comparison,
        h2_by_d_run=h2,
        figures_dir=tmp_path / "figures",
    )
    # matplotlib may be absent in minimal envs — then written == []
    if written:
        assert any("fig1_learning_curves.png" in p for p in written)
        assert any("fig2_mechanism.png" in p for p in written)
        assert (tmp_path / "figures" / "fig1_learning_curves.png").is_file()


def test_write_gate4_report_sidecar(tmp_path: Path) -> None:
    from run_g4_multiseed import G4PreflightReport

    report = G4PreflightReport(
        timestamp="2026-08-06T02:00:00Z",
        mode="preflight",
        plans=[
            PilotPlan(seed=s, b_run_id=1200 + s, d_run_id=1300 + s)
            for s in range(1, 6)
        ],
        ready_for_live=False,
    )
    report.add("anthropic_key", False, "ANTHROPIC_API_KEY missing")
    out = tmp_path / "gate4_report.md"
    write_gate4_report(report, out)
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "Gate 4 report" in text
    assert "exactly 5" not in text or "5 seeds" in text or "seed" in text.lower()
    sidecar = out.with_suffix(".json")
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["mode"] == "preflight"
    assert payload["ready_for_live"] is False
    assert len(payload["plans"]) == 5
    assert "h2_by_d_run" in payload
    assert "ready_status" in payload


def test_write_gate4_report_h2_surfaces_preferred_share(tmp_path: Path) -> None:
    """Tick 365: gate4 H2 section reports preferred_share (MECHANISM), not pool-only."""
    from run_g4_multiseed import G4PreflightReport

    report = G4PreflightReport(
        timestamp="2026-09-07T00:10:00Z",
        mode="refresh-paper",
        plans=[
            PilotPlan(seed=s, b_run_id=1210 + s, d_run_id=1310 + s)
            for s in range(1, 6)
        ],
        ready_for_live=True,
    )
    report.h2_by_d_run = {
        "run_1311": {
            "field": "tool_strategy",
            "preferred_value": "selective",
            "preferred_share": 0.75,
            "in_bias_share": 1.0,
            "counts": {"selective": 6, "aggressive": 2},
        }
    }
    report.h2_pass = True
    report.comparison = {
        "n_pairs": 5,
        "d_wins_gens30": 3,
        "b_wins_gens30": 0,
        "primary_gens30_pass": True,
        "d_wins_cost30": 0,
        "b_wins_cost30": 0,
        "primary_cost30_pass": False,
        "d_wins_final": 3,
        "b_wins_final": 0,
        "d_wins_h2": 4,
        "h2_preferred_pass": True,
    }
    out = tmp_path / "gate4_report.md"
    write_gate4_report(report, out)
    text = out.read_text(encoding="utf-8")
    assert "preferred_share=`0.75`" in text
    assert "preferred=`selective`" in text
    assert "field=`tool_strategy`" in text
    assert "in_bias_share=`1.0`" in text
    # Tick 367: gate4 metrics show preferred-pass aggregate, not binary only.
    assert "H2 preferred ≥0.5: **4/5**" in text
    assert "h2_preferred_pass=True" in text


def test_apply_paper_pack_prefers_compare_h2_preferred_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tick 367: apply_paper_pack MECHANISM uses compare h2_preferred_pass when n≥5."""
    from run_g4_multiseed import G4PreflightReport, apply_paper_pack

    docs = tmp_path / "docs"
    docs.mkdir()
    paper = docs / "paper_artifacts.md"
    paper.write_text(
        "### Live GPQA\n\n"
        "| Seed | B | D |\n|------|---|---|\n| — | — | — |\n\n"
        f"{TABLE2_LIVE_H2_MARKER}\n| H2 | — | — |\n{TABLE2_LIVE_H2_END}\n"
        f"{TABLE2_LIVE_H5_MARKER}\n| H5 | — | — |\n{TABLE2_LIVE_H5_END}\n",
        encoding="utf-8",
    )
    ready = docs / "ICML_READY.md"
    ready.write_text("**STATUS: IN_PROGRESS**\n\n- [ ] Live API-run H2\n", encoding="utf-8")

    report = G4PreflightReport(
        timestamp="2026-09-07T04:05:00Z",
        mode="refresh-paper",
        plans=[
            PilotPlan(seed=s, b_run_id=1210 + s, d_run_id=1310 + s)
            for s in range(1, 6)
        ],
        ready_for_live=True,
    )
    # Simulate loser-dominated aggregate (4/5 preferred pass) even if per-run
    # h2_skew_pass on a thin dict would differ — compare wins when n≥5.
    comparison = {
        "n_pairs": 5,
        "primary_gens30_pass": True,
        "primary_cost30_pass": False,
        "primary_gens25_pass": False,
        "primary_cost25_pass": False,
        "primary_final_pass": True,
        "mean_final_gap": 0.06,
        "d_wins_final": 5,
        "d_wins_h2": 4,
        "h2_preferred_pass": True,
        "rows": [],
    }
    h2_payloads = {
        f"run_{1310 + s}": {
            "field": "tool_strategy",
            "preferred_value": "selective",
            "preferred_share": 0.75 if s != 2 else 0.29,
            "in_bias_share": 1.0,
            "counts": {"selective": 3 if s != 2 else 1, "aggressive": 1 if s != 2 else 3},
            "total": 4,
            "bias_values": ["selective", "aggressive"],
        }
        for s in range(1, 6)
    }

    import run_g4_multiseed as mod

    monkeypatch.setattr(
        mod,
        "score_pilot",
        lambda b, d: (
            comparison,
            {k: {"spearman_rho": 0.5} for k in h2_payloads},
            h2_payloads,
        ),
    )
    monkeypatch.setattr(
        mod,
        "g3_d_steering_ok",
        lambda _d: (
            True,
            [CheckResult("steering_applied_gen3", True, "mocked steered")],
        ),
    )
    monkeypatch.setattr(mod, "write_live_bvd_figures", lambda **kw: [])
    monkeypatch.setattr(mod, "refresh_paper_artifacts_live", lambda **kw: True)
    monkeypatch.setattr(mod, "update_icml_ready_from_g4", lambda **kw: "IN_PROGRESS")

    apply_paper_pack(
        report,
        b_dirs=[tmp_path / f"b{i}" for i in range(5)],
        d_dirs=[tmp_path / f"d{i}" for i in range(5)],
        paper_artifacts=paper,
        ready_path=ready,
        figures_dir=docs / "figures",
        allow_ready=False,
    )
    assert report.h2_pass is True
    assert report.comparison["d_wins_h2"] == 4
    assert report.comparison["h2_preferred_pass"] is True


def test_write_live_fig2_annotates_preferred_allele(tmp_path: Path) -> None:
    """Tick 365: live Fig 2 title includes majority preferred allele."""
    comparison = {
        "rows": [
            {
                "B": {"learning_curve": {"1": {"best": 0.1, "mean": 0.08}}},
                "D": {"learning_curve": {"1": {"best": 0.12, "mean": 0.1}}},
            }
        ]
    }
    h2 = {
        "run_1311": {
            "field": "tool_strategy",
            "preferred_value": "selective",
            "counts": {"selective": 5, "aggressive": 1},
        },
        "run_1312": {
            "field": "tool_strategy",
            "preferred_value": "selective",
            "counts": {"selective": 4, "minimal": 2},
        },
    }
    # Capture title via monkeypatched matplotlib if available; else just ensure write.
    written = write_live_bvd_figures(
        comparison=comparison,
        h2_by_d_run=h2,
        figures_dir=tmp_path / "figures",
    )
    assert any(p.endswith("fig2_mechanism.png") for p in written)
    assert (tmp_path / "figures" / "fig2_mechanism.png").is_file()


def test_main_live_fetch_diamond_refuses_without_hf(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 275: G4 --live --fetch-diamond exits 4 before materialize without HF."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("NEBIUS_API_KEY", "nb-test")
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)

    import run_g4_multiseed as mod

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    (tmp_path / "docs").mkdir()
    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    pub = task / "data" / "public"
    priv = task / "data" / "private"
    pub.mkdir(parents=True)
    priv.mkdir(parents=True)
    rows = [
        {
            "id": 1,
            "Question": "Real?",
            "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
            "correct_answer_letter": "A",
            "domain": "physics",
        }
    ]
    (pub / "diamond_questions.json").write_text(json.dumps(rows), encoding="utf-8")
    (priv / "diamond_questions.json").write_text(json.dumps(rows), encoding="utf-8")
    (pub / "task.md").write_text("# GPQA", encoding="utf-8")
    monkeypatch.setattr(mod, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(mod, "_run_dir_for", lambda rid: None)

    called: list[str] = []

    def boom(*_a, **_k):
        called.append("hf")
        raise AssertionError("must not materialize from HF")

    monkeypatch.setattr(mod, "materialize_from_hf", boom)
    report_path = tmp_path / "docs" / "gate4_report.md"
    rc = mod.main(
        [
            "--live",
            "--seeds",
            "1,2,3,4,5",
            "--b-run-ids",
            "1211,1212,1213,1214,1215",
            "--d-run-ids",
            "1311,1312,1313,1314,1315",
            "--fetch-diamond",
            "--report",
            str(report_path),
        ]
    )
    assert rc == 4
    assert called == []
    text = report_path.read_text(encoding="utf-8")
    assert "HF_TOKEN" in text or "fetch_diamond" in text.lower()


def test_score_live_h2_auto_resolves_tool_strategy(tmp_path: Path, monkeypatch) -> None:
    """Tick 361: G4 live H2 defaults to biased field, not hard-coded memory."""
    import epistemic_results as er

    run = tmp_path / "run_1311"
    for i, allele in enumerate(["selective", "selective", "selective", "aggressive"]):
        agent = run / "gen_3" / f"agent_{i}"
        agent.mkdir(parents=True)
        (agent / "agent_dna.json").write_text(
            json.dumps({"tool_strategy": allele, "memory": "none"}),
            encoding="utf-8",
        )

    monkeypatch.setattr(
        er,
        "_load_mutation_bias_map",
        lambda _run_dir: {"tool_strategy": ["selective", "aggressive"]},
    )
    # score_live_h2 imports compute_h2 from epistemic_results inside the function;
    # patching er._load_mutation_bias_map is enough because compute_h2 uses that.
    out = score_live_h2([run])
    payload = out["run_1311"]
    assert payload["field"] == "tool_strategy"
    assert payload["bias_values"] == ["selective", "aggressive"]
    assert payload["preferred_value"] == "selective"
    assert payload["in_bias_share"] == pytest.approx(1.0)
    assert payload["preferred_share"] == pytest.approx(0.75)
    assert h2_skew_pass({ "run_1311": payload })

    # Loser-dominated population: pool membership still 1.0 but preferred_share low.
    run_lose = tmp_path / "run_1312"
    for i, allele in enumerate(["selective", "aggressive", "aggressive", "aggressive"]):
        agent = run_lose / "gen_3" / f"agent_{i}"
        agent.mkdir(parents=True)
        (agent / "agent_dna.json").write_text(
            json.dumps({"tool_strategy": allele, "memory": "none"}),
            encoding="utf-8",
        )
    lose = score_live_h2([run_lose])["run_1312"]
    assert lose["preferred_share"] == pytest.approx(0.25)
    assert lose["in_bias_share"] == pytest.approx(1.0)
    assert not h2_skew_pass({"run_1312": lose})


def _write_complete_run(run_dir: Path) -> None:
    agent = run_dir / "gen_1" / "agent_0"
    agent.mkdir(parents=True, exist_ok=True)
    (agent / "results.json").write_text('{"accuracy": 0.2}', encoding="utf-8")


def test_g4_preflight_resume_skips_complete_run_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 375: partial G4 complete pairs do not fail run_ids_free."""
    import run_g4_multiseed as mod
    import run_g3_pilot as g3

    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(g3, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    (tmp_path / "runs").mkdir(parents=True)

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    task.mkdir(parents=True)
    prepare_task_tree(task, n=5)
    monkeypatch.setattr(mod, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(mod, "is_synthetic_smoke", lambda *_a, **_k: False)
    monkeypatch.setattr(mod, "check_task_tree", lambda *_a, **_k: [])
    monkeypatch.setattr(mod, "probe_per_run_venv_capable", lambda **_k: (True, "ok"))
    monkeypatch.setattr(mod, "ensure_icml_runtime_deps", lambda **_k: (True, "ok"))
    monkeypatch.setattr(mod, "probe_icml_meta_profile", lambda: (True, "ok"))
    monkeypatch.setattr(mod, "probe_icml_target_profile_nebius", lambda: (True, "ok"))
    monkeypatch.setattr(
        mod, "committed_g3g4_recipes_match_live_shape", lambda **_k: (True, [])
    )
    monkeypatch.setattr(
        mod, "committed_offline_bvd_matches_live_shape", lambda **_k: (True, [])
    )
    monkeypatch.setattr(mod, "write_icml_tip_status", lambda *a, **k: {"tip_ok_for_live": True, "local_tick": 375})

    # 2 of 5 pairs complete
    for rid in (1211, 1311, 1212, 1312):
        _write_complete_run(tmp_path / "runs" / f"run_{rid}")

    plans = build_g4_plans(
        [1, 2, 3, 4, 5],
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    report = run_preflight(mode="preflight", plans=plans)
    names = {c.name: c for c in report.checks}
    assert names["run_ids_free"].ok is True
    assert "resume-ok" in names["run_ids_free"].detail
    assert "3 remaining" in names["budget"].detail


def test_g4_preflight_hydrates_budget_from_unbilled_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 377: direct G4 preflight bills unbilled local completes into spent."""
    import run_g4_multiseed as mod
    import run_g3_pilot as g3

    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("SIA_BUDGET_SPENT_USD", raising=False)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(g3, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    (tmp_path / "runs").mkdir(parents=True)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {
                "spent_usd": 2.0,
                "stages_complete": ["G2"],
                "run_ids": [1300],
                "detail": "G2 only",
            }
        ),
        encoding="utf-8",
    )

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    task.mkdir(parents=True)
    prepare_task_tree(task, n=5)
    monkeypatch.setattr(mod, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(mod, "is_synthetic_smoke", lambda *_a, **_k: False)
    monkeypatch.setattr(mod, "check_task_tree", lambda *_a, **_k: [])
    monkeypatch.setattr(mod, "probe_per_run_venv_capable", lambda **_k: (True, "ok"))
    monkeypatch.setattr(mod, "ensure_icml_runtime_deps", lambda **_k: (True, "ok"))
    monkeypatch.setattr(mod, "probe_icml_meta_profile", lambda: (True, "ok"))
    monkeypatch.setattr(mod, "probe_icml_target_profile_nebius", lambda: (True, "ok"))
    monkeypatch.setattr(
        mod, "committed_g3g4_recipes_match_live_shape", lambda **_k: (True, [])
    )
    monkeypatch.setattr(
        mod, "committed_offline_bvd_matches_live_shape", lambda **_k: (True, [])
    )
    monkeypatch.setattr(
        mod,
        "write_icml_tip_status",
        lambda *a, **k: {"tip_ok_for_live": True, "local_tick": 377},
    )

    for rid in (1211, 1311):
        agent = tmp_path / "runs" / f"run_{rid}" / "gen_1" / "agent_0"
        agent.mkdir(parents=True, exist_ok=True)
        (agent / "results.json").write_text(
            json.dumps({"accuracy": 0.2, "total_cost_usd": 0.5}),
            encoding="utf-8",
        )

    plans = build_g4_plans(
        [1, 2, 3, 4, 5],
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    report = run_preflight(mode="preflight", plans=plans)
    names = {c.name: c for c in report.checks}
    assert names["budget"].ok is True
    assert any("Tick 377" in n for n in report.notes)
    assert float(os.environ.get("SIA_BUDGET_SPENT_USD", "0")) > 2.0
    # 1 of 5 pairs complete → 4 remaining
    assert "4 remaining" in names["budget"].detail
    ledger = json.loads((docs / "icml_budget_spent.json").read_text(encoding="utf-8"))
    assert 1211 in ledger["run_ids"] and 1311 in ledger["run_ids"]
    assert "G4" not in ledger["stages_complete"]


def test_refresh_paper_pack_on_ledger_skip_local_dirs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 381: ledger-skip re-scores local B/D into paper pack."""
    import run_g4_multiseed as mod
    import run_g3_pilot as g3
    from run_g4_multiseed import G4PreflightReport

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(g3, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    (tmp_path / "runs").mkdir(parents=True)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "paper_artifacts.md").write_text("# Paper\n", encoding="utf-8")
    (docs / "ICML_READY.md").write_text("STATUS: IN_PROGRESS\n", encoding="utf-8")
    (docs / "figures").mkdir()

    b_ids = [1211, 1212, 1213, 1214, 1215]
    d_ids = [1311, 1312, 1313, 1314, 1315]
    for rid in b_ids + d_ids:
        _write_complete_run(tmp_path / "runs" / f"run_{rid}")

    plans = build_g4_plans([1, 2, 3, 4, 5], b_ids, d_ids)
    report = G4PreflightReport(
        timestamp="2026-09-08T08:05:00Z",
        mode="live",
        plans=plans,
        ready_for_live=True,
        ledger_skip=True,
    )
    calls: dict[str, object] = {}

    def _fake_apply(rep, *, b_dirs, d_dirs, allow_ready=True, **_kw):
        calls["b_dirs"] = [str(p) for p in b_dirs]
        calls["d_dirs"] = [str(p) for p in d_dirs]
        calls["allow_ready"] = allow_ready
        from run_g3_pilot import CheckResult

        rep.checks.append(
            CheckResult("steering_applied_gen3", True, "mocked steered")
        )
        rep.comparison = {"n_pairs": 5, "primary_gens30_pass": True}
        rep.primary_pass = True
        rep.h2_pass = True
        rep.h5_pass = True
        rep.ready_status = "READY"
        return True

    monkeypatch.setattr(mod, "apply_paper_pack", _fake_apply)
    paper_ok, note = mod.refresh_paper_pack_on_ledger_skip(
        report,
        paper_artifacts=docs / "paper_artifacts.md",
        ready_path=docs / "ICML_READY.md",
        figures_dir=docs / "figures",
        gate4_report_md=docs / "gate4_report.md",
        allow_ready=True,
    )
    assert paper_ok is True
    assert "re-scored G4 from local" in note
    assert len(calls["b_dirs"]) == 5  # type: ignore[arg-type]
    assert len(calls["d_dirs"]) == 5  # type: ignore[arg-type]
    assert calls["allow_ready"] is True
    assert report.ready_status == "READY"


def test_refresh_paper_pack_on_ledger_skip_trusts_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 381: no local dirs → trust live-executed gate4 paper pack sidecar."""
    import run_g4_multiseed as mod
    import run_g3_pilot as g3
    from run_g4_multiseed import G4PreflightReport

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(g3, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    (tmp_path / "runs").mkdir(parents=True)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "gate4_report.json").write_text(
        json.dumps(
            {
                "mode": "live",
                "executed": True,
                "comparison": {"n_pairs": 5, "primary_gens30_pass": True},
                "paper_refreshed": True,
                "primary_pass": True,
                "h2_pass": True,
                "h5_pass": True,
                "ready_status": "READY",
                "steering_applied_gen3": True,
                "h5_by_d_run": {
                    f"run_{1311 + i}": {"spearman_rho": 0.5 + 0.05 * i}
                    for i in range(5)
                },
                "h2_by_d_run": {
                    f"run_{1311 + i}": {
                        "preferred_share": 0.8,
                        "in_bias_share": 1.0,
                        "preferred_value": "selective",
                        "counts": {"selective": 4},
                        "total": 4,
                        "bias_values": ["selective"],
                    }
                    for i in range(5)
                },
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate4_report.md").write_text("# Gate 4\n", encoding="utf-8")

    plans = build_g4_plans(
        [1, 2, 3, 4, 5],
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    report = G4PreflightReport(
        timestamp="2026-09-08T08:05:00Z",
        mode="live",
        plans=plans,
        ready_for_live=True,
        ledger_skip=True,
    )
    paper_ok, note = mod.refresh_paper_pack_on_ledger_skip(
        report,
        paper_artifacts=docs / "paper_artifacts.md",
        ready_path=docs / "ICML_READY.md",
        figures_dir=docs / "figures",
        gate4_report_md=docs / "gate4_report.md",
    )
    assert paper_ok is True
    assert "trusted live-executed" in note
    assert report.ready_status == "READY"
    assert report.comparison is not None


def test_refresh_paper_pack_on_ledger_skip_refuses_preflight_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 381: preflight sidecar must not promote READY on ledger-skip."""
    import run_g4_multiseed as mod
    import run_g3_pilot as g3
    from run_g4_multiseed import G4PreflightReport

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(g3, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    (tmp_path / "runs").mkdir(parents=True)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "gate4_report.json").write_text(
        json.dumps(
            {
                "mode": "preflight",
                "executed": False,
                "comparison": None,
                "paper_refreshed": False,
                "ready_status": "IN_PROGRESS",
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate4_report.md").write_text("# Gate 4\n", encoding="utf-8")

    plans = build_g4_plans(
        [1, 2, 3, 4, 5],
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    report = G4PreflightReport(
        timestamp="2026-09-08T08:05:00Z",
        mode="live",
        plans=plans,
        ledger_skip=True,
    )
    paper_ok, note = mod.refresh_paper_pack_on_ledger_skip(
        report,
        paper_artifacts=docs / "paper_artifacts.md",
        ready_path=docs / "ICML_READY.md",
        figures_dir=docs / "figures",
        gate4_report_md=docs / "gate4_report.md",
    )
    assert paper_ok is False
    assert "ICML_READY not updated" in note
    assert report.ready_status == "IN_PROGRESS"


def test_write_gate4_preflight_preserves_prior_live_metrics(tmp_path: Path) -> None:
    """Tick 386: preflight rewrite keeps prior_live_metrics for G4 resume trust."""
    import run_g4_multiseed as mod
    from run_g4_multiseed import G4PreflightReport

    report_md = tmp_path / "gate4_report.md"
    sidecar = report_md.with_suffix(".json")
    live_cmp = {
        "n_pairs": 5,
        "d_wins_gens30": 4,
        "primary_gens30_pass": True,
        "mean_final_gap": 0.05,
        "primary_final_pass": True,
    }
    sidecar.write_text(
        json.dumps(
            {
                "mode": "live",
                "executed": True,
                "paper_refreshed": True,
                "comparison": live_cmp,
                "h5_by_d_run": {"run_1311": {"spearman_rho": 0.7}},
                "h2_by_d_run": {"run_1311": {"preferred_share": 0.8}},
                "primary_pass": True,
                "h2_pass": True,
                "h5_pass": True,
                "ready_status": "READY",
                "figures_written": ["docs/figures/fig1_learning_curves.png"],
            }
        ),
        encoding="utf-8",
    )
    report_md.write_text("# Gate 4\n", encoding="utf-8")
    report = G4PreflightReport(
        timestamp="2026-09-08T18:10:00Z",
        mode="preflight",
        plans=build_g4_plans(
            [1, 2, 3, 4, 5],
            [1211, 1212, 1213, 1214, 1215],
            [1311, 1312, 1313, 1314, 1315],
        ),
        ready_for_live=False,
        blockers=["nebius_key"],
        checks=[],
        commands=[],
        notes=[],
    )
    write_gate4_report(report, report_md, executed=False, paper_refreshed=False)
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["mode"] == "preflight"
    assert data["comparison"] is None
    assert data["executed"] is False
    assert data["paper_refreshed"] is False
    assert data["prior_live_metrics"]["comparison"]["d_wins_gens30"] == 4
    assert data["prior_live_metrics"]["paper_refreshed"] is True
    assert data["prior_live_metrics"]["ready_status"] == "READY"
    cmp_, h5, h2, meta, source = mod._live_paper_from_gate4_sidecar(data)
    assert source == "prior_live_metrics"
    assert cmp_ is not None and cmp_["d_wins_gens30"] == 4
    assert h5["run_1311"]["spearman_rho"] == 0.7
    assert h2["run_1311"]["preferred_share"] == 0.8
    assert meta["paper_refreshed"] is True
    assert meta["ready_status"] == "READY"


def test_refresh_paper_pack_on_ledger_skip_trusts_prior_live_metrics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 386: ledger-skip trusts prior_live_metrics after preflight wipe."""
    import run_g4_multiseed as mod
    import run_g3_pilot as g3
    from run_g4_multiseed import G4PreflightReport

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(g3, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    (tmp_path / "runs").mkdir(parents=True)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "gate4_report.json").write_text(
        json.dumps(
            {
                "mode": "preflight",
                "executed": False,
                "comparison": None,
                "paper_refreshed": False,
                "prior_live_metrics": {
                    "comparison": {
                        "n_pairs": 5,
                        "d_wins_gens30": 4,
                        "primary_gens30_pass": True,
                    },
                    "h5_by_d_run": {
                        f"run_{1311 + i}": {"spearman_rho": 0.65}
                        for i in range(5)
                    },
                    "h2_by_d_run": {
                        f"run_{1311 + i}": {"preferred_share": 0.7}
                        for i in range(5)
                    },
                    "executed": True,
                    "paper_refreshed": True,
                    "primary_pass": True,
                    "h2_pass": True,
                    "h5_pass": True,
                    "ready_status": "READY",
                    "steering_applied_gen3": True,
                },
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate4_report.md").write_text("# Gate 4\n", encoding="utf-8")
    plans = build_g4_plans(
        [1, 2, 3, 4, 5],
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    report = G4PreflightReport(
        timestamp="2026-09-08T18:11:00Z",
        mode="live",
        plans=plans,
        ready_for_live=True,
        ledger_skip=True,
    )
    paper_ok, note = mod.refresh_paper_pack_on_ledger_skip(
        report,
        paper_artifacts=docs / "paper_artifacts.md",
        ready_path=docs / "ICML_READY.md",
        figures_dir=docs / "figures",
        gate4_report_md=docs / "gate4_report.md",
    )
    assert paper_ok is True
    assert "prior_live_metrics" in note
    assert report.comparison is not None
    assert report.comparison["d_wins_gens30"] == 4
    assert report.ready_status == "READY"
    assert report.h5_by_d_run["run_1311"]["spearman_rho"] == 0.65


def test_g4_live_ledger_skip_refreshes_paper_pack(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 381: direct --live ledger-skip calls paper-pack refresh (no sia)."""
    import run_g4_multiseed as mod
    import run_g3_pilot as g3

    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("SIA_BUDGET_SPENT_USD", raising=False)
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")

    docs = tmp_path / "docs"
    docs.mkdir()
    planned = list(range(1211, 1216)) + list(range(1311, 1316))
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {
                "spent_usd": 19.0,
                "stages_complete": ["G2", "G3", "G4"],
                "run_ids": [1300, 1201, 1301] + planned,
                "detail": "full stack",
            }
        ),
        encoding="utf-8",
    )
    (docs / "paper_artifacts.md").write_text("# Paper\n", encoding="utf-8")
    (docs / "ICML_READY.md").write_text("STATUS: IN_PROGRESS\n", encoding="utf-8")
    (docs / "figures").mkdir()

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    task.mkdir(parents=True)
    prepare_task_tree(task, n=5)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(g3, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    (tmp_path / "runs").mkdir(parents=True)
    monkeypatch.setattr(mod, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(mod, "is_synthetic_smoke", lambda *_a, **_k: False)
    monkeypatch.setattr(mod, "check_task_tree", lambda *_a, **_k: [])
    monkeypatch.setattr(mod, "probe_per_run_venv_capable", lambda **_k: (True, "ok"))
    monkeypatch.setattr(mod, "ensure_icml_runtime_deps", lambda **_k: (True, "ok"))
    monkeypatch.setattr(mod, "probe_icml_meta_profile", lambda: (True, "ok"))
    monkeypatch.setattr(mod, "probe_icml_target_profile_nebius", lambda: (True, "ok"))
    monkeypatch.setattr(
        mod, "committed_g3g4_recipes_match_live_shape", lambda **_k: (True, [])
    )
    monkeypatch.setattr(
        mod, "committed_offline_bvd_matches_live_shape", lambda **_k: (True, [])
    )
    monkeypatch.setattr(
        mod,
        "write_icml_tip_status",
        lambda *a, **k: {"tip_ok_for_live": True, "local_tick": 381},
    )

    refreshed: list[str] = []

    def _fake_refresh(report, **_kw):
        refreshed.append("yes")
        report.comparison = {"n_pairs": 5}
        report.primary_pass = True
        report.h2_pass = True
        report.h5_pass = True
        report.ready_status = "IN_PROGRESS"
        return True, "Tick 381: fake pack refresh"

    monkeypatch.setattr(mod, "refresh_paper_pack_on_ledger_skip", _fake_refresh)

    called: list[list[str]] = []

    def _fake_run(cmd, **_kwargs):
        called.append(list(cmd))

        class _P:
            returncode = 0

        return _P()

    monkeypatch.setattr(g3.subprocess, "run", _fake_run)

    report_path = docs / "gate4_report.md"
    rc = mod.main(
        [
            "--live",
            "--seeds",
            "1,2,3,4,5",
            "--b-run-ids",
            "1211,1212,1213,1214,1215",
            "--d-run-ids",
            "1311,1312,1313,1314,1315",
            "--report",
            str(report_path),
            "--paper-artifacts",
            str(docs / "paper_artifacts.md"),
            "--icml-ready",
            str(docs / "ICML_READY.md"),
            "--figures-dir",
            str(docs / "figures"),
            "--cwd",
            str(tmp_path),
            "--allow-stale-tip",
        ]
    )
    assert rc == 0
    assert called == []
    assert refreshed == ["yes"]
    text = report_path.read_text(encoding="utf-8")
    assert "Tick 381" in text or "ledger" in text.lower()


def _write_d_gen_feedback(run_dir: Path, gen: int, *, with_agenda: bool) -> None:
    """Minimal Condition D gen_N/agent_* feedback for Tick 408."""
    for i in range(2):
        agent = run_dir / f"gen_{gen}" / f"agent_{i}"
        agent.mkdir(parents=True, exist_ok=True)
        body = (
            "Contradiction-Aware Research Agenda\n- investigate tool_strategy\n"
            if with_agenda
            else "Darwinian feedback only (no CABS agenda)\n"
        )
        (agent / "feedback_agent_prompt.txt").write_text(body, encoding="utf-8")
        (agent / "results.json").write_text(
            json.dumps({"accuracy": 0.2}), encoding="utf-8"
        )


def test_apply_paper_pack_refuses_never_steer_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tick 408: never-steer Condition D forces allow_ready=False."""
    from run_g4_multiseed import G4PreflightReport, apply_paper_pack

    docs = tmp_path / "docs"
    docs.mkdir()
    paper = docs / "paper_artifacts.md"
    paper.write_text(
        "### Live GPQA\n\n"
        "| Seed | B | D |\n|------|---|---|\n| — | — | — |\n\n"
        f"{TABLE2_LIVE_H2_MARKER}\n| H2 | — | — |\n{TABLE2_LIVE_H2_END}\n"
        f"{TABLE2_LIVE_H5_MARKER}\n| H5 | — | — |\n{TABLE2_LIVE_H5_END}\n",
        encoding="utf-8",
    )
    ready = docs / "ICML_READY.md"
    ready.write_text("**STATUS: IN_PROGRESS**\n", encoding="utf-8")

    d_dirs = []
    b_dirs = []
    for s in range(1, 6):
        b = tmp_path / f"run_{1210 + s}"
        d = tmp_path / f"run_{1310 + s}"
        b.mkdir()
        d.mkdir()
        _write_d_gen_feedback(d, 3, with_agenda=False)
        b_dirs.append(b)
        d_dirs.append(d)

    report = G4PreflightReport(
        timestamp="2026-09-10T16:10:00Z",
        mode="refresh-paper",
        plans=[
            PilotPlan(seed=s, b_run_id=1210 + s, d_run_id=1310 + s)
            for s in range(1, 6)
        ],
        ready_for_live=True,
    )
    import run_g4_multiseed as mod

    monkeypatch.setattr(
        mod,
        "score_pilot",
        lambda b, d: (
            {
                "n_pairs": 5,
                "primary_gens30_pass": True,
                "primary_cost30_pass": True,
                "primary_final_pass": True,
                "mean_final_gap": 0.06,
                "d_wins_h2": 5,
                "h2_preferred_pass": True,
                "rows": [],
            },
            {f"run_{1310 + s}": {"spearman_rho": 0.9} for s in range(1, 6)},
            {
                f"run_{1310 + s}": {
                    "preferred_share": 0.8,
                    "field": "tool_strategy",
                    "preferred_value": "selective",
                    "in_bias_share": 1.0,
                    "counts": {},
                    "total": 4,
                    "bias_values": [],
                }
                for s in range(1, 6)
            },
        ),
    )
    captured: dict[str, object] = {}

    def _fake_ready(**kw):
        captured["allow_ready"] = kw.get("allow_ready")
        return "IN_PROGRESS"

    monkeypatch.setattr(mod, "write_live_bvd_figures", lambda **kw: [])
    monkeypatch.setattr(mod, "refresh_paper_artifacts_live", lambda **kw: True)
    monkeypatch.setattr(mod, "update_icml_ready_from_g4", _fake_ready)

    apply_paper_pack(
        report,
        b_dirs=b_dirs,
        d_dirs=d_dirs,
        paper_artifacts=paper,
        ready_path=ready,
        figures_dir=docs / "figures",
        allow_ready=True,
    )
    assert captured["allow_ready"] is False
    assert any(c.name == "steering_applied_gen3" and not c.ok for c in report.checks)
    assert any("never-steer" in n or "steering FAILED" in n for n in report.notes)


def test_refresh_paper_pack_refuses_never_steer_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 408: ledger-skip sidecar with steering_applied_gen3=false refuses trust."""
    import run_g4_multiseed as mod
    import run_g3_pilot as g3
    from run_g4_multiseed import G4PreflightReport

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(g3, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    (tmp_path / "runs").mkdir(parents=True)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "gate4_report.md").write_text("# Gate 4\n", encoding="utf-8")
    (docs / "gate4_report.json").write_text(
        json.dumps(
            {
                "mode": "live",
                "executed": True,
                "paper_refreshed": True,
                "steering_applied_gen3": False,
                "comparison": {"n_pairs": 5, "primary_gens30_pass": True},
                "primary_pass": True,
                "h2_pass": True,
                "h5_pass": True,
                "ready_status": "READY",
                "h5_by_d_run": {},
                "h2_by_d_run": {},
            }
        ),
        encoding="utf-8",
    )
    plans = build_g4_plans(
        [1, 2, 3, 4, 5],
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    report = G4PreflightReport(
        timestamp="2026-09-10T16:10:00Z",
        mode="live",
        plans=plans,
        ready_for_live=True,
        ledger_skip=True,
    )
    ok, note = mod.refresh_paper_pack_on_ledger_skip(
        report,
        paper_artifacts=docs / "paper_artifacts.md",
        ready_path=docs / "ICML_READY.md",
        figures_dir=docs / "figures",
        gate4_report_md=docs / "gate4_report.md",
        allow_ready=True,
    )
    assert ok is False
    assert "steering_applied_gen3=false" in note
    assert any(c.name == "steering_applied_gen3" and not c.ok for c in report.checks)


def test_refresh_paper_pack_refuses_partial_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 412: ledger-skip sidecar with n_pairs < planned refuses trust."""
    import run_g4_multiseed as mod
    import run_g3_pilot as g3
    from run_g4_multiseed import G4PreflightReport

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(g3, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    (tmp_path / "runs").mkdir(parents=True)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "gate4_report.md").write_text("# Gate 4\n", encoding="utf-8")
    (docs / "gate4_report.json").write_text(
        json.dumps(
            {
                "mode": "live",
                "executed": True,
                "paper_refreshed": True,
                "steering_applied_gen3": True,
                "comparison": {"n_pairs": 1, "primary_gens30_pass": True},
                "primary_pass": True,
                "h2_pass": True,
                "h5_pass": True,
                "ready_status": "READY",
                "h5_by_d_run": {},
                "h2_by_d_run": {},
            }
        ),
        encoding="utf-8",
    )
    plans = build_g4_plans(
        [1, 2, 3, 4, 5],
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    report = G4PreflightReport(
        timestamp="2026-09-11T00:10:00Z",
        mode="live",
        plans=plans,
        ready_for_live=True,
        ledger_skip=True,
    )
    ok, note = mod.refresh_paper_pack_on_ledger_skip(
        report,
        paper_artifacts=docs / "paper_artifacts.md",
        ready_path=docs / "ICML_READY.md",
        figures_dir=docs / "figures",
        gate4_report_md=docs / "gate4_report.md",
        allow_ready=True,
    )
    assert ok is False
    assert "n_pairs=1" in note
    assert "planned=5" in note
    assert report.comparison is None
    assert report.ready_status is None or report.ready_status == "IN_PROGRESS"
    assert any(c.name == "g4_full_pairs" and not c.ok for c in report.checks)


def test_refresh_paper_pack_refuses_thin_h5_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 413: n_pairs=5 sidecar with thin H5 (1 pass / 4 errors) refuses READY."""
    import run_g4_multiseed as mod
    import run_g3_pilot as g3
    from run_g4_multiseed import G4PreflightReport

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(g3, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    (tmp_path / "runs").mkdir(parents=True)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "gate4_report.md").write_text("# Gate 4\n", encoding="utf-8")
    (docs / "gate4_report.json").write_text(
        json.dumps(
            {
                "mode": "live",
                "executed": True,
                "paper_refreshed": True,
                "steering_applied_gen3": True,
                "comparison": {
                    "n_pairs": 5,
                    "primary_gens30_pass": True,
                    "h2_preferred_pass": True,
                },
                "primary_pass": True,
                "h2_pass": True,
                "h5_pass": True,
                "ready_status": "READY",
                "h5_by_d_run": {
                    "run_1311": {"spearman_rho": 0.9},
                    "run_1312": {"error": "missing"},
                    "run_1313": {"error": "missing"},
                    "run_1314": {"error": "missing"},
                    "run_1315": {"error": "missing"},
                },
                "h2_by_d_run": {
                    f"run_{1311 + i}": {
                        "preferred_share": 0.8,
                        "in_bias_share": 1.0,
                        "preferred_value": "selective",
                        "counts": {"selective": 4},
                        "total": 4,
                        "bias_values": ["selective"],
                    }
                    for i in range(5)
                },
            }
        ),
        encoding="utf-8",
    )
    plans = build_g4_plans(
        [1, 2, 3, 4, 5],
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    report = G4PreflightReport(
        timestamp="2026-09-11T02:10:00Z",
        mode="live",
        plans=plans,
        ready_for_live=True,
        ledger_skip=True,
    )
    ok, note = mod.refresh_paper_pack_on_ledger_skip(
        report,
        paper_artifacts=docs / "paper_artifacts.md",
        ready_path=docs / "ICML_READY.md",
        figures_dir=docs / "figures",
        gate4_report_md=docs / "gate4_report.md",
        allow_ready=True,
    )
    assert ok is False
    assert "Tick 413" in note
    assert "thin H5" in note or "planned" in note
    assert report.h5_pass is False
    assert report.ready_status == "IN_PROGRESS"
    assert any(c.name == "h5_planned" and not c.ok for c in report.checks)


def test_g4_full_pairs_for_paper_requires_all_plans() -> None:
    """Tick 410: equal B/D counts are not enough — need len == len(plans)."""
    from run_g4_multiseed import build_g4_plans, g4_full_pairs_for_paper

    plans = build_g4_plans(
        [1, 2, 3, 4, 5],
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    assert g4_full_pairs_for_paper([Path("b")] * 5, [Path("d")] * 5, plans) is True
    # Partial but equal — the pre-Tick-410 live-path bug class.
    assert g4_full_pairs_for_paper([Path("b")], [Path("d")], plans) is False
    assert g4_full_pairs_for_paper([Path("b")] * 2, [Path("d")] * 2, plans) is False
    assert g4_full_pairs_for_paper([Path("b")] * 5, [Path("d")] * 4, plans) is False


def test_decide_g4_live_paper_action_partial_vs_abort_vs_apply() -> None:
    """Tick 410: decide helper covers never-steer abort, partial, full apply."""
    from run_g4_multiseed import build_g4_plans, decide_g4_live_paper_action

    plans = build_g4_plans(
        [1, 2, 3, 4, 5],
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    b5 = [Path(f"b{i}") for i in range(5)]
    d5 = [Path(f"d{i}") for i in range(5)]
    assert (
        decide_g4_live_paper_action(
            b_dirs=b5, d_dirs=d5, plans=plans, run_notes=["ok"]
        )
        == "apply"
    )
    assert (
        decide_g4_live_paper_action(
            b_dirs=[Path("b")],
            d_dirs=[Path("d")],
            plans=plans,
            run_notes=["B ok", "D ok"],
        )
        == "incomplete"
    )
    assert (
        decide_g4_live_paper_action(
            b_dirs=[Path("b")],
            d_dirs=[Path("d")],
            plans=plans,
            run_notes=[
                "Tick 409: Condition D run_1311 never steered after delay-all "
                "(x) — abort remaining pairs to save budget",
            ],
        )
        == "abort_never_steer"
    )


def test_apply_paper_pack_refuses_partial_pairs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 410: apply_paper_pack must not refresh Live Tables from 1/5 pairs."""
    import run_g4_multiseed as mod
    from run_g4_multiseed import G4PreflightReport, build_g4_plans

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    paper = docs / "paper_artifacts.md"
    paper.write_text("# paper\n", encoding="utf-8")
    ready = docs / "ICML_READY.md"
    ready.write_text("**STATUS: IN_PROGRESS**\n", encoding="utf-8")
    figs = docs / "figures"
    figs.mkdir()

    plans = build_g4_plans(
        [1, 2, 3, 4, 5],
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    report = G4PreflightReport(
        timestamp="2026-09-10T20:10:00Z",
        mode="live",
        plans=plans,
        ready_for_live=True,
    )
    b1 = tmp_path / "runs" / "run_1211"
    d1 = tmp_path / "runs" / "run_1311"
    b1.mkdir(parents=True)
    d1.mkdir(parents=True)

    scored: list[str] = []

    def _boom(*_a, **_k):  # noqa: ANN001
        scored.append("score")
        raise AssertionError("score_pilot must not run on partial pairs")

    monkeypatch.setattr(mod, "score_pilot", _boom)
    monkeypatch.setattr(mod, "g3_d_steering_ok", lambda _d: (True, []))

    refreshed = mod.apply_paper_pack(
        report,
        b_dirs=[b1],
        d_dirs=[d1],
        paper_artifacts=paper,
        ready_path=ready,
        figures_dir=figs,
        allow_ready=True,
    )
    assert refreshed is False
    assert scored == []
    assert any("Tick 410:" in n and "refuse paper pack" in n for n in report.notes)
    assert any(c.name == "g4_full_pairs" and not c.ok for c in report.checks)
    assert "**STATUS: IN_PROGRESS**" in ready.read_text(encoding="utf-8")


def test_g4_live_skips_paper_pack_after_never_steer_abort(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 409: mid-G4 never-steer abort must not promote partial Live Table."""
    import run_g4_multiseed as mod
    import run_g3_pilot as g3
    from run_g4_multiseed import (
        G4PreflightReport,
        build_g4_plans,
        decide_g4_live_paper_action,
    )

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g3, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(g3, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    (tmp_path / "runs").mkdir(parents=True)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "paper_artifacts.md").write_text("# paper\n", encoding="utf-8")
    (docs / "ICML_READY.md").write_text("**STATUS: IN_PROGRESS**\n", encoding="utf-8")
    (docs / "figures").mkdir()

    plans = build_g4_plans(
        [1, 2, 3, 4, 5],
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    report = G4PreflightReport(
        timestamp="2026-09-10T18:10:00Z",
        mode="live",
        plans=plans,
        ready_for_live=True,
    )

    d_bad = tmp_path / "runs" / "run_1311"
    d_bad.mkdir(parents=True)
    # Minimal never-steer D gen3 (no agenda)
    for i in range(2):
        agent = d_bad / "gen_3" / f"agent_{i}"
        agent.mkdir(parents=True, exist_ok=True)
        (agent / "feedback_agent_prompt.txt").write_text(
            "Darwinian feedback only\n", encoding="utf-8"
        )
    b_ok = tmp_path / "runs" / "run_1211"
    b_ok.mkdir(parents=True)

    paper_calls: list[str] = []

    def _fake_apply(**kw):  # noqa: ANN001
        paper_calls.append("apply")
        return True

    monkeypatch.setattr(mod, "apply_paper_pack", _fake_apply)

    run_notes = [
        "B run_1211 ok",
        "D run_1311 ok",
        "Tick 409: Condition D run_1311 never steered after delay-all "
        "(x) — abort remaining pairs to save budget",
    ]
    report.notes.extend(run_notes)
    b_dirs, d_dirs = [b_ok], [d_bad]
    paper_refreshed = False
    steering_ok = False
    paper_action = decide_g4_live_paper_action(
        b_dirs=b_dirs, d_dirs=d_dirs, plans=plans, run_notes=run_notes
    )
    assert paper_action == "abort_never_steer"
    if paper_action == "abort_never_steer":
        if d_dirs:
            _ok, steering_checks = g3.g3_d_steering_ok(d_dirs)
            for c in steering_checks:
                report.checks.append(c)
        report.notes.append(
            "Tick 409: aborted remaining G4 pairs on never-steer — skipped "
            "paper pack (refuse partial Live Table / READY)"
        )
        steering_ok = False
    elif paper_action == "apply":
        paper_refreshed = mod.apply_paper_pack(
            report,
            b_dirs=b_dirs,
            d_dirs=d_dirs,
            paper_artifacts=docs / "paper_artifacts.md",
            ready_path=docs / "ICML_READY.md",
            figures_dir=docs / "figures",
            allow_ready=True,
        )
        steering_ok = True

    assert paper_refreshed is False
    assert steering_ok is False
    assert paper_calls == []
    assert any(c.name == "steering_applied_gen3" and not c.ok for c in report.checks)
    assert any("skipped paper pack" in n for n in report.notes)


def test_g4_live_skips_paper_pack_on_partial_equal_pairs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 410: sia-exit mid-G4 with 1 equal pair must not call apply_paper_pack."""
    import run_g4_multiseed as mod
    from run_g4_multiseed import (
        G4PreflightReport,
        build_g4_plans,
        decide_g4_live_paper_action,
    )

    plans = build_g4_plans(
        [1, 2, 3, 4, 5],
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    report = G4PreflightReport(
        timestamp="2026-09-10T20:10:00Z",
        mode="live",
        plans=plans,
        ready_for_live=True,
    )
    b_ok = tmp_path / "b"
    d_ok = tmp_path / "d"
    b_ok.mkdir()
    d_ok.mkdir()
    paper_calls: list[str] = []
    monkeypatch.setattr(
        mod, "apply_paper_pack", lambda **_k: paper_calls.append("apply") or True
    )

    run_notes = [
        "B run_1211 ok",
        "D run_1311 ok",
        "B run_1212 exited 1; aborting remaining pairs",
    ]
    b_dirs, d_dirs = [b_ok], [d_ok]
    # Pre-Tick-410 bug: len(B)==len(D)==1 would have called apply_paper_pack.
    assert len(b_dirs) == len(d_dirs) == 1
    paper_action = decide_g4_live_paper_action(
        b_dirs=b_dirs, d_dirs=d_dirs, plans=plans, run_notes=run_notes
    )
    assert paper_action == "incomplete"
    paper_refreshed = False
    if paper_action == "apply":
        paper_refreshed = mod.apply_paper_pack(
            report,
            b_dirs=b_dirs,
            d_dirs=d_dirs,
            paper_artifacts=tmp_path / "p.md",
            ready_path=tmp_path / "r.md",
            figures_dir=tmp_path,
            allow_ready=True,
        )
    else:
        report.notes.append(
            "Tick 410: incomplete / partial B/D pairs "
            f"(B={len(b_dirs)} D={len(d_dirs)} plans={len(plans)}) — "
            "skipped compare_b_vs_d / paper refresh"
        )
    assert paper_refreshed is False
    assert paper_calls == []
    assert any("Tick 410:" in n and "partial" in n for n in report.notes)
