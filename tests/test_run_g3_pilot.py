"""Tests for scripts/run_g3_pilot.py (Tick 26 live G3 sequential pilot)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from prepare_gpqa_smoke_data import is_synthetic_smoke, prepare_task_tree  # noqa: E402
from run_g3_pilot import (  # noqa: E402
    G3PreflightReport,
    CheckResult,
    PilotPlan,
    build_plans,
    build_sia_command,
    parse_int_list,
    run_preflight,
    score_pilot,
    write_gate3_report,
)


def test_parse_and_build_plans() -> None:
    assert parse_int_list("1,2") == [1, 2]
    plans = build_plans([1, 2], [1201, 1202], [1301, 1302])
    assert plans[0].b_run_id == 1201
    assert plans[1].d_run_id == 1302
    with pytest.raises(ValueError, match="1–2 seeds"):
        build_plans([1, 2, 3], [1, 2, 3], [4, 5, 6])
    with pytest.raises(ValueError, match="unique"):
        build_plans([1], [1201], [1201])


def test_build_sia_command_b_vs_d() -> None:
    b = build_sia_command(condition="B", run_id=1201, seed=1)
    assert "--cabs" not in b
    assert "--cabs-inline" not in b
    assert "1201" in b
    # Tick 296: Nebius budget-fit defaults (eval5/pop4/max_gen6; not Anthropic-era 15)
    assert "--eval_subset" in b and "5" in b
    assert "--population_size" in b and "4" in b
    assert "--max_gen" in b and "6" in b
    assert "--meta-agent-profile" in b
    assert "kimi-nebius-pydantic-meta" in b
    assert "--target-agent-profile" in b
    assert "kimi-nebius-target" in b
    d = build_sia_command(condition="D", run_id=1301, seed=1)
    assert "--cabs" in d and "--cabs-inline" in d
    assert "--meta-agent-profile" in d
    assert "kimi-nebius-pydantic-meta" in d
    assert "--target-agent-profile" in d
    assert "kimi-nebius-target" in d
    with pytest.raises(ValueError, match="max_gen"):
        build_sia_command(condition="B", run_id=1, seed=1, max_gen=7)


def test_preflight_blocks_without_keys(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)

    import run_g3_pilot as mod

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    task.mkdir(parents=True)
    prepare_task_tree(task, n=5)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")

    plans = [PilotPlan(seed=1, b_run_id=1201, d_run_id=1301)]
    report = run_preflight(mode="preflight", plans=plans)
    assert report.ready_for_live is False
    names = {c.name: c.ok for c in report.checks}
    assert names["anthropic_key"] is True  # Tick 289 optional under Nebius meta
    assert names["nebius_key"] is False
    assert names["gpqa_not_synthetic"] is False
    assert names["sequential_only"] is True
    assert len(report.commands) == 2  # B then D


def test_preflight_live_ready_with_keys_and_real_gpqa(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-ant")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-neb")
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")

    import run_g3_pilot as mod

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
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
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

    plans = [PilotPlan(seed=1, b_run_id=1201, d_run_id=1301)]
    report = run_preflight(mode="live", plans=plans, pair_estimate_usd=4.0)
    assert report.ready_for_live is True
    assert report.blockers == []
    assert is_synthetic_smoke(task) is False


def test_preflight_refuses_stale_recipe_or_offline_bvd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 303: direct G3 --live refuses when shape locks fail (not only pipeline)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-ant")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-neb")
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")

    import run_g3_pilot as mod

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
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
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
        lambda **_k: (False, ["docs/gate3_report.json commands[0] shape stale"]),
    )
    monkeypatch.setattr(
        mod, "committed_offline_bvd_matches_live_shape", lambda **_k: (True, [])
    )

    plans = [PilotPlan(seed=1, b_run_id=1201, d_run_id=1301)]
    report = run_preflight(mode="live", plans=plans, pair_estimate_usd=4.0)
    assert report.ready_for_live is False
    names = {c.name: c.ok for c in report.checks}
    assert names["g3g4_recipes_match_live_shape"] is False
    assert names["offline_bvd_matches_live_shape"] is True
    assert names["nebius_key"] is True
    assert names["gpqa_not_synthetic"] is True

    monkeypatch.setattr(
        mod, "committed_g3g4_recipes_match_live_shape", lambda **_k: (True, [])
    )
    monkeypatch.setattr(
        mod,
        "committed_offline_bvd_matches_live_shape",
        lambda **_k: (False, ["docs/offline_bvd_summary.json: figures must list ≥2"]),
    )
    report2 = run_preflight(mode="live", plans=plans, pair_estimate_usd=4.0)
    assert report2.ready_for_live is False
    names2 = {c.name: c.ok for c in report2.checks}
    assert names2["offline_bvd_matches_live_shape"] is False
    assert names2["g3g4_recipes_match_live_shape"] is True


def test_preflight_refuses_stale_tip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 305: direct G3 --live refuses when tip lineage lags (not only pipeline)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-ant")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-neb")
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")

    import run_g3_pilot as mod

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
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
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

    plans = [PilotPlan(seed=1, b_run_id=1201, d_run_id=1301)]
    report = run_preflight(mode="live", plans=plans, pair_estimate_usd=4.0)
    assert report.ready_for_live is False
    names = {c.name: c.ok for c in report.checks}
    assert names["tip_ok_for_live"] is False
    assert names["g3g4_recipes_match_live_shape"] is True

    report2 = run_preflight(
        mode="live", plans=plans, pair_estimate_usd=4.0, allow_stale_tip=True
    )
    assert report2.ready_for_live is True
    names2 = {c.name: c.ok for c in report2.checks}
    assert names2["tip_ok_for_live"] is True
    assert any("allow-stale-tip" in n for n in report2.notes)


def test_budget_projection_blocks_over_ceiling(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-ant")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-neb")
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "18")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")

    import run_g3_pilot as mod

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
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
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
            "tip_ok_for_live": True,
            "local_tick": 305,
            "remote_tip_ref": "refs/remotes/origin/cursor/icml-epistemic-results-test",
            "blockers": [],
        },
    )

    plans = [
        PilotPlan(seed=1, b_run_id=1201, d_run_id=1301),
        PilotPlan(seed=2, b_run_id=1202, d_run_id=1302),
    ]
    # 18 + 4*2 = 26 > 20
    report = run_preflight(mode="live", plans=plans, pair_estimate_usd=4.0)
    assert report.ready_for_live is False
    assert any(c.name == "budget" and not c.ok for c in report.checks)


def test_write_gate3_report_preserves_offline_block(tmp_path: Path) -> None:
    existing = (
        "# Gate 3 report — Pilot B vs D\n\n"
        "## Offline synthetic pilot (Tick 23 — not a live G3 substitute)\n\n"
        "Offline gens30 **4/5** preserved.\n\n"
        "## Blockers (live G3)\n\n"
        "- old blocker\n"
    )
    report = G3PreflightReport(
        timestamp="2026-08-06T00:10:00Z",
        mode="preflight",
        plans=[PilotPlan(seed=1, b_run_id=1201, d_run_id=1301)],
        ready_for_live=False,
        commands=[["sia", "run", "--darwinian"]],
        blockers=["anthropic_key: missing"],
    )
    report.checks.append(CheckResult("anthropic_key", False, "missing"))
    out = tmp_path / "gate3_report.md"
    write_gate3_report(report, out, existing_text=existing)
    text = out.read_text(encoding="utf-8")
    assert "Offline gens30 **4/5** preserved" in text
    assert "Live G3 preflight" in text
    assert "sequential" in text.lower()
    payload = json.loads(out.with_suffix(".json").read_text())
    assert payload["ready_for_live"] is False
    assert payload["plans"][0]["b_run_id"] == 1201


def test_main_preflight_refuses_live_without_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import run_g3_pilot as mod

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    task.mkdir(parents=True)
    prepare_task_tree(task, n=5)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")

    report_path = tmp_path / "docs" / "gate3_report.md"
    report_path.parent.mkdir(parents=True)
    # Seed a legacy offline section
    report_path.write_text(
        "# Gate 3\n\n## Offline synthetic pilot\n\nKeep me.\n\n## Blockers\n\n- x\n",
        encoding="utf-8",
    )

    rc = mod.main(
        [
            "--preflight-only",
            "--seeds",
            "1",
            "--b-run-ids",
            "1201",
            "--d-run-ids",
            "1301",
            "--report",
            str(report_path),
        ]
    )
    assert rc == 0
    text = report_path.read_text(encoding="utf-8")
    assert "Keep me" in text
    assert "ready_for_live=no" in text.lower() or "Live G3 ready:** no" in text
    payload = json.loads(report_path.with_suffix(".json").read_text())
    assert payload["ready_for_live"] is False

    rc_live = mod.main(
        [
            "--live",
            "--seeds",
            "1",
            "--b-run-ids",
            "1201",
            "--d-run-ids",
            "1301",
            "--report",
            str(report_path),
        ]
    )
    assert rc_live == 3


def test_run_sequential_live_order(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import run_g3_pilot as mod

    calls: list[str] = []

    def fake_run(cmd, cwd=None, env=None):  # noqa: ANN001
        # cmd contains run_id after --run_id
        rid = cmd[cmd.index("--run_id") + 1]
        cond = "D" if "--cabs-inline" in cmd else "B"
        calls.append(f"{cond}:{rid}")
        run_dir = tmp_path / "SIA" / "runs" / f"run_{rid}"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "marker.txt").write_text(cond, encoding="utf-8")

        class P:
            returncode = 0

        return P()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")

    report = G3PreflightReport(
        timestamp="t",
        mode="live",
        plans=[
            PilotPlan(seed=1, b_run_id=1201, d_run_id=1301),
            PilotPlan(seed=2, b_run_id=1202, d_run_id=1302),
        ],
        ready_for_live=True,
    )
    b_dirs, d_dirs, notes = mod.run_sequential_live(
        report,
        cwd=tmp_path / "SIA",
        eval_subset=15,
        population_size=4,
        elite_count=2,
        max_gen=5,
    )
    assert calls == ["B:1201", "D:1301", "B:1202", "D:1302"]
    assert len(b_dirs) == 2 and len(d_dirs) == 2
    assert all("ok" in n for n in notes)


def test_score_pilot_wires_compare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import run_g3_pilot as mod

    def fake_compare(b_runs, d_runs):  # noqa: ANN001
        return {"n_pairs": 1, "d_wins_gens30": 1, "b_wins_gens30": 0}

    def fake_h5(run_dir):  # noqa: ANN001
        return {"spearman_rho": 0.5}

    def fake_h2(d_dirs, field=None):  # noqa: ANN001
        return {
            d_dirs[0].name: {
                "field": "tool_strategy",
                "preferred_value": "selective",
                "preferred_share": 0.75,
                "in_bias_share": 1.0,
            }
        }

    monkeypatch.setattr(mod, "compare_b_vs_d", fake_compare)
    monkeypatch.setattr(mod, "compute_h5", fake_h5)
    # Tick 368: score_pilot lazily imports score_live_h2 from run_g4_multiseed.
    import run_g4_multiseed as g4

    monkeypatch.setattr(g4, "score_live_h2", fake_h2)
    b = tmp_path / "run_1201"
    d = tmp_path / "run_1301"
    b.mkdir()
    d.mkdir()
    cmp_, h5, h2 = score_pilot([b], [d])
    assert cmp_["d_wins_gens30"] == 1
    assert h5["run_1301"]["spearman_rho"] == 0.5
    assert h2["run_1301"]["preferred_share"] == 0.75


def test_write_gate3_report_surfaces_h2_and_mean_gap(tmp_path: Path) -> None:
    """Tick 368: live G3 metrics show mean_final_gap + H2 preferred (G4 parity)."""
    report = G3PreflightReport(
        timestamp="2026-09-07T06:10:00Z",
        mode="live",
        plans=[PilotPlan(seed=1, b_run_id=1201, d_run_id=1301)],
        ready_for_live=True,
        commands=[["sia", "run", "--darwinian"]],
        comparison={
            "n_pairs": 1,
            "d_wins_gens30": 1,
            "b_wins_gens30": 0,
            "d_wins_cost30": 1,
            "b_wins_cost30": 0,
            "d_wins_final": 1,
            "b_wins_final": 0,
            "d_wins_h2": 1,
            "h2_preferred_pass": False,  # n<5 → aggregate False; per-seed still shown
            "mean_final_gap": 0.0615,
            "primary_final_pass": False,
        },
        h5_by_d_run={"run_1301": {"spearman_rho": 0.8}},
        h2_by_d_run={
            "run_1301": {
                "field": "tool_strategy",
                "preferred_value": "selective",
                "preferred_share": 0.75,
                "in_bias_share": 1.0,
                "counts": {"selective": 3, "aggressive": 1},
            }
        },
    )
    out = tmp_path / "gate3_report.md"
    write_gate3_report(report, out, executed=True)
    text = out.read_text(encoding="utf-8")
    assert "mean_final_gap" in text.lower() or "Mean final gap" in text
    assert "0.0615" in text
    assert "h2_preferred_pass" in text
    assert "d_wins_h2=1/1" in text or "H2 preferred ≥0.5: **1/1**" in text
    assert "preferred_share=`0.75`" in text
    assert "field=`tool_strategy`" in text
    payload = json.loads(out.with_suffix(".json").read_text())
    assert payload["h2_by_d_run"]["run_1301"]["preferred_share"] == 0.75
    assert payload["comparison"]["mean_final_gap"] == 0.0615


def test_main_live_fetch_diamond_refuses_without_hf(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 275: G3 --live --fetch-diamond exits 4 before materialize without HF."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("NEBIUS_API_KEY", "nb-test")
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)

    import run_g3_pilot as mod

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
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")

    called: list[str] = []

    def boom(*_a, **_k):
        called.append("hf")
        raise AssertionError("must not materialize from HF")

    monkeypatch.setattr(mod, "materialize_from_hf", boom)
    report_path = tmp_path / "docs" / "gate3_report.md"
    rc = mod.main(
        [
            "--live",
            "--seeds",
            "1",
            "--b-run-ids",
            "1201",
            "--d-run-ids",
            "1301",
            "--fetch-diamond",
            "--report",
            str(report_path),
        ]
    )
    assert rc == 4
    assert called == []
    text = report_path.read_text(encoding="utf-8")
    assert "HF_TOKEN" in text or "fetch_diamond" in text.lower()


def _write_complete_run(run_dir: Path) -> None:
    agent = run_dir / "gen_1" / "agent_0"
    agent.mkdir(parents=True, exist_ok=True)
    (agent / "results.json").write_text('{"accuracy": 0.2}', encoding="utf-8")


def _write_d_gen_feedback(run_dir: Path, gen: int, *, with_agenda: bool) -> None:
    """Minimal Condition D gen_N/agent_* feedback artifacts for Tick 407."""
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


def test_classify_plan_run_occupancy_resume_vs_incomplete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 375: complete runs are resume-ok; incomplete dirs block."""
    import run_g3_pilot as mod

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    (tmp_path / "runs").mkdir(parents=True)
    (tmp_path / "SIA" / "runs").mkdir(parents=True)

    complete = tmp_path / "runs" / "run_1201"
    _write_complete_run(complete)
    incomplete = tmp_path / "runs" / "run_1202"
    incomplete.mkdir(parents=True)

    plans = [
        PilotPlan(seed=1, b_run_id=1201, d_run_id=1301),  # B complete, D missing
        PilotPlan(seed=2, b_run_id=1202, d_run_id=1302),  # B incomplete
    ]
    resume_ok, blocked, needing = mod.classify_plan_run_occupancy(plans)
    assert any("1201" in s for s in resume_ok)
    assert any("1202" in s and "incomplete" in s for s in blocked)
    assert needing == 2


def test_g3_preflight_resume_skips_complete_run_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 375: completed planned IDs do not clear run_ids_free."""
    import run_g3_pilot as mod

    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    (tmp_path / "runs").mkdir(parents=True)

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    task.mkdir(parents=True)
    prepare_task_tree(task, n=5)
    # Make non-synthetic so other checks aren't the only focus — still may fail
    # diamond synthetic check; we only assert run_ids_free.
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

    _write_complete_run(tmp_path / "runs" / "run_1201")
    _write_complete_run(tmp_path / "runs" / "run_1301")

    plans = [PilotPlan(seed=1, b_run_id=1201, d_run_id=1301)]
    report = mod.run_preflight(mode="preflight", plans=plans)
    names = {c.name: c for c in report.checks}
    assert names["run_ids_free"].ok is True
    assert "resume-ok" in names["run_ids_free"].detail or "Tick 375" in names["run_ids_free"].detail
    assert "remaining" in names["budget"].detail
    # Both complete → 0 billable pairs
    assert "0 remaining" in names["budget"].detail


def test_run_sequential_live_resume_skips_complete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 375: already-complete B/D are skipped; only missing IDs launch."""
    import run_g3_pilot as mod

    calls: list[str] = []

    def fake_run(cmd, cwd=None, env=None):  # noqa: ANN001
        rid = cmd[cmd.index("--run_id") + 1]
        cond = "D" if "--cabs-inline" in cmd else "B"
        calls.append(f"{cond}:{rid}")
        run_dir = tmp_path / "SIA" / "runs" / f"run_{rid}"
        _write_complete_run(run_dir)

        class P:
            returncode = 0

        return P()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    (tmp_path / "runs").mkdir(parents=True)
    (tmp_path / "SIA" / "runs").mkdir(parents=True)

    # Seed1 fully complete; seed2 missing
    _write_complete_run(tmp_path / "runs" / "run_1201")
    _write_complete_run(tmp_path / "runs" / "run_1301")

    report = G3PreflightReport(
        timestamp="t",
        mode="live",
        plans=[
            PilotPlan(seed=1, b_run_id=1201, d_run_id=1301),
            PilotPlan(seed=2, b_run_id=1202, d_run_id=1302),
        ],
        ready_for_live=True,
    )
    b_dirs, d_dirs, notes = mod.run_sequential_live(
        report,
        cwd=tmp_path / "SIA",
        eval_subset=5,
        population_size=4,
        elite_count=2,
        max_gen=6,
    )
    assert calls == ["B:1202", "D:1302"]
    assert len(b_dirs) == 2 and len(d_dirs) == 2
    assert any("resume-skip" in n for n in notes)


def test_refresh_g3_metrics_on_ledger_skip_local_dirs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 382: ledger-skip re-scores local B/D into gate3 metrics."""
    import run_g3_pilot as mod

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    (tmp_path / "runs").mkdir(parents=True)
    docs = tmp_path / "docs"
    docs.mkdir()

    _write_complete_run(tmp_path / "runs" / "run_1201")
    _write_complete_run(tmp_path / "runs" / "run_1301")
    # Tick 407: Condition D must evidence gen≥3 steering for ledger-skip ok.
    _write_d_gen_feedback(tmp_path / "runs" / "run_1301", 3, with_agenda=True)

    report = G3PreflightReport(
        timestamp="2026-09-08T10:05:00Z",
        mode="live",
        plans=[PilotPlan(seed=1, b_run_id=1201, d_run_id=1301)],
        ready_for_live=True,
        ledger_skip=True,
    )
    calls: dict[str, object] = {}

    def _fake_score(b_dirs, d_dirs):  # noqa: ANN001
        calls["b_dirs"] = [str(p) for p in b_dirs]
        calls["d_dirs"] = [str(p) for p in d_dirs]
        return (
            {
                "n_pairs": 1,
                "d_wins_gens30": 1,
                "mean_final_gap": 0.05,
                "primary_final_pass": True,
            },
            {"run_1301": {"spearman_rho": 0.8}},
            {"run_1301": {"preferred_share": 0.75, "field": "tool_strategy"}},
        )

    monkeypatch.setattr(mod, "score_pilot", _fake_score)
    ok, note = mod.refresh_g3_metrics_on_ledger_skip(
        report, gate3_report_md=docs / "gate3_report.md"
    )
    assert ok is True
    assert "re-scored G3 from local" in note
    assert "steering ok" in note
    assert len(calls["b_dirs"]) == 1  # type: ignore[arg-type]
    assert len(calls["d_dirs"]) == 1  # type: ignore[arg-type]
    assert report.comparison is not None
    assert report.comparison["d_wins_gens30"] == 1
    assert report.h5_by_d_run["run_1301"]["spearman_rho"] == 0.8


def test_refresh_g3_metrics_on_ledger_skip_trusts_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 382: no local dirs → trust live-executed gate3 sidecar."""
    import run_g3_pilot as mod

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    (tmp_path / "runs").mkdir(parents=True)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "gate3_report.json").write_text(
        json.dumps(
            {
                "mode": "live",
                "executed": True,
                "comparison": {
                    "n_pairs": 1,
                    "d_wins_gens30": 1,
                    "mean_final_gap": 0.04,
                    "primary_final_pass": True,
                },
                "h5_by_d_run": {"run_1301": {"spearman_rho": 0.6}},
                "h2_by_d_run": {"run_1301": {"preferred_share": 0.7}},
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate3_report.md").write_text("# Gate 3\n", encoding="utf-8")

    report = G3PreflightReport(
        timestamp="2026-09-08T10:05:00Z",
        mode="live",
        plans=[PilotPlan(seed=1, b_run_id=1201, d_run_id=1301)],
        ready_for_live=True,
        ledger_skip=True,
    )
    ok, note = mod.refresh_g3_metrics_on_ledger_skip(
        report, gate3_report_md=docs / "gate3_report.md"
    )
    assert ok is True
    assert "trusted live-executed gate3 sidecar" in note
    assert report.comparison is not None
    assert report.comparison["d_wins_gens30"] == 1
    assert report.h5_by_d_run["run_1301"]["spearman_rho"] == 0.6


def test_refresh_g3_metrics_on_ledger_skip_refuses_preflight_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 382: preflight sidecar must not invent G3 metrics on ledger-skip."""
    import run_g3_pilot as mod

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    (tmp_path / "runs").mkdir(parents=True)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "gate3_report.json").write_text(
        json.dumps(
            {
                "mode": "preflight",
                "executed": False,
                "comparison": None,
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate3_report.md").write_text("# Gate 3\n", encoding="utf-8")

    report = G3PreflightReport(
        timestamp="2026-09-08T10:05:00Z",
        mode="live",
        plans=[PilotPlan(seed=1, b_run_id=1201, d_run_id=1301)],
        ready_for_live=True,
        ledger_skip=True,
    )
    ok, note = mod.refresh_g3_metrics_on_ledger_skip(
        report, gate3_report_md=docs / "gate3_report.md"
    )
    assert ok is False
    assert "metrics not updated" in note
    assert report.comparison is None


def test_g3_live_ledger_skip_refreshes_metrics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 382: direct --live ledger-skip calls metrics refresh (no sia)."""
    import run_g3_pilot as mod

    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("SIA_BUDGET_SPENT_USD", raising=False)
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {
                "spent_usd": 4.0,
                "stages_complete": ["G2", "G3"],
                "run_ids": [1300, 1201, 1301],
                "detail": "g2+g3",
            }
        ),
        encoding="utf-8",
    )
    # Pre-existing live sidecar that Tick 380 would have clobbered.
    (docs / "gate3_report.json").write_text(
        json.dumps(
            {
                "mode": "live",
                "executed": True,
                "comparison": {
                    "n_pairs": 1,
                    "d_wins_gens30": 1,
                    "mean_final_gap": 0.06,
                    "primary_final_pass": True,
                },
                "h5_by_d_run": {"run_1301": {"spearman_rho": 0.9}},
                "h2_by_d_run": {},
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate3_report.md").write_text(
        "# Gate 3 report — Pilot B vs D\n\n"
        "<!-- OFFLINE_G3_PILOT_START -->\n"
        "## Offline synthetic pilot (not a live G3 substitute)\n\n"
        "stub\n"
        "<!-- OFFLINE_G3_PILOT_END -->\n",
        encoding="utf-8",
    )

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    task.mkdir(parents=True)
    prepare_task_tree(task, n=5)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
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
        lambda *a, **k: {"tip_ok_for_live": True, "local_tick": 382},
    )

    sia_calls: list[list[str]] = []

    def _fake_run(cmd, cwd=None, env=None):  # noqa: ANN001
        sia_calls.append(list(cmd))

        class P:
            returncode = 0

        return P()

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)

    rc = mod.main(
        [
            "--live",
            "--seeds",
            "1",
            "--b-run-ids",
            "1201",
            "--d-run-ids",
            "1301",
            "--report",
            str(docs / "gate3_report.md"),
            "--cwd",
            str(tmp_path / "SIA"),
            "--allow-stale-tip",
        ]
    )
    assert rc == 0
    assert sia_calls == []
    sidecar = json.loads((docs / "gate3_report.json").read_text(encoding="utf-8"))
    assert sidecar["executed"] is True
    assert sidecar["comparison"]["d_wins_gens30"] == 1
    text = (docs / "gate3_report.md").read_text(encoding="utf-8")
    assert "Tick 382" in text or "ledger" in text.lower()
    assert "Live pilot metrics" in text


def test_write_gate3_preflight_preserves_prior_live_metrics(tmp_path: Path) -> None:
    """Tick 385: preflight rewrite keeps prior_live_metrics for G3→G4 trust."""
    import run_g3_pilot as mod

    report_md = tmp_path / "gate3_report.md"
    sidecar = report_md.with_suffix(".json")
    live_cmp = {
        "n_pairs": 1,
        "d_wins_gens30": 1,
        "mean_final_gap": 0.04,
        "primary_final_pass": True,
    }
    sidecar.write_text(
        json.dumps(
            {
                "mode": "live",
                "executed": True,
                "comparison": live_cmp,
                "h5_by_d_run": {"run_1301": {"spearman_rho": 0.7}},
                "h2_by_d_run": {"run_1301": {"preferred_share": 0.8}},
            }
        ),
        encoding="utf-8",
    )
    report_md.write_text("# Gate 3\n", encoding="utf-8")
    report = G3PreflightReport(
        timestamp="2026-09-08T16:10:00Z",
        mode="preflight",
        plans=[PilotPlan(seed=1, b_run_id=1201, d_run_id=1301)],
        ready_for_live=False,
        blockers=["nebius_key"],
        checks=[],
        commands=[],
        notes=[],
    )
    mod.write_gate3_report(report, report_md, executed=False)
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["mode"] == "preflight"
    assert data["comparison"] is None
    assert data["executed"] is False
    assert data["prior_live_metrics"]["comparison"]["d_wins_gens30"] == 1
    assert data["prior_live_metrics"]["h5_by_d_run"]["run_1301"]["spearman_rho"] == 0.7
    cmp_, h5, h2, source = mod._live_metrics_from_gate3_sidecar(data)
    assert source == "prior_live_metrics"
    assert cmp_ is not None and cmp_["d_wins_gens30"] == 1
    assert h5["run_1301"]["spearman_rho"] == 0.7
    assert h2["run_1301"]["preferred_share"] == 0.8


def test_refresh_g3_metrics_on_ledger_skip_trusts_prior_live_metrics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 385: ledger-skip trusts prior_live_metrics after preflight wipe."""
    import run_g3_pilot as mod

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    (tmp_path / "runs").mkdir(parents=True)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "gate3_report.json").write_text(
        json.dumps(
            {
                "mode": "preflight",
                "executed": False,
                "comparison": None,
                "prior_live_metrics": {
                    "comparison": {
                        "n_pairs": 1,
                        "d_wins_gens30": 1,
                        "mean_final_gap": 0.05,
                        "primary_final_pass": True,
                    },
                    "h5_by_d_run": {"run_1301": {"spearman_rho": 0.65}},
                    "h2_by_d_run": {"run_1301": {"preferred_share": 0.7}},
                    "executed": True,
                },
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate3_report.md").write_text("# Gate 3\n", encoding="utf-8")
    report = G3PreflightReport(
        timestamp="2026-09-08T16:11:00Z",
        mode="live",
        plans=[PilotPlan(seed=1, b_run_id=1201, d_run_id=1301)],
        ready_for_live=True,
        ledger_skip=True,
    )
    ok, note = mod.refresh_g3_metrics_on_ledger_skip(
        report, gate3_report_md=docs / "gate3_report.md"
    )
    assert ok is True
    assert "prior_live_metrics" in note
    assert report.comparison is not None
    assert report.comparison["d_wins_gens30"] == 1
    assert report.h5_by_d_run["run_1301"]["spearman_rho"] == 0.65


def test_validate_g3_d_steering_positive_control(tmp_path: Path) -> None:
    """Tick 407: gen≥3 must show Contradiction-Aware agenda (delay-all lifted)."""
    from run_g3_pilot import validate_g3_d_steering

    d_ok = tmp_path / "run_1301"
    _write_d_gen_feedback(d_ok, 2, with_agenda=False)
    _write_d_gen_feedback(d_ok, 3, with_agenda=True)
    checks = {c.name: c for c in validate_g3_d_steering([d_ok])}
    assert checks["steering_applied_gen3"].ok is True
    assert checks["steering_applied_run_1301"].ok is True

    d_bad = tmp_path / "run_1302"
    _write_d_gen_feedback(d_bad, 2, with_agenda=False)
    _write_d_gen_feedback(d_bad, 3, with_agenda=False)
    leaked = {c.name: c for c in validate_g3_d_steering([d_bad])}
    assert leaked["steering_applied_gen3"].ok is False
    assert leaked["steering_applied_run_1302"].ok is False
    assert "never steered" in leaked["steering_applied_run_1302"].detail

    d_missing = tmp_path / "run_1303"
    d_missing.mkdir()
    (d_missing / "results.json").write_text("{}", encoding="utf-8")
    missing = {c.name: c for c in validate_g3_d_steering([d_missing])}
    assert missing["steering_applied_gen3"].ok is False
    assert "no gen_3" in missing["steering_applied_run_1303"].detail


def test_refresh_g3_metrics_refuses_never_steer_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 407: ledger-skip local re-score fails when D gen3 lacks agenda."""
    import run_g3_pilot as mod

    runs = tmp_path / "runs"
    b = runs / "run_1201"
    d = runs / "run_1301"
    b.mkdir(parents=True)
    d.mkdir(parents=True)
    (b / "results.json").write_text(
        json.dumps({"accuracy": 0.1}), encoding="utf-8"
    )
    (d / "results.json").write_text(
        json.dumps({"accuracy": 0.2}), encoding="utf-8"
    )
    _write_d_gen_feedback(d, 3, with_agenda=False)

    monkeypatch.setattr(mod, "_run_dir_for", lambda rid: runs / f"run_{rid}")
    monkeypatch.setattr(
        mod,
        "darwinian_run_complete",
        lambda p: p is not None and (p / "results.json").is_file(),
    )
    monkeypatch.setattr(
        mod,
        "score_pilot",
        lambda b_dirs, d_dirs: (
            {"n_pairs": 1, "d_wins_gens30": 1, "mean_final_gap": 0.05},
            {"run_1301": {"spearman_rho": 0.8}},
            {"run_1301": {"preferred_share": 0.7}},
        ),
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "gate3_report.md").write_text("# Gate 3\n", encoding="utf-8")
    report = G3PreflightReport(
        timestamp="2026-09-10T12:00:00Z",
        mode="live",
        plans=[PilotPlan(seed=1, b_run_id=1201, d_run_id=1301)],
        ready_for_live=True,
        ledger_skip=True,
    )
    ok, note = mod.refresh_g3_metrics_on_ledger_skip(
        report, gate3_report_md=docs / "gate3_report.md"
    )
    assert ok is False
    assert "steering FAILED" in note
    assert any(
        c.name == "steering_applied_gen3" and not c.ok for c in report.checks
    )


def test_refresh_g3_metrics_refuses_sidecar_steering_false(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 407: sidecar with steering_applied_gen3=false refuses G4 advance."""
    import run_g3_pilot as mod

    monkeypatch.setattr(mod, "_run_dir_for", lambda rid: None)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "gate3_report.json").write_text(
        json.dumps(
            {
                "mode": "live",
                "executed": True,
                "steering_applied_gen3": False,
                "comparison": {
                    "n_pairs": 1,
                    "d_wins_gens30": 1,
                    "mean_final_gap": 0.06,
                },
                "h5_by_d_run": {"run_1301": {"spearman_rho": 0.9}},
                "h2_by_d_run": {},
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate3_report.md").write_text("# Gate 3\n", encoding="utf-8")
    report = G3PreflightReport(
        timestamp="2026-09-10T12:00:00Z",
        mode="live",
        plans=[PilotPlan(seed=1, b_run_id=1201, d_run_id=1301)],
        ready_for_live=True,
        ledger_skip=True,
    )
    ok, note = mod.refresh_g3_metrics_on_ledger_skip(
        report, gate3_report_md=docs / "gate3_report.md"
    )
    assert ok is False
    assert "steering_applied_gen3=false" in note