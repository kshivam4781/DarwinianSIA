"""Tests for scripts/run_g2_smoke.py (Tick 24 live G2 preflight)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from prepare_gpqa_smoke_data import is_synthetic_smoke, prepare_task_tree  # noqa: E402
from run_g2_smoke import (  # noqa: E402
    build_sia_command,
    run_preflight,
    validate_g2_artifacts,
    write_gate2_report,
)


def test_is_synthetic_smoke_detects_fixture(tmp_path: Path) -> None:
    task_dir = tmp_path / "gpqa"
    task_dir.mkdir()
    prepare_task_tree(task_dir, n=5)
    assert is_synthetic_smoke(task_dir) is True


def test_is_synthetic_smoke_false_for_real_looking(tmp_path: Path) -> None:
    task_dir = tmp_path / "gpqa"
    pub = task_dir / "data" / "public"
    priv = task_dir / "data" / "private"
    pub.mkdir(parents=True)
    priv.mkdir(parents=True)
    rows = [
        {
            "id": 1,
            "Question": "Which enzyme catalyzes …?",
            "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
            "correct_answer_letter": "B",
            "domain": "biology",
        }
    ]
    (pub / "diamond_questions.json").write_text(json.dumps(rows), encoding="utf-8")
    (priv / "diamond_questions.json").write_text(json.dumps(rows), encoding="utf-8")
    (pub / "task.md").write_text("# real", encoding="utf-8")
    assert is_synthetic_smoke(task_dir) is False


def test_build_sia_command_flags() -> None:
    dry = build_sia_command(run_id=1850, seed=42, dry_run=True)
    assert "--dry-run" in dry
    assert "--cabs-inline" in dry
    assert "1850" in dry
    live = build_sia_command(run_id=1300, seed=1, dry_run=False)
    assert "--dry-run" not in live
    assert "1300" in live


def test_preflight_live_blocks_without_keys(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    # Point task tree at a temp smoke fixture via monkeypatch of helper paths
    import run_g2_smoke as mod

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    task.mkdir(parents=True)
    prepare_task_tree(task, n=5)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")

    report = run_preflight(mode="live", run_id=1300, ensure_smoke_layout=False)
    assert report.ready_for_live is False
    names = {c.name: c.ok for c in report.checks}
    assert names["anthropic_key"] is False
    assert names["nebius_key"] is False
    assert names["gpqa_not_synthetic"] is False  # smoke fixture


def test_preflight_live_ready_with_keys_and_real_gpqa(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-ant")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-neb")
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")

    import run_g2_smoke as mod

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
        }
        for i in range(5)
    ]
    (pub / "diamond_questions.json").write_text(json.dumps(rows), encoding="utf-8")
    (priv / "diamond_questions.json").write_text(json.dumps(rows), encoding="utf-8")
    (pub / "task.md").write_text("# GPQA", encoding="utf-8")

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")

    report = run_preflight(mode="live", run_id=1300, ensure_smoke_layout=False)
    assert report.ready_for_live is True
    assert report.blockers == []


def test_validate_g2_artifacts_reads_belief_store(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_1850"
    store = run_dir / "belief_store"
    store.mkdir(parents=True)
    (store / "epistemic_value.jsonl").write_text(
        json.dumps({"generation": 1, "epistemic_value": 1.0}) + "\n", encoding="utf-8"
    )
    (store / "contradictions.json").write_text("[]\n", encoding="utf-8")
    (store / "beliefs.json").write_text("[]\n", encoding="utf-8")
    checks = {c.name: c for c in validate_g2_artifacts(run_dir)}
    assert checks["belief_store"].ok
    assert checks["epistemic_value_jsonl"].ok
    # empty JSON arrays are size>2? "[]\n" is 3 bytes — has_cabs true; bias may fail
    assert "scoped_mutation_bias" in checks


def test_write_gate2_report(tmp_path: Path) -> None:
    from run_g2_smoke import PreflightReport, CheckResult

    report = PreflightReport(
        timestamp="2026-08-05T20:00:00Z",
        mode="preflight",
        run_id=1850,
        ready_for_dry_run=True,
        ready_for_live=False,
        command=["sia", "run", "--dry-run"],
        blockers=["anthropic_key: missing"],
    )
    report.checks.append(CheckResult("anthropic_key", False, "missing"))
    out = tmp_path / "gate2_report.md"
    write_gate2_report(report, out)
    text = out.read_text(encoding="utf-8")
    assert "Gate 2 report" in text
    assert "ready_for_live" not in text.lower() or "Ready for live G2" in text
    assert out.with_suffix(".json").is_file()
