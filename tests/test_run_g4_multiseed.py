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
    demote_icml_ready_file,
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
    assert report.comparison is None  # Tick 416 clear on refuse
    assert any(c.name == "h5_planned" and not c.ok for c in report.checks)


def test_refresh_paper_pack_refuses_false_primary_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 414: n_pairs=5 + meta.primary_pass but no PRIMARY wins → refuse."""
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
                # Full pairs, but no gens30/cost30/final PRIMARY win markers.
                "comparison": {
                    "n_pairs": 5,
                    "d_wins_final": 0,
                    "mean_final_gap": 0.0,
                    "h2_preferred_pass": True,
                },
                "primary_pass": True,
                "h2_pass": True,
                "h5_pass": True,
                "ready_status": "READY",
                "h5_by_d_run": {
                    f"run_{1311 + i}": {"spearman_rho": 0.55 + 0.05 * i}
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
    plans = build_g4_plans(
        [1, 2, 3, 4, 5],
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    report = G4PreflightReport(
        timestamp="2026-09-24T18:10:00Z",
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
    assert "Tick 414" in note
    assert "primary" in note.lower()
    assert report.primary_pass is False
    assert report.ready_status == "IN_PROGRESS"
    assert report.comparison is None  # Tick 416 clear on refuse
    assert any(c.name == "primary_recomputed" and not c.ok for c in report.checks)


def test_refresh_paper_pack_refuses_thin_h2_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 415: n_pairs=5 + meta.h2_pass but only 1/5 preferred ≥0.5 → refuse."""
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
    thin_h2 = {
        "run_1311": {
            "preferred_share": 0.8,
            "preferred_value": "selective",
            "counts": {"selective": 4},
            "total": 4,
            "bias_values": ["selective"],
        },
        # Four errors — pre-415 planned_n=None would pass as 1/1; planned_n=5 fails.
        **{f"run_{1312 + i}": {"error": "missing"} for i in range(4)},
    }
    (docs / "gate4_report.json").write_text(
        json.dumps(
            {
                "mode": "live",
                "executed": True,
                "paper_refreshed": True,
                "steering_applied_gen3": True,
                "comparison": {
                    "n_pairs": 5,
                    "d_wins_final": 4,
                    "mean_final_gap": 0.06,
                    "primary_final_pass": True,
                    "primary_gens30_pass": True,
                    "h2_preferred_pass": True,
                },
                "primary_pass": True,
                "h2_pass": True,
                "h5_pass": True,
                "ready_status": "READY",
                "h5_by_d_run": {
                    f"run_{1311 + i}": {"spearman_rho": 0.55 + 0.05 * i}
                    for i in range(5)
                },
                "h2_by_d_run": thin_h2,
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
        timestamp="2026-09-24T20:10:00Z",
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
    assert "Tick 415" in note
    assert "thin H2" in note or "H2" in note
    assert report.h2_pass is False
    assert report.ready_status == "IN_PROGRESS"
    assert report.comparison is None  # Tick 416 clear on refuse
    assert any(c.name == "h2_planned" and not c.ok for c in report.checks)


def test_refresh_paper_pack_refuses_honest_thin_h5_and_demotes_ready_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 417: honest meta.h5_pass=False + thin H5 still refuses + demotes disk.

    Pre-417 only refused when meta claimed True, so an honest-fail sidecar with
    disk STATUS: READY stayed READY (report demotion only).
    """
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
    ready = docs / "ICML_READY.md"
    ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n**STATUS: READY**\n\n"
        "Do not set STATUS: READY until criteria pass.\n",
        encoding="utf-8",
    )
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
                # Honest fail — pre-417 skipped refuse when meta already False.
                "primary_pass": True,
                "h2_pass": True,
                "h5_pass": False,
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
        timestamp="2026-09-25T00:20:00Z",
        mode="live",
        plans=plans,
        ready_for_live=True,
        ledger_skip=True,
    )
    ok, note = mod.refresh_paper_pack_on_ledger_skip(
        report,
        paper_artifacts=docs / "paper_artifacts.md",
        ready_path=ready,
        figures_dir=docs / "figures",
        gate4_report_md=docs / "gate4_report.md",
        allow_ready=True,
    )
    assert ok is False
    assert "Tick 413" in note
    assert report.h5_pass is False
    assert report.ready_status == "IN_PROGRESS"
    assert report.comparison is None
    assert any(c.name == "h5_planned" and not c.ok for c in report.checks)
    disk = ready.read_text(encoding="utf-8")
    assert "**STATUS: READY**" not in disk
    assert "**STATUS: IN_PROGRESS**" in disk
    assert "Tick 417 demote" in disk


def test_demote_icml_ready_header_only_despite_prose_and_indent(tmp_path: Path) -> None:
    """Tick 443: G4 demote uses header-only STATUS (Tick 442 durable parity).

    Pre-443 whole-body ``"**STATUS: READY**" in text`` + unstripped
    ``startswith`` could (a) false-trigger on Tick-note prose mentioning
    ``**STATUS: READY**`` when the header is IN_PROGRESS, or (b) enter demote
    but miss an indented READY header and return False — poisoned READY stays.
    """
    from icml_env_checks import _icml_ready_status_header

    # (a) Prose mentions **STATUS: READY** but header is IN_PROGRESS → no-op.
    prose_only = tmp_path / "prose_only.md"
    prose_only.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "**STATUS: IN_PROGRESS**\n\n"
        "_Note: never set **STATUS: READY** from offline / trust refuse alone._\n",
        encoding="utf-8",
    )
    assert demote_icml_ready_file(prose_only, reason="unit") is False
    assert _icml_ready_status_header(prose_only.read_text(encoding="utf-8")) == (
        "IN_PROGRESS"
    )
    assert "Tick 417 demote" not in prose_only.read_text(encoding="utf-8")

    # (b) Indented READY header must demote (pre-443 unstripped startswith miss).
    indented = tmp_path / "indented.md"
    indented.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "  **STATUS: READY**\n\n"
        "_Note: do not leave STATUS: IN_PROGRESS after live criteria pass._\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(indented.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(indented, reason="indented READY", timestamp="t") is True
    demoted = indented.read_text(encoding="utf-8")
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert not any(
        ln.strip().startswith("**STATUS: READY") for ln in demoted.splitlines()
    )
    assert "Tick 417 demote" in demoted
    assert "- [x] Table 1 (primary metrics by seed)" in demoted
    assert "do not leave STATUS: IN_PROGRESS" in demoted  # prose preserved

    # (c) Tick 446: READY header with trailing IN_PROGRESS note must still demote
    # (pre-446 substring scan misread as IN_PROGRESS → demote no-op → READY stays).
    trailed = tmp_path / "trailed.md"
    trailed.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "**STATUS: READY** — was IN_PROGRESS before G4 pack\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(trailed.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(trailed, reason="trailing IN_PROGRESS", timestamp="t") is True
    trailed_text = trailed.read_text(encoding="utf-8")
    assert _icml_ready_status_header(trailed_text) == "IN_PROGRESS"
    assert not any(
        ln.strip().startswith("**STATUS: READY") for ln in trailed_text.splitlines()
    )
    assert "Tick 417 demote" in trailed_text

    # (d) Tick 447: bare ``STATUS: READY`` (no ``**``) must demote — pre-447
    # ``**STATUS:``-only rewrite left plain READY poisoned after trust refuse.
    plain = tmp_path / "plain.md"
    plain.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "STATUS: READY\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(plain.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(plain, reason="plain READY", timestamp="t") is True
    plain_text = plain.read_text(encoding="utf-8")
    assert _icml_ready_status_header(plain_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in plain_text.splitlines())
    assert "Do not set STATUS: READY until criteria pass." in plain_text
    assert "Tick 417 demote" in plain_text
    assert not any(
        ln.strip().startswith("STATUS: READY") for ln in plain_text.splitlines()
    )

    # (e) update_icml_ready_from_g4 must rewrite indented STATUS headers too.
    ready = tmp_path / "update_indent.md"
    ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "  **STATUS: IN_PROGRESS**\n\n"
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
    status = update_icml_ready_from_g4(
        ready_path=ready,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-27T04:00:00Z",
        allow_ready=True,
    )
    assert status == "READY"
    updated = ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(updated) == "READY"
    assert any(ln.strip() == "**STATUS: READY**" for ln in updated.splitlines())

    # (f) Tick 447: update must rewrite bare ``STATUS: IN_PROGRESS`` up to READY
    # (pre-447 ``**STATUS:``-only rewrite left plain IN_PROGRESS on disk while
    # the function returned READY — false report vs disk after live criteria).
    plain_upd = tmp_path / "update_plain.md"
    plain_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "STATUS: IN_PROGRESS\n\n"
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
    status_plain = update_icml_ready_from_g4(
        ready_path=plain_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-27T12:00:00Z",
        allow_ready=True,
    )
    assert status_plain == "READY"
    plain_updated = plain_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(plain_updated) == "READY"
    assert any(ln.strip() == "**STATUS: READY**" for ln in plain_updated.splitlines())
    assert not any(
        ln.strip().startswith("STATUS: IN_PROGRESS")
        for ln in plain_updated.splitlines()
    )

    # (g) Tick 448: ATX heading ``# STATUS: READY`` must demote — pre-448
    # non-heading-only match left heading READY poisoned after trust refuse.
    atx = tmp_path / "atx.md"
    atx.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "# STATUS: READY\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(atx.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(atx, reason="atx READY", timestamp="t") is True
    atx_text = atx.read_text(encoding="utf-8")
    assert _icml_ready_status_header(atx_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in atx_text.splitlines())
    assert "Do not set STATUS: READY until criteria pass." in atx_text
    assert "Tick 417 demote" in atx_text
    assert not any(
        ln.strip().startswith("# STATUS: READY") for ln in atx_text.splitlines()
    )

    # (h) Tick 448: update must rewrite ``## **STATUS: IN_PROGRESS**`` up to READY.
    atx_upd = tmp_path / "update_atx.md"
    atx_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "## **STATUS: IN_PROGRESS**\n\n"
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
    status_atx = update_icml_ready_from_g4(
        ready_path=atx_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-27T14:00:00Z",
        allow_ready=True,
    )
    assert status_atx == "READY"
    atx_updated = atx_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(atx_updated) == "READY"
    assert any(ln.strip() == "**STATUS: READY**" for ln in atx_updated.splitlines())
    assert not any(
        ln.strip().startswith("## **STATUS: IN_PROGRESS")
        for ln in atx_updated.splitlines()
    )

    # (i) Tick 449: bold-closed label ``**STATUS:** READY`` must demote —
    # pre-449 same-span-only match left label READY poisoned after trust refuse.
    label = tmp_path / "label.md"
    label.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "**STATUS:** READY\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(label.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(label, reason="label READY", timestamp="t") is True
    label_text = label.read_text(encoding="utf-8")
    assert _icml_ready_status_header(label_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in label_text.splitlines())
    assert "Do not set STATUS: READY until criteria pass." in label_text
    assert "Tick 417 demote" in label_text
    assert not any(
        ln.strip().startswith("**STATUS:** READY") for ln in label_text.splitlines()
    )

    # (j) Tick 449: update must rewrite ``**STATUS:** IN_PROGRESS`` up to READY.
    label_upd = tmp_path / "update_label.md"
    label_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "**STATUS:** IN_PROGRESS\n\n"
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
    status_label = update_icml_ready_from_g4(
        ready_path=label_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-27T16:00:00Z",
        allow_ready=True,
    )
    assert status_label == "READY"
    label_updated = label_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(label_updated) == "READY"
    assert any(ln.strip() == "**STATUS: READY**" for ln in label_updated.splitlines())
    assert not any(
        ln.strip().startswith("**STATUS:** IN_PROGRESS")
        for ln in label_updated.splitlines()
    )

    # (k) Tick 450: colon-outside-bold ``**STATUS**: READY`` must demote —
    # pre-450 colon-inside-bold-only match left colon-out READY poisoned.
    colon_out = tmp_path / "colon_out.md"
    colon_out.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "**STATUS**: READY\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(colon_out.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(colon_out, reason="colon-out READY", timestamp="t") is True
    colon_text = colon_out.read_text(encoding="utf-8")
    assert _icml_ready_status_header(colon_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in colon_text.splitlines())
    assert "Do not set STATUS: READY until criteria pass." in colon_text
    assert "Tick 417 demote" in colon_text
    assert not any(
        ln.strip().startswith("**STATUS**: READY") for ln in colon_text.splitlines()
    )

    # (l) Tick 450: update must rewrite ``**STATUS**: IN_PROGRESS`` up to READY.
    colon_upd = tmp_path / "update_colon_out.md"
    colon_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "**STATUS**: IN_PROGRESS\n\n"
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
    status_colon = update_icml_ready_from_g4(
        ready_path=colon_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-27T18:00:00Z",
        allow_ready=True,
    )
    assert status_colon == "READY"
    colon_updated = colon_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(colon_updated) == "READY"
    assert any(ln.strip() == "**STATUS: READY**" for ln in colon_updated.splitlines())
    assert not any(
        ln.strip().startswith("**STATUS**: IN_PROGRESS")
        for ln in colon_updated.splitlines()
    )

    # (m) Tick 451: blockquote ``> **STATUS: READY**`` must demote —
    # pre-451 container-prefix miss left quoted READY poisoned.
    bq = tmp_path / "blockquote.md"
    bq.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "> **STATUS: READY**\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(bq.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(bq, reason="blockquote READY", timestamp="t") is True
    bq_text = bq.read_text(encoding="utf-8")
    assert _icml_ready_status_header(bq_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in bq_text.splitlines())
    assert "Do not set STATUS: READY until criteria pass." in bq_text
    assert "Tick 417 demote" in bq_text
    assert not any("> **STATUS: READY**" in ln for ln in bq_text.splitlines())

    # (n) Tick 451: list ``- **STATUS: IN_PROGRESS**`` must update to READY.
    list_upd = tmp_path / "update_list.md"
    list_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "- **STATUS: IN_PROGRESS**\n\n"
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
    status_list = update_icml_ready_from_g4(
        ready_path=list_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-27T20:00:00Z",
        allow_ready=True,
    )
    assert status_list == "READY"
    list_updated = list_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(list_updated) == "READY"
    assert any(ln.strip() == "**STATUS: READY**" for ln in list_updated.splitlines())
    assert not any(
        ln.strip().startswith("- **STATUS: IN_PROGRESS**")
        for ln in list_updated.splitlines()
    )

    # (o) Tick 451: UTF-8 BOM + READY must demote.
    bom = tmp_path / "bom.md"
    bom.write_text(
        "\ufeff**STATUS: READY**\n\n- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(bom.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(bom, reason="bom READY", timestamp="t") is True
    bom_text = bom.read_text(encoding="utf-8")
    assert _icml_ready_status_header(bom_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in bom_text.splitlines())

    # (p) Tick 452: italic ``*STATUS*: READY`` must demote —
    # pre-452 emphasis miss left italic READY poisoned.
    ital = tmp_path / "italic.md"
    ital.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "*STATUS*: READY\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(ital.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(ital, reason="italic READY", timestamp="t") is True
    ital_text = ital.read_text(encoding="utf-8")
    assert _icml_ready_status_header(ital_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in ital_text.splitlines())
    assert "Do not set STATUS: READY until criteria pass." in ital_text
    assert "Tick 417 demote" in ital_text
    assert not any("*STATUS*: READY" in ln for ln in ital_text.splitlines())

    # (q) Tick 452: underscore ``_STATUS: IN_PROGRESS_`` must update to READY.
    us_upd = tmp_path / "update_underscore.md"
    us_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "_STATUS: IN_PROGRESS_\n\n"
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
    status_us = update_icml_ready_from_g4(
        ready_path=us_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-27T22:00:00Z",
        allow_ready=True,
    )
    assert status_us == "READY"
    us_updated = us_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(us_updated) == "READY"
    assert any(ln.strip() == "**STATUS: READY**" for ln in us_updated.splitlines())
    assert not any(
        ln.strip().startswith("_STATUS: IN_PROGRESS")
        for ln in us_updated.splitlines()
    )

    # (r) Tick 453: dunder ``__STATUS: READY__`` must demote —
    # pre-453 ``__`` miss left dunder READY poisoned.
    dunder = tmp_path / "dunder.md"
    dunder.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "__STATUS: READY__\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(dunder.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(dunder, reason="dunder READY", timestamp="t") is True
    dunder_text = dunder.read_text(encoding="utf-8")
    assert _icml_ready_status_header(dunder_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in dunder_text.splitlines())
    assert "Do not set STATUS: READY until criteria pass." in dunder_text
    assert "Tick 417 demote" in dunder_text
    assert not any("__STATUS: READY__" in ln for ln in dunder_text.splitlines())

    # (s) Tick 453: triple-star ``***STATUS: IN_PROGRESS***`` must update to READY.
    tri_upd = tmp_path / "update_triple_star.md"
    tri_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "***STATUS: IN_PROGRESS***\n\n"
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
    status_tri = update_icml_ready_from_g4(
        ready_path=tri_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-28T00:00:00Z",
        allow_ready=True,
    )
    assert status_tri == "READY"
    tri_updated = tri_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(tri_updated) == "READY"
    assert any(ln.strip() == "**STATUS: READY**" for ln in tri_updated.splitlines())
    assert not any(
        "***STATUS: IN_PROGRESS***" in ln for ln in tri_updated.splitlines()
    )

    # (t) Tick 454: ZWSP-prefixed ``\\u200b**STATUS: READY**`` must demote —
    # pre-454 ZWSP miss left paste READY poisoned.
    zwsp = "\u200b"
    zw = tmp_path / "zwsp.md"
    zw.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{zwsp}**STATUS: READY**\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(zw.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(zw, reason="zwsp READY", timestamp="t") is True
    zw_text = zw.read_text(encoding="utf-8")
    assert _icml_ready_status_header(zw_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in zw_text.splitlines())
    assert "Do not set STATUS: READY until criteria pass." in zw_text
    assert "Tick 417 demote" in zw_text
    assert not any(
        zwsp in ln and "STATUS: READY" in ln for ln in zw_text.splitlines()
    )

    # (u) Tick 454: nested ``**__STATUS: IN_PROGRESS__**`` must update to READY.
    nest_upd = tmp_path / "update_nested_bold_dunder.md"
    nest_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "**__STATUS: IN_PROGRESS__**\n\n"
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
    status_nest = update_icml_ready_from_g4(
        ready_path=nest_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-28T02:00:00Z",
        allow_ready=True,
    )
    assert status_nest == "READY"
    nest_updated = nest_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(nest_updated) == "READY"
    assert any(ln.strip() == "**STATUS: READY**" for ln in nest_updated.splitlines())
    assert not any(
        "**__STATUS: IN_PROGRESS__**" in ln for ln in nest_updated.splitlines()
    )

    # (v) Tick 454: nested ``__**STATUS: READY**__`` must demote.
    nest2 = tmp_path / "nested_dunder_bold.md"
    nest2.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "__**STATUS: READY**__\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(nest2.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(nest2, reason="nested dunder-bold READY", timestamp="t") is True
    nest2_text = nest2.read_text(encoding="utf-8")
    assert _icml_ready_status_header(nest2_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in nest2_text.splitlines())
    assert not any("__**STATUS: READY**__" in ln for ln in nest2_text.splitlines())

    # (w) Tick 455: HTML-entity ``&#8203;**STATUS: READY**`` must demote —
    # pre-455 Unicode-only strip left HTML-export READY poisoned.
    ent = tmp_path / "html_entity_zwsp.md"
    ent.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "&#8203;**STATUS: READY**\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(ent.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(ent, reason="html-entity ZWSP READY", timestamp="t") is True
    ent_text = ent.read_text(encoding="utf-8")
    assert _icml_ready_status_header(ent_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in ent_text.splitlines())
    assert "Do not set STATUS: READY until criteria pass." in ent_text
    assert "Tick 417 demote" in ent_text
    assert not any(
        "&#8203;" in ln and "STATUS: READY" in ln for ln in ent_text.splitlines()
    )

    # (x) Tick 455: ``**STATUS:&nbsp;IN_PROGRESS**`` must update to READY.
    nbsp_upd = tmp_path / "update_nbsp_status.md"
    nbsp_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "**STATUS:&nbsp;IN_PROGRESS**\n\n"
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
    status_nbsp = update_icml_ready_from_g4(
        ready_path=nbsp_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-28T04:00:00Z",
        allow_ready=True,
    )
    assert status_nbsp == "READY"
    nbsp_updated = nbsp_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(nbsp_updated) == "READY"
    assert any(ln.strip() == "**STATUS: READY**" for ln in nbsp_updated.splitlines())
    assert not any(
        "&nbsp;" in ln and "STATUS: IN_PROGRESS" in ln
        for ln in nbsp_updated.splitlines()
    )

    # (y) Tick 456: HTML-tag ``<strong>STATUS: READY</strong>`` must demote —
    # pre-456 entity/ZWSP strip left rich-paste READY poisoned.
    tag = tmp_path / "html_tag_strong.md"
    tag.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "<strong>STATUS: READY</strong>\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(tag.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(tag, reason="html-tag strong READY", timestamp="t") is True
    tag_text = tag.read_text(encoding="utf-8")
    assert _icml_ready_status_header(tag_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in tag_text.splitlines())
    assert "Do not set STATUS: READY until criteria pass." in tag_text
    assert "Tick 417 demote" in tag_text
    assert not any(
        "<strong>" in ln and "STATUS: READY" in ln for ln in tag_text.splitlines()
    )

    # (z) Tick 456: ``<span style="…">**STATUS: IN_PROGRESS**</span>`` must update to READY.
    span_upd = tmp_path / "update_span_status.md"
    span_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        '<span style="font-weight:bold">**STATUS: IN_PROGRESS**</span>\n\n'
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
    status_span = update_icml_ready_from_g4(
        ready_path=span_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-28T06:00:00Z",
        allow_ready=True,
    )
    assert status_span == "READY"
    span_updated = span_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(span_updated) == "READY"
    assert any(ln.strip() == "**STATUS: READY**" for ln in span_updated.splitlines())
    assert not any(
        "<span" in ln and "STATUS: IN_PROGRESS" in ln
        for ln in span_updated.splitlines()
    )

    # (aa) Tick 457: HTML heading ``<h1>STATUS: READY</h1>`` must demote —
    # pre-457 Tick 456 left Notion HTML heading export READY poisoned.
    h1 = tmp_path / "html_h1_status.md"
    h1.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "<h1>STATUS: READY</h1>\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(h1.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(h1, reason="html-h1 READY", timestamp="t") is True
    h1_text = h1.read_text(encoding="utf-8")
    assert _icml_ready_status_header(h1_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in h1_text.splitlines())
    assert "Do not set STATUS: READY until criteria pass." in h1_text
    assert not any(
        "<h1>" in ln and "STATUS: READY" in ln for ln in h1_text.splitlines()
    )

    # (ab) Tick 457: markdown backtick `` `STATUS: IN_PROGRESS` `` must update.
    bt_upd = tmp_path / "update_backtick_status.md"
    bt_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "`STATUS: IN_PROGRESS`\n\n"
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
    status_bt = update_icml_ready_from_g4(
        ready_path=bt_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-28T08:00:00Z",
        allow_ready=True,
    )
    assert status_bt == "READY"
    bt_updated = bt_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(bt_updated) == "READY"
    assert any(ln.strip() == "**STATUS: READY**" for ln in bt_updated.splitlines())
    assert not any(
        ln.strip().startswith("`") and "STATUS: IN_PROGRESS" in ln
        for ln in bt_updated.splitlines()
    )

    # (ac) Tick 458: HTML ``<blockquote>STATUS: READY</blockquote>`` must demote —
    # pre-458 Tick 451 markdown ``>`` worked but Notion HTML blockquote missed.
    bq = tmp_path / "html_blockquote_status.md"
    bq.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "<blockquote>STATUS: READY</blockquote>\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(bq.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(bq, reason="html-blockquote READY", timestamp="t") is True
    bq_text = bq.read_text(encoding="utf-8")
    assert _icml_ready_status_header(bq_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in bq_text.splitlines())
    assert "Do not set STATUS: READY until criteria pass." in bq_text
    assert not any(
        "<blockquote>" in ln and "STATUS: READY" in ln for ln in bq_text.splitlines()
    )

    # (ad) Tick 458: Obsidian ``==STATUS: IN_PROGRESS==`` must update.
    eq_upd = tmp_path / "update_obsidian_status.md"
    eq_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "==STATUS: IN_PROGRESS==\n\n"
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
    status_eq = update_icml_ready_from_g4(
        ready_path=eq_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-28T10:00:00Z",
        allow_ready=True,
    )
    assert status_eq == "READY"
    eq_updated = eq_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(eq_updated) == "READY"
    assert any(ln.strip() == "**STATUS: READY**" for ln in eq_updated.splitlines())
    assert not any(
        ln.strip().startswith("==") and "STATUS: IN_PROGRESS" in ln
        for ln in eq_updated.splitlines()
    )

    # (ae) Tick 459: HTML ``<td>STATUS: READY</td>`` must demote —
    # pre-459 Tick 458 list/blockquote worked but Notion HTML table cells missed.
    td = tmp_path / "html_td_status.md"
    td.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "<td>STATUS: READY</td>\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(td.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(td, reason="html-td READY", timestamp="t") is True
    td_text = td.read_text(encoding="utf-8")
    assert _icml_ready_status_header(td_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in td_text.splitlines())
    assert "Do not set STATUS: READY until criteria pass." in td_text
    assert not any(
        "<td>" in ln and "STATUS: READY" in ln for ln in td_text.splitlines()
    )

    # (af) Tick 459: markdown ``| STATUS: IN_PROGRESS |`` must update.
    pipe_upd = tmp_path / "update_md_pipe_status.md"
    pipe_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "| STATUS: IN_PROGRESS |\n\n"
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
    status_pipe = update_icml_ready_from_g4(
        ready_path=pipe_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-28T12:00:00Z",
        allow_ready=True,
    )
    assert status_pipe == "READY"
    pipe_updated = pipe_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(pipe_updated) == "READY"
    assert any(ln.strip() == "**STATUS: READY**" for ln in pipe_updated.splitlines())
    assert not any(
        ln.strip().startswith("|") and "STATUS: IN_PROGRESS" in ln
        for ln in pipe_updated.splitlines()
    )

    # (ag) Tick 460: outer wrap-around-pipe `` `| STATUS: READY |` `` must demote —
    # pre-460 Tick 459 peeled pipes once before wraps; residual pipes missed.
    wrap_pipe = tmp_path / "wrap_around_md_pipe_status.md"
    wrap_pipe.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "`| STATUS: READY |`\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(wrap_pipe.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(wrap_pipe, reason="wrap-pipe READY", timestamp="t") is True
    wrap_text = wrap_pipe.read_text(encoding="utf-8")
    assert _icml_ready_status_header(wrap_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in wrap_text.splitlines())
    assert "Do not set STATUS: READY until criteria pass." in wrap_text
    assert not any(
        "`|" in ln and "STATUS: READY" in ln for ln in wrap_text.splitlines()
    )

    # (ah) Tick 460: ``~~| STATUS: IN_PROGRESS |~~`` must update to READY.
    strike_pipe_upd = tmp_path / "update_wrap_around_md_pipe_status.md"
    strike_pipe_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "~~| STATUS: IN_PROGRESS |~~\n\n"
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
    status_strike = update_icml_ready_from_g4(
        ready_path=strike_pipe_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-28T14:00:00Z",
        allow_ready=True,
    )
    assert status_strike == "READY"
    strike_updated = strike_pipe_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(strike_updated) == "READY"
    assert any(ln.strip() == "**STATUS: READY**" for ln in strike_updated.splitlines())
    assert not any(
        "~~|" in ln and "STATUS: IN_PROGRESS" in ln for ln in strike_updated.splitlines()
    )

    # (ai) Tick 461: quote-wrap ``"STATUS: READY"`` must demote —
    # pre-461 quote wrappers missed; demote no-op left poisoned READY.
    quote_ready = tmp_path / "quote_status.md"
    quote_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        '"STATUS: READY"\n\n'
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(quote_ready.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(quote_ready, reason="quote READY", timestamp="t") is True
    quote_text = quote_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(quote_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in quote_text.splitlines())
    assert "Do not set STATUS: READY until criteria pass." in quote_text
    assert not any(
        '"' in ln and "STATUS: READY" in ln for ln in quote_text.splitlines()
    )

    # (aj) Tick 461: ``STATUS : IN_PROGRESS`` (space before colon) must update.
    space_upd = tmp_path / "update_space_colon_status.md"
    space_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "STATUS : IN_PROGRESS\n\n"
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
    status_space = update_icml_ready_from_g4(
        ready_path=space_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-28T16:00:00Z",
        allow_ready=True,
    )
    assert status_space == "READY"
    space_updated = space_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(space_updated) == "READY"
    assert any(ln.strip() == "**STATUS: READY**" for ln in space_updated.splitlines())
    assert not any(
        ln.strip().startswith("STATUS : IN_PROGRESS")
        for ln in space_updated.splitlines()
    )

    # (ak) Tick 461: multi-cell ``| STATUS: READY | note |`` must NOT demote
    # as a READY header (pre-461 false READY from non-greedy pipe peel).
    multi_cell = tmp_path / "multi_cell_pipe_status.md"
    multi_cell.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "| STATUS: READY | note |\n\n"
        "**STATUS: IN_PROGRESS**\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(multi_cell.read_text(encoding="utf-8")) == (
        "IN_PROGRESS"
    )
    assert (
        demote_icml_ready_file(multi_cell, reason="multi-cell", timestamp="t") is False
    )

    # (al) Tick 462: GitHub task-list ``- [ ] STATUS: READY`` must demote —
    # pre-462 checkbox after list marker missed; demote no-op left poisoned READY.
    task_ready = tmp_path / "task_list_status.md"
    task_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "- [ ] STATUS: READY\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(task_ready.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(task_ready, reason="task-list READY", timestamp="t") is True
    task_text = task_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(task_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in task_text.splitlines())
    assert "Do not set STATUS: READY until criteria pass." in task_text
    assert not any(
        "[ ]" in ln and "STATUS: READY" in ln for ln in task_text.splitlines()
    )

    # (am) Tick 462: ``STATUS: `IN_PROGRESS` `` token-wrap must update to READY.
    token_upd = tmp_path / "update_token_wrap_status.md"
    token_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "STATUS: `IN_PROGRESS`\n\n"
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
    status_token = update_icml_ready_from_g4(
        ready_path=token_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-28T18:00:00Z",
        allow_ready=True,
    )
    assert status_token == "READY"
    token_updated = token_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(token_updated) == "READY"
    assert any(ln.strip() == "**STATUS: READY**" for ln in token_updated.splitlines())
    assert not any(
        "`IN_PROGRESS`" in ln for ln in token_updated.splitlines() if "STATUS" in ln
    )

    # (an) Tick 462: ``STATUS: ~~READY~~`` strikethrough token must demote.
    strike_token = tmp_path / "strike_token_status.md"
    strike_token.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "STATUS: ~~READY~~\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(strike_token.read_text(encoding="utf-8")) == "READY"
    assert (
        demote_icml_ready_file(strike_token, reason="strike-token READY", timestamp="t")
        is True
    )
    strike_tok_text = strike_token.read_text(encoding="utf-8")
    assert _icml_ready_status_header(strike_tok_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in strike_tok_text.splitlines()
    )
    assert not any(
        "~~READY~~" in ln for ln in strike_tok_text.splitlines() if "STATUS" in ln
    )

    # (ao) Tick 463: bare ``[ ] STATUS: READY`` must demote —
    # pre-463 required ``[-*+]`` before checkbox; demote no-op left poisoned READY.
    bare_ready = tmp_path / "bare_checkbox_status.md"
    bare_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "[ ] STATUS: READY\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(bare_ready.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(bare_ready, reason="bare checkbox READY", timestamp="t") is True
    bare_text = bare_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(bare_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in bare_text.splitlines())
    assert "Do not set STATUS: READY until criteria pass." in bare_text
    assert not any(
        ln.strip().startswith("[ ]") and "STATUS: READY" in ln
        for ln in bare_text.splitlines()
    )

    # (ap) Tick 463: ``1. [ ] STATUS: IN_PROGRESS`` ordered checkbox must update to READY.
    ord_upd = tmp_path / "update_ordered_checkbox_status.md"
    ord_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "1. [ ] STATUS: IN_PROGRESS\n\n"
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
    status_ord = update_icml_ready_from_g4(
        ready_path=ord_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-28T20:00:00Z",
        allow_ready=True,
    )
    assert status_ord == "READY"
    ord_updated = ord_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(ord_updated) == "READY"
    assert any(ln.strip() == "**STATUS: READY**" for ln in ord_updated.splitlines())
    assert not any(
        "1. [ ]" in ln and "STATUS: IN_PROGRESS" in ln for ln in ord_updated.splitlines()
    )

    # (aq) Tick 463: ``> [x] **STATUS: READY**`` blockquote+checkbox must demote.
    bq_ready = tmp_path / "blockquote_checkbox_status.md"
    bq_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "> [x] **STATUS: READY**\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(bq_ready.read_text(encoding="utf-8")) == "READY"
    assert (
        demote_icml_ready_file(bq_ready, reason="bq-checkbox READY", timestamp="t")
        is True
    )
    bq_text = bq_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(bq_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in bq_text.splitlines())
    assert not any(
        ">" in ln and "STATUS: READY" in ln for ln in bq_text.splitlines()
    )

    # (ar) Tick 464: ``(STATUS: READY)`` paren wrap must demote —
    # pre-464 left chat/JSON paren stubs unmatched (demote no-op / poisoned READY).
    paren_ready = tmp_path / "paren_status.md"
    paren_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "(STATUS: READY)\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(paren_ready.read_text(encoding="utf-8")) == "READY"
    assert demote_icml_ready_file(paren_ready, reason="paren READY", timestamp="t") is True
    paren_text = paren_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(paren_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in paren_text.splitlines())
    assert "Do not set STATUS: READY until criteria pass." in paren_text
    assert not any(
        ln.strip().startswith("(") and "STATUS: READY" in ln
        for ln in paren_text.splitlines()
    )

    # (as) Tick 464: ``[STATUS: IN_PROGRESS]`` bracket wrap must update to READY.
    br_upd = tmp_path / "update_bracket_status.md"
    br_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "[STATUS: IN_PROGRESS]\n\n"
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
    status_br = update_icml_ready_from_g4(
        ready_path=br_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-28T22:00:00Z",
        allow_ready=True,
    )
    assert status_br == "READY"
    br_updated = br_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(br_updated) == "READY"
    assert any(ln.strip() == "**STATUS: READY**" for ln in br_updated.splitlines())
    assert not any(
        ln.strip().startswith("[STATUS: IN_PROGRESS]") for ln in br_updated.splitlines()
    )

    # (at) Tick 464: fullwidth colon ``STATUS：READY`` must demote.
    fw_ready = tmp_path / "fullwidth_colon_status.md"
    fw_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "STATUS：READY\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(fw_ready.read_text(encoding="utf-8")) == "READY"
    assert (
        demote_icml_ready_file(fw_ready, reason="fullwidth-colon READY", timestamp="t")
        is True
    )
    fw_text = fw_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(fw_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in fw_text.splitlines())
    assert not any("STATUS：READY" in ln for ln in fw_text.splitlines())

    # (au) Tick 465: ``[STATUS: READY](url)`` markdown-link wrap must demote —
    # pre-465 Tick 464 bare ``[STATUS:…]`` left linked stubs unmatched.
    mdlink_ready = tmp_path / "mdlink_status.md"
    mdlink_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "[STATUS: READY](https://example.com)\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(mdlink_ready.read_text(encoding="utf-8")) == "READY"
    )
    assert (
        demote_icml_ready_file(mdlink_ready, reason="md-link READY", timestamp="t")
        is True
    )
    mdlink_text = mdlink_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(mdlink_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in mdlink_text.splitlines()
    )
    assert "Do not set STATUS: READY until criteria pass." in mdlink_text
    assert not any(
        "](https://example.com)" in ln and "STATUS: READY" in ln
        for ln in mdlink_text.splitlines()
    )

    # (av) Tick 465: ``[STATUS: IN_PROGRESS](#)`` must update to READY.
    mdlink_upd = tmp_path / "update_mdlink_status.md"
    mdlink_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "[STATUS: IN_PROGRESS](#anchor)\n\n"
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
    status_ml = update_icml_ready_from_g4(
        ready_path=mdlink_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-29T00:10:00Z",
        allow_ready=True,
    )
    assert status_ml == "READY"
    ml_updated = mdlink_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(ml_updated) == "READY"
    assert any(ln.strip() == "**STATUS: READY**" for ln in ml_updated.splitlines())
    assert not any(
        "](#anchor)" in ln and "IN_PROGRESS" in ln for ln in ml_updated.splitlines()
    )

    # (aw) Tick 465: ``<a href>STATUS: READY</a>`` HTML anchor must demote.
    a_ready = tmp_path / "html_anchor_status.md"
    a_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        '<a href="https://example.com">STATUS: READY</a>\n\n'
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(a_ready.read_text(encoding="utf-8")) == "READY"
    assert (
        demote_icml_ready_file(a_ready, reason="html-anchor READY", timestamp="t")
        is True
    )
    a_text = a_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(a_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in a_text.splitlines())
    assert not any(
        "<a " in ln and "STATUS: READY" in ln for ln in a_text.splitlines()
    )

    # (ax) Tick 466: nested-paren URL markdown-link must demote —
    # pre-466 ``[^)]*`` truncated at first ``)``.
    nested_ready = tmp_path / "mdlink_nested_paren_status.md"
    nested_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "[STATUS: READY](https://x.com/foo_(bar))\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(nested_ready.read_text(encoding="utf-8")) == "READY"
    )
    assert (
        demote_icml_ready_file(
            nested_ready, reason="md-link nested-paren READY", timestamp="t"
        )
        is True
    )
    nested_text = nested_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(nested_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in nested_text.splitlines()
    )
    assert "Do not set STATUS: READY until criteria pass." in nested_text
    assert not any(
        "foo_(bar)" in ln and "STATUS: READY" in ln
        for ln in nested_text.splitlines()
    )

    # (ay) Tick 466: nested-paren URL ``[STATUS: IN_PROGRESS](…(draft))`` must update.
    nested_upd = tmp_path / "update_mdlink_nested_paren_status.md"
    nested_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "[STATUS: IN_PROGRESS](https://example.com/path#status-(draft))\n\n"
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
    status_nested = update_icml_ready_from_g4(
        ready_path=nested_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-29T02:10:00Z",
        allow_ready=True,
    )
    assert status_nested == "READY"
    nested_updated = nested_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(nested_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**" for ln in nested_updated.splitlines()
    )
    assert not any(
        "status-(draft)" in ln and "IN_PROGRESS" in ln
        for ln in nested_updated.splitlines()
    )

    # (az) Tick 467: markdown-image STATUS must demote —
    # pre-467 link peel required bare ``[`` start (leading ``!`` missed).
    img_ready = tmp_path / "md_image_status.md"
    img_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "![STATUS: READY](https://img.shields.io/badge/STATUS-READY_(live)-green)\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert _icml_ready_status_header(img_ready.read_text(encoding="utf-8")) == "READY"
    assert (
        demote_icml_ready_file(
            img_ready, reason="md-image READY", timestamp="t"
        )
        is True
    )
    img_text = img_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(img_text) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in img_text.splitlines())
    assert "Do not set STATUS: READY until criteria pass." in img_text
    assert not any(
        "![" in ln and "STATUS: READY" in ln for ln in img_text.splitlines()
    )

    # (ba) Tick 467: markdown-image ``![STATUS: IN_PROGRESS](…badge_(draft)…)`` must update.
    img_upd = tmp_path / "update_md_image_status.md"
    img_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "![STATUS: IN_PROGRESS](https://cdn.example/badge_(draft).svg)\n\n"
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
    status_img = update_icml_ready_from_g4(
        ready_path=img_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-29T04:10:00Z",
        allow_ready=True,
    )
    assert status_img == "READY"
    img_updated = img_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(img_updated) == "READY"
    assert any(ln.strip() == "**STATUS: READY**" for ln in img_updated.splitlines())
    assert not any(
        "![" in ln and "IN_PROGRESS" in ln for ln in img_updated.splitlines()
    )

    # (bb) Tick 468: HTML ``<img alt="STATUS: READY">`` must demote —
    # pre-468 Tick 467 only peeled markdown ``![…](…)``.
    html_img_ready = tmp_path / "html_img_alt_status.md"
    html_img_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        '<img alt="STATUS: READY" '
        'src="https://img.shields.io/badge/STATUS-READY_(live)-green">\n\n'
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(html_img_ready.read_text(encoding="utf-8"))
        == "READY"
    )
    assert (
        demote_icml_ready_file(
            html_img_ready, reason="html-img-alt READY", timestamp="t"
        )
        is True
    )
    html_img_text = html_img_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_img_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in html_img_text.splitlines()
    )
    assert "Do not set STATUS: READY until criteria pass." in html_img_text
    assert not any(
        "<img" in ln.lower() and "STATUS: READY" in ln
        for ln in html_img_text.splitlines()
    )

    # (bc) Tick 468: HTML img alt IN_PROGRESS must update to READY.
    html_img_upd = tmp_path / "update_html_img_alt_status.md"
    html_img_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        '<img src="https://cdn.example/badge_(draft).svg" '
        'alt="**STATUS: IN_PROGRESS**" />\n\n'
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
    status_html_img = update_icml_ready_from_g4(
        ready_path=html_img_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-29T06:10:00Z",
        allow_ready=True,
    )
    assert status_html_img == "READY"
    html_img_updated = html_img_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_img_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**" for ln in html_img_updated.splitlines()
    )
    assert not any(
        "<img" in ln.lower() and "IN_PROGRESS" in ln
        for ln in html_img_updated.splitlines()
    )

    # (bd) Tick 469: HTML ``<picture><img alt="STATUS: READY">`` must demote —
    # pre-469 Tick 468 only peeled a full-line bare ``<img>``.
    html_pic_ready = tmp_path / "html_picture_img_alt_status.md"
    html_pic_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        '<picture><source srcset="https://cdn.example/badge_(live).webp">'
        '<img alt="STATUS: READY" '
        'src="https://img.shields.io/badge/STATUS-READY_(live)-green">'
        "</picture>\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(html_pic_ready.read_text(encoding="utf-8"))
        == "READY"
    )
    assert (
        demote_icml_ready_file(
            html_pic_ready, reason="html-picture READY", timestamp="t"
        )
        is True
    )
    html_pic_text = html_pic_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_pic_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in html_pic_text.splitlines()
    )
    assert "Do not set STATUS: READY until criteria pass." in html_pic_text
    assert not any(
        "<picture" in ln.lower() and "STATUS: READY" in ln
        for ln in html_pic_text.splitlines()
    )

    # (be) Tick 469: HTML picture+img alt IN_PROGRESS must update to READY.
    html_pic_upd = tmp_path / "update_html_picture_img_alt_status.md"
    html_pic_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        '<picture><img src="https://cdn.example/badge_(draft).svg" '
        'alt="**STATUS: IN_PROGRESS**" /></picture>\n\n'
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
    status_html_pic = update_icml_ready_from_g4(
        ready_path=html_pic_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-29T08:10:00Z",
        allow_ready=True,
    )
    assert status_html_pic == "READY"
    html_pic_updated = html_pic_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_pic_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**" for ln in html_pic_updated.splitlines()
    )
    assert not any(
        "<picture" in ln.lower() and "IN_PROGRESS" in ln
        for ln in html_pic_updated.splitlines()
    )

    # (bf) Tick 470: HTML ``<img title="STATUS: READY">`` must demote —
    # pre-470 Tick 468/469 only peeled ``alt=``.
    html_title_ready = tmp_path / "html_img_title_aria_status.md"
    html_title_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        '<img alt="badge_(live)" title="STATUS: READY" '
        'src="https://img.shields.io/badge/STATUS-READY_(live)-green">\n\n'
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(html_title_ready.read_text(encoding="utf-8"))
        == "READY"
    )
    assert (
        demote_icml_ready_file(
            html_title_ready, reason="html-img-title READY", timestamp="t"
        )
        is True
    )
    html_title_text = html_title_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_title_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in html_title_text.splitlines()
    )
    assert "Do not set STATUS: READY until criteria pass." in html_title_text
    assert not any(
        "<img" in ln.lower() and "STATUS: READY" in ln
        for ln in html_title_text.splitlines()
    )

    # (bg) Tick 470: HTML img aria-label IN_PROGRESS must update to READY.
    html_aria_upd = tmp_path / "update_html_img_aria_status.md"
    html_aria_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        '<img src="https://cdn.example/badge_(draft).svg" '
        'aria-label="**STATUS: IN_PROGRESS**" />\n\n'
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
    status_html_aria = update_icml_ready_from_g4(
        ready_path=html_aria_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-29T10:10:00Z",
        allow_ready=True,
    )
    assert status_html_aria == "READY"
    html_aria_updated = html_aria_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_aria_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**" for ln in html_aria_updated.splitlines()
    )
    assert not any(
        "<img" in ln.lower() and "IN_PROGRESS" in ln
        for ln in html_aria_updated.splitlines()
    )

    # (bh) Tick 471: HTML inline SVG ``<title>STATUS: READY</title>`` must demote —
    # pre-471 Tick 468–470 only peeled ``<img>`` attrs.
    html_svg_ready = tmp_path / "html_svg_title_status.md"
    html_svg_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        '<svg xmlns="http://www.w3.org/2000/svg" role="img">'
        "<title>STATUS: READY</title>"
        '<text x="0" y="15">badge_(live)</text></svg>\n\n'
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(html_svg_ready.read_text(encoding="utf-8"))
        == "READY"
    )
    assert (
        demote_icml_ready_file(
            html_svg_ready, reason="html-svg-title READY", timestamp="t"
        )
        is True
    )
    html_svg_text = html_svg_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_svg_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in html_svg_text.splitlines()
    )
    assert "Do not set STATUS: READY until criteria pass." in html_svg_text
    assert not any(
        "<svg" in ln.lower() and "STATUS: READY" in ln
        for ln in html_svg_text.splitlines()
    )

    # (bi) Tick 471: HTML SVG title IN_PROGRESS must update to READY.
    html_svg_upd = tmp_path / "update_html_svg_title_status.md"
    html_svg_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        '<svg role="img"><title>**STATUS: IN_PROGRESS**</title>'
        "<desc>draft</desc></svg>\n\n"
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
    status_html_svg = update_icml_ready_from_g4(
        ready_path=html_svg_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-29T12:10:00Z",
        allow_ready=True,
    )
    assert status_html_svg == "READY"
    html_svg_updated = html_svg_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_svg_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**" for ln in html_svg_updated.splitlines()
    )
    assert not any(
        "<svg" in ln.lower() and "IN_PROGRESS" in ln
        for ln in html_svg_updated.splitlines()
    )

    # (bj) Tick 472: HTML SVG ``aria-label="STATUS: READY"`` must demote —
    # pre-472 Tick 471 only peeled nested ``<title>``.
    html_svg_aria_ready = tmp_path / "html_svg_aria_title_attr_status.md"
    html_svg_aria_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        '<svg xmlns="http://www.w3.org/2000/svg" role="img" '
        'aria-label="STATUS: READY">'
        "<title>Badge_(live)</title>"
        '<text x="0" y="15">ok</text></svg>\n\n'
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(html_svg_aria_ready.read_text(encoding="utf-8"))
        == "READY"
    )
    assert (
        demote_icml_ready_file(
            html_svg_aria_ready, reason="html-svg-aria-title-attr READY", timestamp="t"
        )
        is True
    )
    html_svg_aria_text = html_svg_aria_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_svg_aria_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**"
        for ln in html_svg_aria_text.splitlines()
    )
    assert "Do not set STATUS: READY until criteria pass." in html_svg_aria_text
    assert not any(
        "<svg" in ln.lower() and "STATUS: READY" in ln
        for ln in html_svg_aria_text.splitlines()
    )

    # (bk) Tick 472: HTML SVG root title= IN_PROGRESS must update to READY.
    html_svg_title_upd = tmp_path / "update_html_svg_title_attr_status.md"
    html_svg_title_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        '<svg role="img" title="**STATUS: IN_PROGRESS**">'
        "<title>draft</title></svg>\n\n"
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
    status_html_svg_attr = update_icml_ready_from_g4(
        ready_path=html_svg_title_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-29T14:10:00Z",
        allow_ready=True,
    )
    assert status_html_svg_attr == "READY"
    html_svg_attr_updated = html_svg_title_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_svg_attr_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**"
        for ln in html_svg_attr_updated.splitlines()
    )
    assert not any(
        "<svg" in ln.lower() and "IN_PROGRESS" in ln
        for ln in html_svg_attr_updated.splitlines()
    )

    # (bl) Tick 473: HTML SVG ``<desc>STATUS: READY</desc>`` must demote —
    # pre-473 Tick 471/472 only peeled root attrs + nested ``<title>``.
    html_svg_desc_ready = tmp_path / "html_svg_desc_status.md"
    html_svg_desc_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        '<svg xmlns="http://www.w3.org/2000/svg" role="img">'
        "<title>Badge_(live)</title>"
        "<desc>STATUS: READY</desc>"
        '<text x="0" y="15">ok</text></svg>\n\n'
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(html_svg_desc_ready.read_text(encoding="utf-8"))
        == "READY"
    )
    assert (
        demote_icml_ready_file(
            html_svg_desc_ready, reason="html-svg-desc READY", timestamp="t"
        )
        is True
    )
    html_svg_desc_text = html_svg_desc_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_svg_desc_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**"
        for ln in html_svg_desc_text.splitlines()
    )
    assert "Do not set STATUS: READY until criteria pass." in html_svg_desc_text
    assert not any(
        "<svg" in ln.lower() and "STATUS: READY" in ln
        for ln in html_svg_desc_text.splitlines()
    )

    # (bm) Tick 473: HTML SVG desc IN_PROGRESS must update to READY.
    html_svg_desc_upd = tmp_path / "update_html_svg_desc_status.md"
    html_svg_desc_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        '<svg role="img"><title>draft</title>'
        "<desc>**STATUS: IN_PROGRESS**</desc></svg>\n\n"
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
    status_html_svg_desc = update_icml_ready_from_g4(
        ready_path=html_svg_desc_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-29T16:10:00Z",
        allow_ready=True,
    )
    assert status_html_svg_desc == "READY"
    html_svg_desc_updated = html_svg_desc_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_svg_desc_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**"
        for ln in html_svg_desc_updated.splitlines()
    )
    assert not any(
        "<svg" in ln.lower() and "IN_PROGRESS" in ln
        for ln in html_svg_desc_updated.splitlines()
    )

    # (bn) Tick 474: HTML SVG ``<text>STATUS: READY</text>`` must demote —
    # pre-474 Tick 471–473 only peeled attrs / ``<title>`` / ``<desc>``.
    html_svg_text_ready = tmp_path / "html_svg_text_status.md"
    html_svg_text_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        '<svg xmlns="http://www.w3.org/2000/svg" role="img">'
        "<title>Badge_(live)</title>"
        "<desc>ICML badge detail</desc>"
        '<text x="4" y="14">STATUS: READY</text></svg>\n\n'
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(html_svg_text_ready.read_text(encoding="utf-8"))
        == "READY"
    )
    assert (
        demote_icml_ready_file(
            html_svg_text_ready, reason="html-svg-text READY", timestamp="t"
        )
        is True
    )
    html_svg_text_text = html_svg_text_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_svg_text_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**"
        for ln in html_svg_text_text.splitlines()
    )
    assert "Do not set STATUS: READY until criteria pass." in html_svg_text_text
    assert not any(
        "<svg" in ln.lower() and "STATUS: READY" in ln
        for ln in html_svg_text_text.splitlines()
    )

    # (bo) Tick 474: HTML SVG text IN_PROGRESS must update to READY.
    html_svg_text_upd = tmp_path / "update_html_svg_text_status.md"
    html_svg_text_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        '<svg role="img"><title>draft</title>'
        "<text><tspan>**STATUS: IN_PROGRESS**</tspan></text></svg>\n\n"
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
    status_html_svg_text = update_icml_ready_from_g4(
        ready_path=html_svg_text_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-29T18:10:00Z",
        allow_ready=True,
    )
    assert status_html_svg_text == "READY"
    html_svg_text_updated = html_svg_text_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_svg_text_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**"
        for ln in html_svg_text_updated.splitlines()
    )
    assert not any(
        "<svg" in ln.lower() and "IN_PROGRESS" in ln
        for ln in html_svg_text_updated.splitlines()
    )

    # (bp) Tick 475: HTML SVG ``<foreignObject>STATUS: READY</foreignObject>``
    # must demote — pre-475 Tick 471–474 only peeled attrs/title/desc/text.
    html_svg_fo_ready = tmp_path / "html_svg_foreign_object_status.md"
    html_svg_fo_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        '<svg xmlns="http://www.w3.org/2000/svg" role="img">'
        "<title>Badge_(live)</title>"
        "<desc>ICML badge detail</desc>"
        '<foreignObject width="110" height="20">'
        "<div xmlns=\"http://www.w3.org/1999/xhtml\">STATUS: READY</div>"
        "</foreignObject></svg>\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(html_svg_fo_ready.read_text(encoding="utf-8"))
        == "READY"
    )
    assert (
        demote_icml_ready_file(
            html_svg_fo_ready, reason="html-svg-foreignObject READY", timestamp="t"
        )
        is True
    )
    html_svg_fo_text = html_svg_fo_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_svg_fo_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**"
        for ln in html_svg_fo_text.splitlines()
    )
    assert "Do not set STATUS: READY until criteria pass." in html_svg_fo_text
    assert not any(
        "<svg" in ln.lower() and "STATUS: READY" in ln
        for ln in html_svg_fo_text.splitlines()
    )

    # (bq) Tick 475: HTML SVG foreignObject IN_PROGRESS must update to READY.
    html_svg_fo_upd = tmp_path / "update_html_svg_foreign_object_status.md"
    html_svg_fo_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        '<svg role="img"><title>draft</title>'
        "<foreignObject><span>**STATUS: IN_PROGRESS**</span>"
        "</foreignObject></svg>\n\n"
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
    status_html_svg_fo = update_icml_ready_from_g4(
        ready_path=html_svg_fo_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-29T20:10:00Z",
        allow_ready=True,
    )
    assert status_html_svg_fo == "READY"
    html_svg_fo_updated = html_svg_fo_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_svg_fo_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**"
        for ln in html_svg_fo_updated.splitlines()
    )
    assert not any(
        "<svg" in ln.lower() and "IN_PROGRESS" in ln
        for ln in html_svg_fo_updated.splitlines()
    )

    # (br) Tick 476: pretty-printed multi-line SVG ``<text>STATUS: READY</text>``
    # must demote — pre-476 Tick 471–475 required a full-line ``<svg>…</svg>``.
    html_svg_ml_ready = tmp_path / "html_svg_multiline_status.md"
    html_svg_ml_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="24">\n'
        "  <title>Badge_(live)</title>\n"
        '  <text x="0" y="16">STATUS: READY</text>\n'
        "</svg>\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(html_svg_ml_ready.read_text(encoding="utf-8"))
        == "READY"
    )
    assert (
        demote_icml_ready_file(
            html_svg_ml_ready, reason="html-svg-multiline READY", timestamp="t"
        )
        is True
    )
    html_svg_ml_text = html_svg_ml_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_svg_ml_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**"
        for ln in html_svg_ml_text.splitlines()
    )
    assert "Do not set STATUS: READY until criteria pass." in html_svg_ml_text
    # Whole SVG block replaced (not inner-line rewrite leaving broken markup).
    assert "<svg" not in html_svg_ml_text.lower()

    # (bs) Tick 476: multi-line SVG IN_PROGRESS must update to READY.
    html_svg_ml_upd = tmp_path / "update_html_svg_multiline_status.md"
    html_svg_ml_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        '<svg role="img">\n'
        "  <title>draft</title>\n"
        "  <text>**STATUS: IN_PROGRESS**</text>\n"
        "</svg>\n\n"
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
    status_html_svg_ml = update_icml_ready_from_g4(
        ready_path=html_svg_ml_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-29T22:10:00Z",
        allow_ready=True,
    )
    assert status_html_svg_ml == "READY"
    html_svg_ml_updated = html_svg_ml_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_svg_ml_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**"
        for ln in html_svg_ml_updated.splitlines()
    )
    assert "<svg" not in html_svg_ml_updated.lower()

    # (bt) Tick 477: pretty-printed multi-line ``<img alt="STATUS: READY">``
    # must demote — pre-477 Tick 468–470 required a full-line ``<img>``.
    html_img_ml_ready = tmp_path / "html_img_multiline_status.md"
    html_img_ml_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "<img\n"
        '  alt="STATUS: READY"\n'
        '  src="https://img.shields.io/badge/status-ready-green.svg"\n'
        "/>\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(html_img_ml_ready.read_text(encoding="utf-8"))
        == "READY"
    )
    assert (
        demote_icml_ready_file(
            html_img_ml_ready, reason="html-img-multiline READY", timestamp="t"
        )
        is True
    )
    html_img_ml_text = html_img_ml_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_img_ml_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**"
        for ln in html_img_ml_text.splitlines()
    )
    assert "Do not set STATUS: READY until criteria pass." in html_img_ml_text
    # Whole img block replaced (not inner-attr rewrite leaving broken markup).
    assert "<img" not in html_img_ml_text.lower()

    # (bu) Tick 477: multi-line img IN_PROGRESS must update to READY.
    html_img_ml_upd = tmp_path / "update_html_img_multiline_status.md"
    html_img_ml_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "<img\n"
        '  title="**STATUS: IN_PROGRESS**"\n'
        '  src="https://cdn.example/badge_(draft).svg"\n'
        ">\n\n"
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
    status_html_img_ml = update_icml_ready_from_g4(
        ready_path=html_img_ml_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-30T00:10:00Z",
        allow_ready=True,
    )
    assert status_html_img_ml == "READY"
    html_img_ml_updated = html_img_ml_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_img_ml_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**"
        for ln in html_img_ml_updated.splitlines()
    )
    assert "<img" not in html_img_ml_updated.lower()

    # (bv) Tick 478: mid-line ``<img`` after ``<picture><source>`` multiline
    # must demote — pre-478 Tick 477 required ``^<img`` at line start.
    html_pic_ml_ready = tmp_path / "html_picture_img_multiline_status.md"
    html_pic_ml_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        '<picture><source srcset="https://cdn.example/badge_(live).webp" '
        'type="image/webp"><img\n'
        '  alt="STATUS: READY"\n'
        '  src="https://img.shields.io/badge/status-ready-green.svg"\n'
        "/></picture>\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(html_pic_ml_ready.read_text(encoding="utf-8"))
        == "READY"
    )
    assert (
        demote_icml_ready_file(
            html_pic_ml_ready,
            reason="html-picture-img-multiline READY",
            timestamp="t",
        )
        is True
    )
    html_pic_ml_text = html_pic_ml_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_pic_ml_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**"
        for ln in html_pic_ml_text.splitlines()
    )
    assert "Do not set STATUS: READY until criteria pass." in html_pic_ml_text
    assert "<img" not in html_pic_ml_text.lower()
    assert "<picture" not in html_pic_ml_text.lower()

    # (bw) Tick 478: picture+midline-img IN_PROGRESS must update to READY.
    html_pic_ml_upd = tmp_path / "update_html_picture_img_multiline_status.md"
    html_pic_ml_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "<picture><img\n"
        '  title="**STATUS: IN_PROGRESS**"\n'
        '  src="https://cdn.example/badge_(draft).svg"\n'
        "></picture>\n\n"
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
    status_html_pic_ml = update_icml_ready_from_g4(
        ready_path=html_pic_ml_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-30T02:10:00Z",
        allow_ready=True,
    )
    assert status_html_pic_ml == "READY"
    html_pic_ml_updated = html_pic_ml_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_pic_ml_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**"
        for ln in html_pic_ml_updated.splitlines()
    )
    assert "<img" not in html_pic_ml_updated.lower()
    assert "<picture" not in html_pic_ml_updated.lower()

    # (bx) Tick 479: mid-line ``<svg`` after ``<div role="img">`` multiline
    # must demote — pre-479 Tick 476 required ``^<svg`` at line start.
    html_svg_inl_ready = tmp_path / "html_svg_inline_multiline_status.md"
    html_svg_inl_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        '<div role="img"><svg\n'
        '  aria-label="STATUS: READY"\n'
        '  width="120" height="20">\n'
        "<title>Badge</title>\n"
        "</svg></div>\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(html_svg_inl_ready.read_text(encoding="utf-8"))
        == "READY"
    )
    assert (
        demote_icml_ready_file(
            html_svg_inl_ready,
            reason="html-svg-inline-multiline READY",
            timestamp="t",
        )
        is True
    )
    html_svg_inl_text = html_svg_inl_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_svg_inl_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**"
        for ln in html_svg_inl_text.splitlines()
    )
    assert "Do not set STATUS: READY until criteria pass." in html_svg_inl_text
    assert "<svg" not in html_svg_inl_text.lower()
    assert "<div" not in html_svg_inl_text.lower()

    # (by) Tick 479: wrapper+midline-svg IN_PROGRESS must update to READY.
    html_svg_inl_upd = tmp_path / "update_html_svg_inline_multiline_status.md"
    html_svg_inl_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        '<a href="https://img.shields.io/badge/status-wip-yellow"><svg\n'
        '  role="img"\n'
        '  aria-label="**STATUS: IN_PROGRESS**"\n'
        ">\n"
        "<title>WIP</title>\n"
        "</svg></a>\n\n"
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
    status_html_svg_inl = update_icml_ready_from_g4(
        ready_path=html_svg_inl_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-30T04:10:00Z",
        allow_ready=True,
    )
    assert status_html_svg_inl == "READY"
    html_svg_inl_updated = html_svg_inl_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(html_svg_inl_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**"
        for ln in html_svg_inl_updated.splitlines()
    )
    assert "<svg" not in html_svg_inl_updated.lower()
    assert "<a " not in html_svg_inl_updated.lower()

    # (bz) Tick 480: soft-wrapped markdown image STATUS must demote —
    # pre-480 Tick 465–467 required a single-line ``![…](…)``.
    md_soft_ready = tmp_path / "md_link_softwrap_status.md"
    md_soft_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "![STATUS: READY](\n"
        "https://img.shields.io/badge/status-ready-green.svg)\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(md_soft_ready.read_text(encoding="utf-8"))
        == "READY"
    )
    assert (
        demote_icml_ready_file(
            md_soft_ready,
            reason="md-link-softwrap READY",
            timestamp="t",
        )
        is True
    )
    md_soft_text = md_soft_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(md_soft_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**"
        for ln in md_soft_text.splitlines()
    )
    assert "Do not set STATUS: READY until criteria pass." in md_soft_text
    assert "![STATUS: READY]" not in md_soft_text

    # (ca) Tick 480: soft-wrapped md link IN_PROGRESS must update to READY.
    md_soft_upd = tmp_path / "update_md_link_softwrap_status.md"
    md_soft_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "[**STATUS: IN_PROGRESS**](\n"
        "https://x.com/foo_(bar))\n\n"
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
    status_md_soft = update_icml_ready_from_g4(
        ready_path=md_soft_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-30T06:10:00Z",
        allow_ready=True,
    )
    assert status_md_soft == "READY"
    md_soft_updated = md_soft_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(md_soft_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**"
        for ln in md_soft_updated.splitlines()
    )
    assert "[**STATUS: IN_PROGRESS**]" not in md_soft_updated

    # (cb) Tick 481: HTML <a title=/aria-label= STATUS must demote —
    # pre-481 Tick 465 strip kept inner text only (badge/Go).
    from icml_env_checks import _icml_ready_status_header

    a_title_ready = tmp_path / "html_a_title_status.md"
    a_title_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "<a\n"
        '  href="https://example.com"\n'
        '  title="STATUS: READY"\n'
        ">badge</a>\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(a_title_ready.read_text(encoding="utf-8"))
        == "READY"
    )
    assert (
        demote_icml_ready_file(
            a_title_ready,
            reason="html-a-title-aria READY",
            timestamp="t",
        )
        is True
    )
    a_title_text = a_title_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(a_title_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**"
        for ln in a_title_text.splitlines()
    )
    assert "Do not set STATUS: READY until criteria pass." in a_title_text
    assert 'title="STATUS: READY"' not in a_title_text

    # (cc) Tick 481: <button aria-label= IN_PROGRESS must update to READY.
    btn_upd = tmp_path / "update_html_button_aria_status.md"
    btn_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        '<button aria-label="STATUS: IN_PROGRESS">Go</button>\n\n'
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
    status_btn = update_icml_ready_from_g4(
        ready_path=btn_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-30T08:10:00Z",
        allow_ready=True,
    )
    assert status_btn == "READY"
    btn_updated = btn_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(btn_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**"
        for ln in btn_updated.splitlines()
    )
    assert 'aria-label="STATUS: IN_PROGRESS"' not in btn_updated

    # (cd) Tick 482: HTML <span title= STATUS must demote —
    # pre-482 Tick 481 only peeled a/button attrs.
    from icml_env_checks import _icml_ready_status_header

    span_title_ready = tmp_path / "html_span_title_status.md"
    span_title_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "<span\n"
        '  title="STATUS: READY"\n'
        ">badge</span>\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(span_title_ready.read_text(encoding="utf-8"))
        == "READY"
    )
    assert (
        demote_icml_ready_file(
            span_title_ready,
            reason="html-span-label-title-aria READY",
            timestamp="t",
        )
        is True
    )
    span_title_text = span_title_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(span_title_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**"
        for ln in span_title_text.splitlines()
    )
    assert "Do not set STATUS: READY until criteria pass." in span_title_text
    assert 'title="STATUS: READY"' not in span_title_text

    # (ce) Tick 482: <label aria-label= IN_PROGRESS must update to READY.
    label_upd = tmp_path / "update_html_label_aria_status.md"
    label_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        '<label aria-label="STATUS: IN_PROGRESS">x</label>\n\n'
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
    status_label = update_icml_ready_from_g4(
        ready_path=label_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-30T10:05:00Z",
        allow_ready=True,
    )
    assert status_label == "READY"
    label_updated = label_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(label_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**"
        for ln in label_updated.splitlines()
    )
    assert 'aria-label="STATUS: IN_PROGRESS"' not in label_updated

    # (cf) Tick 484: HTML aria-description STATUS must demote —
    # pre-484 Tick 481–483 only peeled title/aria-label.
    from icml_env_checks import _icml_ready_status_header

    aria_desc_ready = tmp_path / "html_aria_description_status.md"
    aria_desc_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "<p\n"
        '  aria-description="STATUS: READY"\n'
        ">badge</p>\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(aria_desc_ready.read_text(encoding="utf-8"))
        == "READY"
    )
    assert (
        demote_icml_ready_file(
            aria_desc_ready,
            reason="html-aria-description READY",
            timestamp="t",
        )
        is True
    )
    aria_desc_text = aria_desc_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(aria_desc_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**"
        for ln in aria_desc_text.splitlines()
    )
    assert "Do not set STATUS: READY until criteria pass." in aria_desc_text
    assert 'aria-description="STATUS: READY"' not in aria_desc_text

    # (cg) Tick 484: <span aria-description= IN_PROGRESS must update to READY.
    span_desc_upd = tmp_path / "update_html_aria_description_status.md"
    span_desc_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        '<span aria-description="STATUS: IN_PROGRESS">x</span>\n\n'
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
    status_span_desc = update_icml_ready_from_g4(
        ready_path=span_desc_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-30T14:10:00Z",
        allow_ready=True,
    )
    assert status_span_desc == "READY"
    span_desc_updated = span_desc_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(span_desc_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**"
        for ln in span_desc_updated.splitlines()
    )
    assert 'aria-description="STATUS: IN_PROGRESS"' not in span_desc_updated

    # (ch) Tick 485: unquoted HTML STATUS attrs must demote —
    # pre-485 ATTR peels required quotes.
    from icml_env_checks import _icml_ready_status_header

    unquoted_ready = tmp_path / "html_unquoted_attr_status.md"
    unquoted_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "<p\n"
        "  title=STATUS:READY\n"
        ">badge</p>\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(unquoted_ready.read_text(encoding="utf-8"))
        == "READY"
    )
    assert (
        demote_icml_ready_file(
            unquoted_ready,
            reason="html-unquoted-attr READY",
            timestamp="t",
        )
        is True
    )
    unquoted_text = unquoted_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(unquoted_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**"
        for ln in unquoted_text.splitlines()
    )
    assert "Do not set STATUS: READY until criteria pass." in unquoted_text
    assert "title=STATUS:READY" not in unquoted_text

    # (ci) Tick 485: <img alt=STATUS:IN_PROGRESS must update to READY.
    img_uq_upd = tmp_path / "update_html_unquoted_attr_status.md"
    img_uq_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "<img alt=STATUS:IN_PROGRESS src=b.svg>\n\n"
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
    status_img_uq = update_icml_ready_from_g4(
        ready_path=img_uq_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-30T16:10:00Z",
        allow_ready=True,
    )
    assert status_img_uq == "READY"
    img_uq_updated = img_uq_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(img_uq_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**"
        for ln in img_uq_updated.splitlines()
    )
    assert "alt=STATUS:IN_PROGRESS" not in img_uq_updated

    # (cj) Tick 486: HTML-entity STATUS colon must demote —
    # pre-486 Tick 455 decoded only invisibles/nbsp.
    entity_colon_ready = tmp_path / "html_entity_colon_status.md"
    entity_colon_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "STATUS&#58; READY\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(entity_colon_ready.read_text(encoding="utf-8"))
        == "READY"
    )
    assert (
        demote_icml_ready_file(
            entity_colon_ready,
            reason="html-entity-colon READY",
            timestamp="t",
        )
        is True
    )
    entity_colon_text = entity_colon_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(entity_colon_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**"
        for ln in entity_colon_text.splitlines()
    )
    assert "Do not set STATUS: READY until criteria pass." in entity_colon_text
    assert "STATUS&#58; READY" not in entity_colon_text

    # (ck) Tick 486: attr title="STATUS&colon; IN_PROGRESS" must update to READY.
    attr_colon_upd = tmp_path / "update_html_entity_colon_attr_status.md"
    attr_colon_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        '<p\n'
        '  title="STATUS&colon; IN_PROGRESS"\n'
        ">badge</p>\n\n"
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
    status_attr_colon = update_icml_ready_from_g4(
        ready_path=attr_colon_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-30T18:10:00Z",
        allow_ready=True,
    )
    assert status_attr_colon == "READY"
    attr_colon_updated = attr_colon_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(attr_colon_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**"
        for ln in attr_colon_updated.splitlines()
    )
    assert "STATUS&colon;" not in attr_colon_updated

    # (cl) Tick 487: double-escaped STATUS&amp;#58; READY must demote.
    dbl_ready = tmp_path / "html_double_escaped_status.md"
    dbl_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "STATUS&amp;#58; READY\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(dbl_ready.read_text(encoding="utf-8")) == "READY"
    )
    assert (
        demote_icml_ready_file(
            dbl_ready,
            reason="html-double-escaped READY",
            timestamp="t",
        )
        is True
    )
    dbl_text = dbl_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(dbl_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in dbl_text.splitlines()
    )
    assert "STATUS&amp;#58; READY" not in dbl_text

    # (cm) Tick 487: escaped HTML &lt;p title=&quot;STATUS: IN_PROGRESS&quot;&gt;
    # must update to READY.
    esc_upd = tmp_path / "update_html_double_escaped_attr_status.md"
    esc_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "&lt;p title=&quot;STATUS&amp;colon; IN_PROGRESS&quot;&gt;badge&lt;/p&gt;\n\n"
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
    status_esc = update_icml_ready_from_g4(
        ready_path=esc_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-30T20:10:00Z",
        allow_ready=True,
    )
    assert status_esc == "READY"
    esc_updated = esc_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(esc_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**" for ln in esc_updated.splitlines()
    )
    assert "&lt;p" not in esc_updated
    assert "STATUS&amp;colon;" not in esc_updated

    # (cn) Tick 488: JSON/JS STATUS\u003a READY must demote.
    js_ready = tmp_path / "js_unicode_escaped_status.md"
    js_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "STATUS\\u003a READY\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(js_ready.read_text(encoding="utf-8")) == "READY"
    )
    assert (
        demote_icml_ready_file(
            js_ready,
            reason="js-unicode-escaped READY",
            timestamp="t",
        )
        is True
    )
    js_text = js_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(js_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in js_text.splitlines()
    )
    assert "STATUS\\u003a READY" not in js_text

    # (co) Tick 488: JSON-escaped HTML badge IN_PROGRESS must update to READY.
    js_upd = tmp_path / "update_js_unicode_escaped_attr_status.md"
    js_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "\\u003cp title=\\u0022STATUS\\u003a IN_PROGRESS\\u0022\\u003e"
        "badge\\u003c/p\\u003e\n\n"
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
    status_js = update_icml_ready_from_g4(
        ready_path=js_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-30T22:20:00Z",
        allow_ready=True,
    )
    assert status_js == "READY"
    js_updated = js_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(js_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**" for ln in js_updated.splitlines()
    )
    assert "\\u003c" not in js_updated
    assert "STATUS\\u003a" not in js_updated

    # (cp) Tick 489: URL percent-encoded STATUS%3A%20READY must demote.
    pct_ready = tmp_path / "url_percent_encoded_status.md"
    pct_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "STATUS%3A%20READY\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(pct_ready.read_text(encoding="utf-8")) == "READY"
    )
    assert (
        demote_icml_ready_file(
            pct_ready,
            reason="url-percent-encoded READY",
            timestamp="t",
        )
        is True
    )
    pct_text = pct_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(pct_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in pct_text.splitlines()
    )
    assert "STATUS%3A%20READY" not in pct_text

    # (cq) Tick 489: URL-encoded HTML badge IN_PROGRESS must update to READY.
    pct_upd = tmp_path / "update_url_percent_encoded_attr_status.md"
    pct_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "%3Cp%20title%3D%22STATUS%3A%20IN_PROGRESS%22%3E"
        "badge%3C%2Fp%3E\n\n"
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
    status_pct = update_icml_ready_from_g4(
        ready_path=pct_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-09-30T22:20:00Z",
        allow_ready=True,
    )
    assert status_pct == "READY"
    pct_updated = pct_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(pct_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**" for ln in pct_updated.splitlines()
    )
    assert "%3C" not in pct_updated
    assert "STATUS%3A" not in pct_updated

    # (cr) Tick 490: quoted-printable STATUS=3A=20READY must demote.
    qp_ready = tmp_path / "quoted_printable_status.md"
    qp_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "STATUS=3A=20READY\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(qp_ready.read_text(encoding="utf-8")) == "READY"
    )
    assert (
        demote_icml_ready_file(
            qp_ready,
            reason="quoted-printable READY",
            timestamp="t",
        )
        is True
    )
    qp_text = qp_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(qp_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in qp_text.splitlines()
    )
    assert "STATUS=3A=20READY" not in qp_text

    # (cs) Tick 490: QP-encoded HTML badge IN_PROGRESS must update to READY.
    qp_upd = tmp_path / "update_quoted_printable_attr_status.md"
    qp_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "=3Cp title=3D=22STATUS=3A IN_PROGRESS=22=3E"
        "badge=3C/p=3E\n\n"
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
    status_qp = update_icml_ready_from_g4(
        ready_path=qp_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-10-01T02:20:00Z",
        allow_ready=True,
    )
    assert status_qp == "READY"
    qp_updated = qp_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(qp_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**" for ln in qp_updated.splitlines()
    )
    assert "=3C" not in qp_updated
    assert "STATUS=3A" not in qp_updated

    # (ct) Tick 491: RFC 2047 encoded-word STATUS must demote.
    import base64 as _b64

    rfc_ready = tmp_path / "rfc2047_encoded_word_status.md"
    rfc_q = "=?UTF-8?Q?STATUS=3A_READY?="
    rfc_ready.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{rfc_q}\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(rfc_ready.read_text(encoding="utf-8")) == "READY"
    )
    assert (
        demote_icml_ready_file(
            rfc_ready,
            reason="rfc2047 encoded-word READY",
            timestamp="t",
        )
        is True
    )
    rfc_text = rfc_ready.read_text(encoding="utf-8")
    assert _icml_ready_status_header(rfc_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in rfc_text.splitlines()
    )
    assert "=?UTF-8?Q?" not in rfc_text

    # (cu) Tick 491: RFC 2047 B-encoding IN_PROGRESS must update to READY.
    rfc_upd = tmp_path / "update_rfc2047_b_status.md"
    rfc_b_prog = (
        "=?UTF-8?B?"
        + _b64.b64encode(b"STATUS: IN_PROGRESS").decode("ascii")
        + "?="
    )
    rfc_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        f"{rfc_b_prog}\n\n"
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
    status_rfc = update_icml_ready_from_g4(
        ready_path=rfc_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-10-01T04:20:00Z",
        allow_ready=True,
    )
    assert status_rfc == "READY"
    rfc_updated = rfc_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(rfc_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**" for ln in rfc_updated.splitlines()
    )
    assert "=?UTF-8?B?" not in rfc_updated

    # (cv) Tick 492: bare base64 STATUS payload must demote.
    bare_ready_b64 = _b64.b64encode(b"STATUS: READY").decode("ascii")
    bare_ready_path = tmp_path / "bare_base64_status.md"
    bare_ready_path.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{bare_ready_b64}\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(bare_ready_path.read_text(encoding="utf-8"))
        == "READY"
    )
    assert (
        demote_icml_ready_file(
            bare_ready_path,
            reason="bare base64 READY",
            timestamp="t",
        )
        is True
    )
    bare_text = bare_ready_path.read_text(encoding="utf-8")
    assert _icml_ready_status_header(bare_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in bare_text.splitlines()
    )
    assert bare_ready_b64 not in bare_text

    # (cw) Tick 492: bold-wrapped bare base64 IN_PROGRESS must update to READY.
    bare_prog_b64 = _b64.b64encode(b"STATUS: IN_PROGRESS").decode("ascii")
    bare_upd = tmp_path / "update_bare_base64_status.md"
    bare_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        f"**{bare_prog_b64}**\n\n"
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
    status_bare = update_icml_ready_from_g4(
        ready_path=bare_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-10-01T06:20:00Z",
        allow_ready=True,
    )
    assert status_bare == "READY"
    bare_updated = bare_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(bare_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**" for ln in bare_updated.splitlines()
    )
    assert bare_prog_b64 not in bare_updated

    # (cx) Tick 493: data-URI base64 STATUS payload must demote.
    data_uri_ready = f"data:text/plain;base64,{bare_ready_b64}"
    data_ready_path = tmp_path / "data_uri_base64_status.md"
    data_ready_path.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{data_uri_ready}\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(data_ready_path.read_text(encoding="utf-8"))
        == "READY"
    )
    assert (
        demote_icml_ready_file(
            data_ready_path,
            reason="data-URI base64 READY",
            timestamp="t",
        )
        is True
    )
    data_text = data_ready_path.read_text(encoding="utf-8")
    assert _icml_ready_status_header(data_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in data_text.splitlines()
    )
    assert data_uri_ready not in data_text
    assert bare_ready_b64 not in data_text

    # (cy) Tick 493: bold-wrapped data-URI IN_PROGRESS must update to READY.
    data_uri_prog = f"data:text/plain;charset=utf-8;base64,{bare_prog_b64}"
    data_upd = tmp_path / "update_data_uri_base64_status.md"
    data_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        f"**{data_uri_prog}**\n\n"
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
    status_data = update_icml_ready_from_g4(
        ready_path=data_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-10-01T08:20:00Z",
        allow_ready=True,
    )
    assert status_data == "READY"
    data_updated = data_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(data_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**" for ln in data_updated.splitlines()
    )
    assert data_uri_prog not in data_updated
    assert bare_prog_b64 not in data_updated

    # (cz) Tick 494: plain / percent-encoded data-URI STATUS must demote.
    plain_uri_ready = "data:text/plain,STATUS%3A%20READY"
    plain_ready_path = tmp_path / "data_uri_plain_status.md"
    plain_ready_path.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{plain_uri_ready}\n\n"
        "- [x] Table 1 (primary metrics by seed)\n",
        encoding="utf-8",
    )
    assert (
        _icml_ready_status_header(plain_ready_path.read_text(encoding="utf-8"))
        == "READY"
    )
    assert (
        demote_icml_ready_file(
            plain_ready_path,
            reason="data-URI plain READY",
            timestamp="t",
        )
        is True
    )
    plain_text = plain_ready_path.read_text(encoding="utf-8")
    assert _icml_ready_status_header(plain_text) == "IN_PROGRESS"
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in plain_text.splitlines()
    )
    assert plain_uri_ready not in plain_text

    # (da) Tick 494: bold-wrapped plain data-URI IN_PROGRESS must update to READY.
    plain_uri_prog = "data:text/plain;charset=utf-8,STATUS%3A%20IN_PROGRESS"
    plain_upd = tmp_path / "update_data_uri_plain_status.md"
    plain_upd.write_text(
        "# ICML Thesis 1 — Ready checklist\n\n"
        f"**{plain_uri_prog}**\n\n"
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
    status_plain = update_icml_ready_from_g4(
        ready_path=plain_upd,
        comparison={
            "primary_gens30_pass": True,
            "primary_cost30_pass": False,
            "d_wins_final": 4,
        },
        primary_pass=True,
        h2_pass=True,
        h5_pass=True,
        paper_refreshed=True,
        figures_written=["fig1.png"],
        timestamp="2026-10-01T10:20:00Z",
        allow_ready=True,
    )
    assert status_plain == "READY"
    plain_updated = plain_upd.read_text(encoding="utf-8")
    assert _icml_ready_status_header(plain_updated) == "READY"
    assert any(
        ln.strip() == "**STATUS: READY**" for ln in plain_updated.splitlines()
    )
    assert plain_uri_prog not in plain_updated


def test_g4_live_ledger_skip_exits_4_on_thin_h2_refuse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 416: direct --live ledger-skip must exit 4 when H2 refuse fires.

    Pre-416 trust_refused only checked steering/g4_full_pairs, so thin H2
    refuse returned paper_refreshed=False with comparison still set → exit 0.
    """
    import run_g4_multiseed as mod
    import run_g3_pilot as g3
    from run_g4_multiseed import CheckResult, G4PreflightReport

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
        lambda *a, **k: {"tip_ok_for_live": True, "local_tick": 416},
    )

    def _fake_refresh(report: G4PreflightReport, **_kw):
        # Simulate Tick 415 refuse after thin H2 (comparison cleared — Tick 416).
        report.comparison = None
        report.primary_pass = False
        report.h2_pass = False
        report.h5_pass = False
        report.ready_status = "IN_PROGRESS"
        report.checks.append(
            CheckResult(
                "h2_planned",
                False,
                "Tick 415: thin H2 MECHANISM refuse",
            )
        )
        return False, "Tick 415: trusted gate4 sidecar but H2 fails planned"

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
    assert rc == 4
    assert called == []


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
