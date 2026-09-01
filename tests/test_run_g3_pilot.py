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

    plans = [PilotPlan(seed=1, b_run_id=1201, d_run_id=1301)]
    report = run_preflight(mode="live", plans=plans, pair_estimate_usd=4.0)
    assert report.ready_for_live is True
    assert report.blockers == []
    assert is_synthetic_smoke(task) is False


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

    monkeypatch.setattr(mod, "compare_b_vs_d", fake_compare)
    monkeypatch.setattr(mod, "compute_h5", fake_h5)
    b = tmp_path / "run_1201"
    d = tmp_path / "run_1301"
    b.mkdir()
    d.mkdir()
    cmp_, h5 = score_pilot([b], [d])
    assert cmp_["d_wins_gens30"] == 1
    assert h5["run_1301"]["spearman_rho"] == 0.5


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
