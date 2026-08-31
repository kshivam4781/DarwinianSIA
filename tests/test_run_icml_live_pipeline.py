"""Tests for scripts/run_icml_live_pipeline.py (Tick 29 G2→G3→G4 orchestrator)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from run_icml_live_pipeline import (  # noqa: E402
    bump_spent,
    bump_spent_reconciled,
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


def test_bump_spent_updates_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "1.5")
    import run_icml_live_pipeline as pipe

    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    (tmp_path / "docs").mkdir()
    new = bump_spent(2.0, stage="G2", run_ids=[1300], detail="test bump")
    assert new == pytest.approx(3.5)
    assert float(os.environ["SIA_BUDGET_SPENT_USD"]) == pytest.approx(3.5)
    ledger = json.loads((tmp_path / "docs" / "icml_budget_spent.json").read_text())
    assert ledger["spent_usd"] == pytest.approx(3.5)
    assert "G2" in ledger["stages_complete"]


def test_darwinian_run_complete_and_ledger_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tick 284: complete detection + ledger reload into env."""
    from icml_env_checks import (
        apply_persisted_spent_to_env,
        darwinian_run_complete,
        write_budget_spent_ledger,
    )

    empty = tmp_path / "run_empty"
    empty.mkdir()
    assert darwinian_run_complete(empty) is False
    assert darwinian_run_complete(None) is False

    run = tmp_path / "run_1300"
    agent = run / "gen_1" / "agent_0"
    agent.mkdir(parents=True)
    (agent / "results.json").write_text(
        json.dumps({"accuracy": 0.2, "total_cost_usd": 0.4}),
        encoding="utf-8",
    )
    assert darwinian_run_complete(run) is True

    ledger_path = tmp_path / "docs" / "icml_budget_spent.json"
    write_budget_spent_ledger(
        spent_usd=1.25,
        stages_complete=["G2"],
        detail="unit",
        run_ids=[1300],
        path=ledger_path,
    )
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    spent, detail = apply_persisted_spent_to_env(path=ledger_path)
    assert spent == pytest.approx(1.25)
    assert "ledger=" in detail
    assert float(os.environ["SIA_BUDGET_SPENT_USD"]) == pytest.approx(1.25)


def test_project_budget_skips_completed_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tick 284: resume projection excludes finished gates."""
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0.8")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")
    bud = project_budget(g3_pairs=1, g4_pairs=5, skip_g2=True)
    assert bud["g2_estimate"] == pytest.approx(0.0)
    assert bud["stack_estimate"] == pytest.approx(4.0 + 15.0)
    assert bud["projected"] == pytest.approx(0.8 + 19.0)
    assert bud["ok"] is True


def test_live_skips_completed_g2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 284: mid-stack resume skips G2 when run_1300 already complete."""
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("NEBIUS_API_KEY", "nb-test")
    monkeypatch.setenv("HF_TOKEN", "hf-test")

    import run_icml_live_pipeline as pipe

    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ICML_PROGRESS.md").write_text(
        "## 2026-08-31 — Tick 284 (test)\n", encoding="utf-8"
    )
    # Completed G2 artifacts under SIA/runs (resolver order).
    run = tmp_path / "SIA" / "runs" / "run_1300"
    agent = run / "gen_1" / "agent_0"
    agent.mkdir(parents=True)
    (agent / "results.json").write_text(
        json.dumps({"accuracy": 0.15, "total_cost_usd": 0.32}),
        encoding="utf-8",
    )
    # Point g2/g3 resolvers at tmp_path layout.
    monkeypatch.setattr(pipe.g2, "_run_dir_for", lambda rid: (tmp_path / "SIA" / "runs" / f"run_{rid}") if (tmp_path / "SIA" / "runs" / f"run_{rid}").exists() else None)
    monkeypatch.setattr(pipe.g3, "_run_dir_for", lambda rid: (tmp_path / "SIA" / "runs" / f"run_{rid}") if (tmp_path / "SIA" / "runs" / f"run_{rid}").exists() else None)
    monkeypatch.setattr(pipe.g4, "_run_dir_for", lambda rid: (tmp_path / "SIA" / "runs" / f"run_{rid}") if (tmp_path / "SIA" / "runs" / f"run_{rid}").exists() else None)

    called: list[str] = []

    def g2_boom(*_a, **_k):
        called.append("g2")
        return 0

    def g3_ok(*_a, **_k):
        called.append("g3")
        return 0

    monkeypatch.setattr(pipe.g2, "main", g2_boom)
    monkeypatch.setattr(pipe.g3, "main", g3_ok)
    monkeypatch.setattr(pipe, "_fetch_diamond", lambda **_k: ["fetched"])
    # Make G3 look promising without real sidecar.
    monkeypatch.setattr(
        pipe,
        "_load_gate3_sidecar",
        lambda _p: ({"d_wins_gens30": 1}, {"run_1301": {"spearman_rho": 0.5}}),
    )
    # Stop after G3 so we don't need G4.
    rc = pipe.main(
        [
            "--live",
            "--fetch-diamond",
            "--stop-after",
            "g3",
            "--report",
            str(docs / "pipe.md"),
        ]
    )
    assert rc == 0
    assert "g2" not in called
    assert "g3" in called
    text = (docs / "pipe.md").read_text(encoding="utf-8")
    assert "resume" in text.lower() or "skipped G2" in text or "already complete" in text
    ledger = json.loads((docs / "icml_budget_spent.json").read_text())
    assert ledger["spent_usd"] > 0
    assert "G2" in ledger["stages_complete"]


def test_reconcile_gate_spend_prefers_actual_usd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tick 283: actual total_cost_usd × overhead beats blind estimate."""
    from icml_env_checks import reconcile_gate_spend_usd, sum_run_dirs_cost_usd
    from run_icml_live_pipeline import bump_spent_reconciled

    run = tmp_path / "run_1300"
    agent = run / "gen_1" / "agent_0"
    agent.mkdir(parents=True)
    (agent / "results.json").write_text(
        json.dumps({"accuracy": 0.2, "total_cost_usd": 0.40}),
        encoding="utf-8",
    )
    assert sum_run_dirs_cost_usd([run]) == pytest.approx(0.40)
    amount, detail = reconcile_gate_spend_usd([run], fallback_estimate=1.0, meta_overhead=1.25)
    assert amount == pytest.approx(0.50)
    assert "actual_target" in detail

    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    # Patch resolver to use tmp run id mapping via creating under expected path is hard;
    # call reconcile helper path through bump with monkeypatched _resolve_run_dirs.
    import run_icml_live_pipeline as pipe

    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    (tmp_path / "docs").mkdir(exist_ok=True)
    monkeypatch.setattr(pipe, "_resolve_run_dirs", lambda _ids: [run])
    bumped, detail2 = bump_spent_reconciled([1300], fallback_estimate=1.0, stage="G2")
    assert bumped == pytest.approx(0.50)
    assert float(os.environ["SIA_BUDGET_SPENT_USD"]) == pytest.approx(0.50)
    assert "actual_target" in detail2
    assert (tmp_path / "docs" / "icml_budget_spent.json").is_file()


def test_reconcile_gate_spend_falls_back_to_estimate(tmp_path: Path) -> None:
    from icml_env_checks import reconcile_gate_spend_usd

    run = tmp_path / "run_empty"
    (run / "gen_1" / "agent_0").mkdir(parents=True)
    (run / "gen_1" / "agent_0" / "results.json").write_text(
        json.dumps({"accuracy": 0.1, "eval_subset": 5}),
        encoding="utf-8",
    )
    amount, detail = reconcile_gate_spend_usd([run], fallback_estimate=4.0)
    assert amount == pytest.approx(4.0)
    assert "estimate" in detail


def test_run_preflight_stack_default_diamond_n_is_15() -> None:
    """Tick 283: preflight stack default matches G3/G4 eval_subset=15."""
    import inspect

    from run_icml_live_pipeline import run_preflight_stack

    default = inspect.signature(run_preflight_stack).parameters["diamond_n"].default
    assert default == 15


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


def test_preflight_stack_fetch_diamond_surfaces_hf_in_gates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 276: --fetch-diamond preflight requires HF in gate2/3/4 + aggregate."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")

    import run_icml_live_pipeline as pipe
    import run_g2_smoke as g2
    import run_g3_pilot as g3
    import run_g4_multiseed as g4
    from prepare_gpqa_smoke_data import prepare_task_tree

    docs = tmp_path / "docs"
    docs.mkdir()
    # Minimal tip/progress so tip lineage does not dominate blockers.
    (docs / "ICML_PROGRESS.md").write_text(
        "## 2026-08-30T12:00Z — Tick 276 (test)\n", encoding="utf-8"
    )
    (docs / "ICML_READY.md").write_text("**STATUS: IN_PROGRESS**\n", encoding="utf-8")

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    task.mkdir(parents=True)
    prepare_task_tree(task, n=5)

    for mod in (pipe, g2, g3, g4):
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    monkeypatch.setattr(g2, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(g2, "_run_dir_for", lambda rid: None)
    monkeypatch.setattr(g3, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(g3, "_run_dir_for", lambda rid: None)
    monkeypatch.setattr(g4, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(g4, "_run_dir_for", lambda rid: None)

    # Avoid real HF calls during preflight materialize attempts.
    def _no_hf(*_a, **_k):
        raise RuntimeError("HF unavailable in unit test")

    monkeypatch.setattr(g2, "materialize_from_hf", _no_hf)
    monkeypatch.setattr(g3, "materialize_from_hf", _no_hf)
    monkeypatch.setattr(g4, "materialize_from_hf", _no_hf)

    report = PipelineReport(
        timestamp="2026-08-30T12:00:00Z",
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
        fetch_diamond=True,
    )
    assert report.ready_for_live is False
    # Aggregate pipeline blocker.
    assert any("HF_TOKEN" in b for b in report.blockers)
    # Individual gates must also require HF (require_hf_for_diamond).
    for name in ("gate2_report.json", "gate3_report.json", "gate4_report.json"):
        data = json.loads((tmp_path / "docs" / name).read_text(encoding="utf-8"))
        assert data.get("ready_for_live") is False
        blockers = " ".join(data.get("blockers") or [])
        assert "HF" in blockers.upper() or "hf_token" in blockers.lower()
    # Stage detail records fetch-diamond propagation.
    assert any("+fetch-diamond" in (s.detail or "") for s in report.stages)


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


def test_live_fetch_diamond_refuses_without_hf(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 274: --live --fetch-diamond refuses on API keys without HF_TOKEN."""
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("NEBIUS_API_KEY", "nb-test")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)

    import run_icml_live_pipeline as pipe

    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    # Tip OK so we reach the HF gate (not tip refuse).
    (docs / "ICML_PROGRESS.md").write_text(
        "## 2026-08-30 — Tick 274 (test)\n", encoding="utf-8"
    )
    called: list[str] = []

    def boom(*_a, **_k):
        called.append("g2")
        return 0

    monkeypatch.setattr(pipe.g2, "main", boom)
    # Avoid real diamond materialize.
    monkeypatch.setattr(
        pipe,
        "_fetch_diamond",
        lambda **_k: (_ for _ in ()).throw(AssertionError("must not fetch")),
    )
    rc = pipe.main(
        [
            "--live",
            "--fetch-diamond",
            "--report",
            str(docs / "pipe.md"),
        ]
    )
    assert rc == 4
    assert called == []
    text = (docs / "pipe.md").read_text(encoding="utf-8")
    assert "HF_TOKEN" in text or "fetch_diamond" in text.lower()
