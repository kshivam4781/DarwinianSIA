"""Tests for scripts/run_icml_live_pipeline.py (Tick 29 G2→G3→G4 orchestrator)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from run_icml_live_pipeline import (  # noqa: E402
    bump_spent,
    g3_pilot_promising,
    project_budget,
    run_preflight_stack,
    write_pipeline_report,
    PipelineReport,
)


def test_project_budget_defaults_fit_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")
    monkeypatch.delenv("SIA_G2_ESTIMATE_USD", raising=False)
    monkeypatch.delenv("SIA_G3_PAIR_ESTIMATE_USD", raising=False)
    monkeypatch.delenv("SIA_G4_PAIR_ESTIMATE_USD", raising=False)
    bud = project_budget(g3_pairs=1, g4_pairs=5)
    assert bud["stack_estimate"] == pytest.approx(1.0 + 4.0 + 15.0)
    assert bud["ok"] is True
    assert bud["projected"] == pytest.approx(20.0)


def test_project_budget_blocks_when_over(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "5")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")
    bud = project_budget(g3_pairs=1, g4_pairs=5)
    assert bud["ok"] is False
    assert bud["projected"] == pytest.approx(25.0)


def test_bump_spent_updates_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "1.5")
    new = bump_spent(2.0)
    assert new == pytest.approx(3.5)
    assert float(__import__("os").environ["SIA_BUDGET_SPENT_USD"]) == pytest.approx(3.5)


def test_g3_pilot_promising_on_d_win() -> None:
    assert g3_pilot_promising({"d_wins_gens30": 1, "n_pairs": 1}, {}) is True
    assert g3_pilot_promising({"d_wins_final": 0, "d_wins_gens30": 0}, {}) is False
    assert g3_pilot_promising(
        {"d_wins_final": 0},
        {"run_1301": {"spearman_rho": 0.55}},
    ) is True
    assert g3_pilot_promising(
        {"mean_final_b": 0.2, "mean_final_d": 0.25},
        {},
    ) is True


def test_preflight_stack_not_ready_without_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")

    import run_icml_live_pipeline as pipe
    import run_g2_smoke as g2
    import run_g3_pilot as g3
    import run_g4_multiseed as g4
    from prepare_gpqa_smoke_data import prepare_task_tree

    docs = tmp_path / "docs"
    docs.mkdir()
    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    task.mkdir(parents=True)
    prepare_task_tree(task, n=5)

    # Point all modules at tmp repo layout.
    for mod in (pipe, g2, g3, g4):
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    monkeypatch.setattr(g2, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(g2, "_run_dir_for", lambda rid: None)
    monkeypatch.setattr(g3, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(g3, "_run_dir_for", lambda rid: None)
    monkeypatch.setattr(g4, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(g4, "_run_dir_for", lambda rid: None)

    # Avoid rewriting real docs; gate writers use REPO_ROOT/docs/...
    report = PipelineReport(
        timestamp="2026-08-06T06:00:00Z",
        mode="preflight",
        budget=project_budget(),
    )
    run_preflight_stack(
        report,
        g2_run_id=1300,
        g3_seeds="1",
        g3_b="1201",
        g3_d="1301",
        g4_seeds="1,2,3,4,5",
        g4_b="1211,1212,1213,1214,1215",
        g4_d="1311,1312,1313,1314,1315",
    )
    assert report.ready_for_live is False
    assert any("anthropic" in b.lower() or "ANTHROPIC" in b for b in report.blockers)
    assert (tmp_path / "docs" / "gate2_report.md").is_file()
    assert (tmp_path / "docs" / "gate3_report.md").is_file()
    assert (tmp_path / "docs" / "gate4_report.md").is_file()


def test_write_pipeline_report(tmp_path: Path) -> None:
    report = PipelineReport(
        timestamp="2026-08-06T06:00:00Z",
        mode="preflight",
        budget=project_budget(),
        ready_for_live=False,
        blockers=["G2: anthropic_key: missing"],
        notes=["test"],
    )
    from run_icml_live_pipeline import StageResult

    report.add_stage(
        StageResult(name="G2", attempted=True, exit_code=0, ok=True, detail="preflight")
    )
    path = tmp_path / "icml_live_pipeline_report.md"
    write_pipeline_report(report, path)
    text = path.read_text(encoding="utf-8")
    assert "G2 → G3 → G4" in text
    assert "anthropic_key" in text
    sidecar = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    assert sidecar["ready_for_live"] is False
    assert sidecar["stages"][0]["name"] == "G2"


def test_live_refuses_over_budget(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "10")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")
    import run_icml_live_pipeline as pipe

    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    (tmp_path / "docs").mkdir()
    # Avoid calling real gate mains
    called: list[str] = []

    def boom(*_a, **_k):
        called.append("g2")
        return 0

    monkeypatch.setattr(pipe.g2, "main", boom)
    rc = pipe.main(["--live", "--report", str(tmp_path / "docs" / "pipe.md")])
    assert rc == 3
    assert called == []  # refused before G2
    text = (tmp_path / "docs" / "pipe.md").read_text(encoding="utf-8")
    assert "within ceiling | NO" in text or "exceeds ceiling" in text.lower() or "projected" in text
