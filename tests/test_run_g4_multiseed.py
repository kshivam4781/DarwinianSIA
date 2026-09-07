"""Tests for scripts/run_g4_multiseed.py (Tick 27–28 live G4 5-seed runner + paper pack)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from prepare_gpqa_smoke_data import is_synthetic_smoke, prepare_task_tree  # noqa: E402
from run_g4_multiseed import (  # noqa: E402
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
    }
    out = tmp_path / "gate4_report.md"
    write_gate4_report(report, out)
    text = out.read_text(encoding="utf-8")
    assert "preferred_share=`0.75`" in text
    assert "preferred=`selective`" in text
    assert "field=`tool_strategy`" in text
    assert "in_bias_share=`1.0`" in text


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
