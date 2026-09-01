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
from icml_env_checks import icml_g3g4_live_shape  # noqa: E402


def _seed_recipe_lock_docs(docs: Path, *, stale: bool = False) -> dict[str, int]:
    """Write Section 21.7 + pipeline note + gate3/4 JSON for Tick 299–300.

    Gate JSON are normally produced by G3/G4 preflight; ``--live`` refuses
    before those writers run, so tmp-repo live tests must seed them too.
    Tick 300 also seeds offline Bvd summary + gate3 offline table shape.
    """
    docs.mkdir(parents=True, exist_ok=True)
    shape = icml_g3g4_live_shape()
    if stale:
        # Tick 297 failure mode: collapsed pop3 recipe still advertised.
        flags = {
            "population_size": 3,
            "elite_count": 2,
            "max_gen": 4,
            "eval_subset": 10,
        }
    else:
        flags = dict(shape)
    b_line = (
        "sia run --task gpqa --darwinian "
        f"--population_size {flags['population_size']} "
        f"--elite_count {flags['elite_count']} "
        f"--max_gen {flags['max_gen']} --run_id 1201 "
        f"--eval_subset {flags['eval_subset']} --no-web --seed 1"
    )
    d_line = (
        "sia run --task gpqa --darwinian "
        f"--population_size {flags['population_size']} "
        f"--elite_count {flags['elite_count']} "
        f"--max_gen {flags['max_gen']} --run_id 1301 "
        f"--eval_subset {flags['eval_subset']} --no-web --seed 1 "
        "--cabs --cabs-inline"
    )
    (docs / "HACKATHON_MASTER_PLAN.md").write_text(
        "### 21.7 Suggested cheap GPQA commands (after keys + budget check)\n\n"
        f"{b_line}\n\n"
        f"{d_line}\n\n"
        "### 21.8 Artifact paths\n",
        encoding="utf-8",
    )
    (docs / "icml_live_pipeline_report.md").write_text(
        "Tick 296 G3/G4 shape: "
        f"eval_subset={flags['eval_subset']} pop={flags['population_size']} "
        f"elite={flags['elite_count']} max_gen={flags['max_gen']}\n",
        encoding="utf-8",
    )
    cmd = [
        "python",
        "-m",
        "sia",
        "run",
        "--task",
        "gpqa",
        "--darwinian",
        "--population_size",
        str(flags["population_size"]),
        "--elite_count",
        str(flags["elite_count"]),
        "--max_gen",
        str(flags["max_gen"]),
        "--run_id",
        "1201",
        "--eval_subset",
        str(flags["eval_subset"]),
        "--no-web",
        "--seed",
        "1",
    ]
    for name in ("gate3_report.json", "gate4_report.json"):
        (docs / name).write_text(
            json.dumps({"commands": [cmd, cmd]}, indent=2) + "\n",
            encoding="utf-8",
        )
    # Tick 300: offline Bvd live-shape lock fixtures.
    (docs / "offline_bvd_summary.json").write_text(
        json.dumps({"shape": dict(flags), "seeds": [11]}, indent=2) + "\n",
        encoding="utf-8",
    )
    (docs / "gate3_report.md").write_text(
        "<!-- OFFLINE_G3_PILOT_START -->\n"
        "## Offline synthetic pilot\n\n"
        "| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Run IDs |\n"
        "|------|-------|-----|-------|---------|-------------|---------|"
        f"\n| B | 11 | {flags['population_size']} | {flags['elite_count']} | "
        f"{flags['max_gen']} | {flags['eval_subset']} | `1890` |\n"
        f"| D | 11 | {flags['population_size']} | {flags['elite_count']} | "
        f"{flags['max_gen']} | {flags['eval_subset']} | `1900` |\n"
        "<!-- OFFLINE_G3_PILOT_END -->\n",
        encoding="utf-8",
    )
    return flags



def test_project_budget_defaults_fit_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")
    monkeypatch.delenv("SIA_G2_ESTIMATE_USD", raising=False)
    monkeypatch.delenv("SIA_G3_PAIR_ESTIMATE_USD", raising=False)
    monkeypatch.delenv("SIA_G4_PAIR_ESTIMATE_USD", raising=False)
    monkeypatch.delenv("ICML_META_AGENT_PROFILE", raising=False)
    monkeypatch.delenv("SIA_META_AGENT_PROFILE", raising=False)
    bud = project_budget(g3_pairs=1, g4_pairs=5)
    # Tick 293: Nebius defaults G2+$2 + G3+$3 + G4+$2.8×5 = $19
    assert bud["stack_estimate"] == pytest.approx(2.0 + 3.0 + 14.0)
    assert bud["ok"] is True
    assert bud["projected"] == pytest.approx(19.0)


def test_project_budget_blocks_when_over(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "5")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")
    monkeypatch.delenv("SIA_G2_ESTIMATE_USD", raising=False)
    monkeypatch.delenv("SIA_G3_PAIR_ESTIMATE_USD", raising=False)
    monkeypatch.delenv("SIA_G4_PAIR_ESTIMATE_USD", raising=False)
    monkeypatch.delenv("ICML_META_AGENT_PROFILE", raising=False)
    monkeypatch.delenv("SIA_META_AGENT_PROFILE", raising=False)
    bud = project_budget(g3_pairs=1, g4_pairs=5)
    # Tick 293 Nebius: spent 5 + stack 19 = 24
    assert bud["ok"] is False
    assert bud["projected"] == pytest.approx(24.0)


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
    monkeypatch.delenv("SIA_G2_ESTIMATE_USD", raising=False)
    monkeypatch.delenv("SIA_G3_PAIR_ESTIMATE_USD", raising=False)
    monkeypatch.delenv("SIA_G4_PAIR_ESTIMATE_USD", raising=False)
    monkeypatch.delenv("ICML_META_AGENT_PROFILE", raising=False)
    monkeypatch.delenv("SIA_META_AGENT_PROFILE", raising=False)
    bud = project_budget(g3_pairs=1, g4_pairs=5, skip_g2=True)
    assert bud["g2_estimate"] == pytest.approx(0.0)
    # Tick 293 Nebius: G3+$3 + G4+$14
    assert bud["stack_estimate"] == pytest.approx(3.0 + 14.0)
    assert bud["projected"] == pytest.approx(0.8 + 17.0)
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
    _seed_recipe_lock_docs(docs)
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


def test_ledger_stage_complete_requires_matching_run_ids(tmp_path: Path) -> None:
    """Tick 285: ledger skip only when stage + all required run IDs match."""
    from icml_env_checks import ledger_stage_complete, write_budget_spent_ledger

    path = tmp_path / "docs" / "icml_budget_spent.json"
    write_budget_spent_ledger(
        spent_usd=0.9,
        stages_complete=["G2"],
        run_ids=[1300],
        detail="unit",
        path=path,
    )
    assert ledger_stage_complete("G2", [1300], path=path) is True
    assert ledger_stage_complete("G2", [1301], path=path) is False
    assert ledger_stage_complete("G3", [1201, 1301], path=path) is False


def test_live_skips_g2_from_committed_ledger_without_run_dirs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 285: cross-VM resume — ledger committed, runs/ absent → skip G2."""
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("NEBIUS_API_KEY", "nb-test")
    monkeypatch.setenv("HF_TOKEN", "hf-test")

    import run_icml_live_pipeline as pipe
    from icml_env_checks import write_budget_spent_ledger

    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ICML_PROGRESS.md").write_text(
        "## 2026-08-31 — Tick 285 (test)\n", encoding="utf-8"
    )
    _seed_recipe_lock_docs(docs)
    # Prior tick committed ledger; this VM has no runs/ artifacts.
    write_budget_spent_ledger(
        spent_usd=0.85,
        stages_complete=["G2"],
        detail="prior tick G2",
        run_ids=[1300],
        path=docs / "icml_budget_spent.json",
    )
    monkeypatch.setattr(pipe.g2, "_run_dir_for", lambda _rid: None)
    monkeypatch.setattr(pipe.g3, "_run_dir_for", lambda _rid: None)
    monkeypatch.setattr(pipe.g4, "_run_dir_for", lambda _rid: None)

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
    monkeypatch.setattr(
        pipe,
        "_load_gate3_sidecar",
        lambda _p: ({"d_wins_gens30": 1}, {"run_1301": {"spearman_rho": 0.5}}),
    )
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
    assert float(os.environ["SIA_BUDGET_SPENT_USD"]) >= 0.85
    text = (docs / "pipe.md").read_text(encoding="utf-8")
    assert "ledger" in text.lower() or "skipped G2" in text or "already complete" in text
    ledger = json.loads((docs / "icml_budget_spent.json").read_text())
    # G2 spend preserved from ledger; G3 bump may add estimate after live G3.
    assert ledger["spent_usd"] >= 0.85
    assert "G2" in ledger["stages_complete"]
    assert "G3" in ledger["stages_complete"]


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
    # Tick 291: default Nebius meta overhead is 3.0 → 0.40 × 3.0 = 1.20
    import run_icml_live_pipeline as pipe

    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    (tmp_path / "docs").mkdir(exist_ok=True)
    monkeypatch.setattr(pipe, "_resolve_run_dirs", lambda _ids: [run])
    bumped, detail2 = bump_spent_reconciled([1300], fallback_estimate=1.0, stage="G2")
    assert bumped == pytest.approx(1.20)
    assert float(os.environ["SIA_BUDGET_SPENT_USD"]) == pytest.approx(1.20)
    assert "actual_target" in detail2
    assert (tmp_path / "docs" / "icml_budget_spent.json").is_file()


def test_sum_run_dirs_cost_estimates_usd_from_tokens_when_usd_zero(tmp_path: Path) -> None:
    """Tick 291: zero total_cost_usd + tokens → Nebius Kimi rate estimate."""
    from icml_env_checks import (
        NEBIUS_KIMI_USD_PER_MILLION,
        estimate_usd_from_tokens,
        reconcile_gate_spend_usd,
        sum_run_dirs_cost_usd,
    )

    run = tmp_path / "run_tokens"
    agent = run / "gen_1" / "agent_0"
    agent.mkdir(parents=True)
    payload = {
        "accuracy": 0.2,
        "total_cost_usd": 0.0,
        "total_input_tokens": 1_000_000,
        "total_output_tokens": 500_000,
        "total_reasoning_tokens": 0,
    }
    (agent / "results.json").write_text(json.dumps(payload), encoding="utf-8")
    expected = (
        (1_000_000 / 1e6) * NEBIUS_KIMI_USD_PER_MILLION["input"]
        + (500_000 / 1e6) * NEBIUS_KIMI_USD_PER_MILLION["output"]
    )
    assert estimate_usd_from_tokens(payload) == pytest.approx(expected)
    assert sum_run_dirs_cost_usd([run]) == pytest.approx(expected)
    amount, detail = reconcile_gate_spend_usd([run], fallback_estimate=9.0, meta_overhead=2.0)
    assert amount == pytest.approx(expected * 2.0)
    assert "actual_target" in detail
    assert "estimate was $9" in detail


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


def test_sum_run_dirs_cost_reads_submission_when_results_accuracy_only(
    tmp_path: Path,
) -> None:
    """Tick 290: pre-merge accuracy-only results.json still meters via submission.json."""
    from icml_env_checks import reconcile_gate_spend_usd, sum_run_dirs_cost_usd

    run = tmp_path / "run_legacy"
    agent = run / "gen_1" / "agent_0"
    results_dir = agent / "results"
    results_dir.mkdir(parents=True)
    (agent / "results.json").write_text(
        json.dumps({"accuracy": 0.2, "n_correct": 1, "n_total": 5, "eval_subset": 5}),
        encoding="utf-8",
    )
    (results_dir / "submission.json").write_text(
        json.dumps(
            {
                "total_cost_usd": 0.32,
                "total_input_tokens": 900,
                "total_output_tokens": 40,
                "details": [{"question_id": 0, "model_answer": "A", "cost_usd": 0.32}],
            }
        ),
        encoding="utf-8",
    )
    assert sum_run_dirs_cost_usd([run]) == pytest.approx(0.32)
    amount, detail = reconcile_gate_spend_usd([run], fallback_estimate=1.0, meta_overhead=1.25)
    assert amount == pytest.approx(0.40)
    assert "actual_target" in detail


def test_run_preflight_stack_default_diamond_n_is_budget_fit() -> None:
    """Tick 283/293/296: preflight stack default matches G3/G4 eval_subset (Nebius→5)."""
    import inspect

    from icml_env_checks import icml_diamond_n_for_stack
    from run_icml_live_pipeline import run_preflight_stack

    default = inspect.signature(run_preflight_stack).parameters["diamond_n"].default
    assert default is None
    assert icml_diamond_n_for_stack() == 5


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
    _seed_recipe_lock_docs(docs)
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
    # Tick 289: default Nebius meta → Anthropic optional; NEBIUS still required.
    assert any("nebius" in b.lower() or "NEBIUS" in b for b in report.blockers)
    # Tick 299: matching recipe lock should not add recipe blockers.
    assert not any(b.startswith("recipes:") for b in report.blockers)
    assert any("Tick 299: committed G3/G4 recipes match" in n for n in report.notes)
    # Tick 300: offline Bvd live-shape lock green when fixtures match.
    assert not any(b.startswith("offline_bvd:") for b in report.blockers)
    assert any("Tick 300: offline Bvd summary matches" in n for n in report.notes)
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
    _seed_recipe_lock_docs(docs)

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


def test_live_refuses_stale_g3g4_recipes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 299: --live refuses when Section 21.7 / pipeline note lag live shape."""
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")
    monkeypatch.setenv("NEBIUS_API_KEY", "nb-test")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)

    import run_icml_live_pipeline as pipe

    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ICML_PROGRESS.md").write_text(
        "## 2026-09-01T10:00Z — Tick 299 (test)\n", encoding="utf-8"
    )
    (docs / "ICML_READY.md").write_text("**STATUS: IN_PROGRESS**\n", encoding="utf-8")
    # Stale pop3 recipes (Tick 297 failure mode) while code wants pop4×eval5×max_gen6.
    # Helper also writes matching-shape? No — stale=True writes stale gate JSON too,
    # which is enough for --live refuse before G3/G4 writers run.
    _seed_recipe_lock_docs(docs, stale=True)

    called: list[str] = []

    def boom(*_a, **_k):
        called.append("g2")
        return 0

    monkeypatch.setattr(pipe.g2, "main", boom)
    rc = pipe.main(["--live", "--report", str(docs / "pipe.md")])
    assert rc == 3
    assert called == []
    text = (docs / "pipe.md").read_text(encoding="utf-8")
    assert "recipes" in text.lower() or "stale" in text.lower()
    assert "21.7" in text or "shape" in text.lower()


def test_preflight_stack_blocks_stale_recipes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 299: preflight clears ready_for_live when committed recipes drift."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")

    import run_icml_live_pipeline as pipe
    import run_g2_smoke as g2
    import run_g3_pilot as g3
    import run_g4_multiseed as g4
    from prepare_gpqa_smoke_data import prepare_task_tree

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ICML_PROGRESS.md").write_text(
        "## 2026-09-01T10:00Z — Tick 299 (test)\n", encoding="utf-8"
    )
    _seed_recipe_lock_docs(docs, stale=True)

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

    report = PipelineReport(
        timestamp="2026-09-01T10:00:00Z",
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
    assert any(b.startswith("recipes:") for b in report.blockers)
    assert any("Tick 299: refuse live" in n for n in report.notes)


def test_preflight_stack_blocks_stale_offline_bvd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 300: preflight clears ready_for_live when offline Bvd shape drifts."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")

    import run_icml_live_pipeline as pipe
    import run_g2_smoke as g2
    import run_g3_pilot as g3
    import run_g4_multiseed as g4
    from prepare_gpqa_smoke_data import prepare_task_tree

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ICML_PROGRESS.md").write_text(
        "## 2026-09-01T12:00Z — Tick 300 (test)\n", encoding="utf-8"
    )
    # Matching recipes, but stale eval=3 offline summary (Tick 23 artifact era).
    _seed_recipe_lock_docs(docs, stale=False)
    (docs / "offline_bvd_summary.json").write_text(
        json.dumps(
            {
                "shape": {
                    "eval_subset": 3,
                    "population_size": 4,
                    "elite_count": 2,
                    "max_gen": 6,
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

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

    report = PipelineReport(
        timestamp="2026-09-01T12:00:00Z",
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
    assert any(b.startswith("offline_bvd:") for b in report.blockers)
    assert any("Tick 300: refuse live" in n for n in report.notes)
