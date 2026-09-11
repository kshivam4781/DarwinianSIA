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
    g2_resume_gates_ok,
    load_g2_post_for_g3,
    g3_pilot_promising,
    load_g3_metrics_for_g4,
    project_budget,
    refresh_g4_paper_pack_on_resume,
    run_preflight_stack,
    complete_run_ids_among,
    remaining_seed_pairs,
    sync_spent_from_completed_stages,
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
    # Tick 300–302: offline Bvd live-shape + paper-ID + figures lock fixtures.
    b_ids = [1890, 1891, 1892, 1893, 1894]
    d_ids = [1900, 1901, 1902, 1903, 1904]
    figs_dir = docs / "figures"
    figs_dir.mkdir(parents=True, exist_ok=True)
    fig1 = figs_dir / "fig1_learning_curves.png"
    fig2 = figs_dir / "fig2_mechanism.png"
    # Tick 302 lock requires real-looking files (≥1000 bytes).
    fig1.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 1200)
    fig2.write_bytes(b"\x89PNG\r\n\x1a\n" + b"1" * 1200)
    fig_paths = [
        "docs/figures/fig1_learning_curves.png",
        "docs/figures/fig2_mechanism.png",
    ]
    (docs / "offline_bvd_summary.json").write_text(
        json.dumps(
            {
                "shape": dict(flags),
                "seeds": [11, 22, 33, 44, 55],
                "b_run_ids": b_ids,
                "d_run_ids": d_ids,
                "figures": fig_paths,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "gate3_report.md").write_text(
        "<!-- OFFLINE_G3_PILOT_START -->\n"
        "## Offline synthetic pilot\n\n"
        "| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Run IDs |\n"
        "|------|-------|-----|-------|---------|-------------|---------|"
        f"\n| B | 11 | {flags['population_size']} | {flags['elite_count']} | "
        f"{flags['max_gen']} | {flags['eval_subset']} | `1890–1894` |\n"
        f"| D | 11 | {flags['population_size']} | {flags['elite_count']} | "
        f"{flags['max_gen']} | {flags['eval_subset']} | `1900–1904` |\n"
        "<!-- OFFLINE_G3_PILOT_END -->\n",
        encoding="utf-8",
    )
    (docs / "case_study_offline.md").write_text(
        f"**Run:** `runs/run_{d_ids[0]}`\n",
        encoding="utf-8",
    )
    (docs / "paper_artifacts.md").write_text(
        f"Offline pilot `1890–1894` / `1900–1904`\n\n"
        "## Case study (offline)\n\n"
        f"Lift +0.0436 (`run_{d_ids[0]}`, Tick 300).\n\n"
        "| Fig | Path |\n"
        "|-----|------|\n"
        "| 1 | `docs/figures/fig1_learning_curves.png` |\n"
        "| 2 | `docs/figures/fig2_mechanism.png` |\n",
        encoding="utf-8",
    )
    (docs / "ICML_READY.md").write_text(
        "### 1. PRIMARY\n"
        "- Evidence: offline `1890–1894` vs `1900–1904`\n\n"
        "### 3. VALIDITY — H5\n"
        "- Evidence: offline D `1900–1904` → ρ>0.3 on 5/5\n",
        encoding="utf-8",
    )
    # Append Section 12 offline pilot row without wiping Section 21.7 recipes.
    master_path = docs / "HACKATHON_MASTER_PLAN.md"
    prior = master_path.read_text(encoding="utf-8") if master_path.is_file() else ""
    master_path.write_text(
        prior
        + "\n| Offline B vs D case-study pilot | **DONE** | "
        "Latest Tick 300 `1890–1894` / `1900–1904` |\n",
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
    # Tick 372/384: this fixture is accuracy-only; stub post-gates so the
    # resume-skip path under test is ledger/complete-run skip (not artifact depth).
    monkeypatch.setattr(pipe, "g2_resume_gates_ok", lambda _rid: (True, "stub ok"))
    monkeypatch.setattr(
        pipe, "load_g2_post_for_g3", lambda **_k: (True, "Tick 384: stub ok")
    )
    # Make G3 look promising without real sidecar.
    monkeypatch.setattr(
        pipe,
        "_load_gate3_sidecar",
        lambda _p: (
            {"d_wins_gens30": 1, "n_pairs": 1, "mean_final_gap": 0.05},
            {"run_1301": {"spearman_rho": 0.5}},
            {},
        ),
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
    # Tick 384: ledger-only G2→G3 requires trustable gate2 post evidence.
    (docs / "gate2_report.json").write_text(
        json.dumps(
            {
                "mode": "preflight",
                "run_id": 1300,
                "post": [],
                "prior_live_post": [
                    {"name": "belief_store", "ok": True, "detail": "present"},
                    {"name": "epistemic_value_jsonl", "ok": True, "detail": "present"},
                    {"name": "cabs_json", "ok": True, "detail": "ok"},
                    {"name": "scoped_mutation_bias", "ok": True, "detail": "ok"},
                    {
                        "name": "nonzero_fitness",
                        "ok": True,
                        "detail": "best=0.2000 > min=0",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate2_report.md").write_text("# Gate 2\n", encoding="utf-8")
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
        lambda _p: (
            {"d_wins_gens30": 1, "n_pairs": 1},
            {"run_1301": {"spearman_rho": 0.5}},
            {},
        ),
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
    assert "Tick 384" in text or "prior_live_post" in text or "post-gates ok" in text or "trusted gate2" in text
    ledger = json.loads((docs / "icml_budget_spent.json").read_text())
    # G2 spend preserved from ledger; stubbed G3 creates no local runs so
    # stages_complete may remain G2-only (Tick 376 sync needs artifacts).
    assert ledger["spent_usd"] >= 0.85
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
    # Tick 370: H5 alone must NOT auto-advance to paid G4 (PRIMARY required).
    assert g3_pilot_promising(
        {"d_wins_final": 0},
        {"run_1301": {"spearman_rho": 0.55}},
    ) is False
    assert g3_pilot_promising(
        {"mean_final_b": 0.2, "mean_final_d": 0.25},
        {},
    ) is True
    # Tick 360: mean_final_gap alone (emitted by compare_b_vs_d) is promising.
    assert g3_pilot_promising({"mean_final_gap": 0.05}, {}) is True
    assert g3_pilot_promising({"mean_final_gap": 0.005}, {}) is False
    # PRIMARY win still wins even if H5 is weak/missing.
    assert g3_pilot_promising(
        {"d_wins_cost30": 1},
        {"run_1301": {"spearman_rho": 0.0}},
    ) is True


def test_g2_resume_refuses_zero_fitness_local_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 372: 0%-fitness G2 still has results.json → must not resume-skip."""
    import run_icml_live_pipeline as pipe
    import run_g2_smoke as g2

    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(g2, "REPO_ROOT", tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {
                "spent_usd": 2.0,
                "stages_complete": ["G2"],
                "run_ids": [1300],
                "detail": "stale pre-Tick-372 ledger",
            }
        ),
        encoding="utf-8",
    )

    run_dir = tmp_path / "runs" / "run_1300"
    store = run_dir / "belief_store"
    store.mkdir(parents=True)
    (store / "epistemic_value.jsonl").write_text(
        json.dumps({"generation": 1, "epistemic_value": 1.0}) + "\n",
        encoding="utf-8",
    )
    (store / "contradictions.json").write_text(
        json.dumps([{"topic": "tool_strategy", "a": "selective", "b": "aggressive"}])
        + "\n",
        encoding="utf-8",
    )
    (store / "beliefs.json").write_text(
        json.dumps([{"topic": "tool_strategy", "claim": "selective"}]) + "\n",
        encoding="utf-8",
    )
    agent = run_dir / "gen_1" / "agent_0"
    agent.mkdir(parents=True)
    (agent / "results.json").write_text(
        json.dumps({"accuracy": 0.0}), encoding="utf-8"
    )

    monkeypatch.setattr(g2, "_run_dir_for", lambda rid: run_dir if rid == 1300 else None)
    monkeypatch.setattr(
        pipe, "_resolve_run_dirs", lambda ids: [run_dir] if 1300 in ids else []
    )

    ok, detail = g2_resume_gates_ok(1300)
    assert ok is False
    assert "nonzero_fitness" in detail

    resume = sync_spent_from_completed_stages(
        g2_run_id=1300,
        g3_b_ids=[1201],
        g3_d_ids=[1301],
        g4_b_ids=[1211, 1212, 1213, 1214, 1215],
        g4_d_ids=[1311, 1312, 1313, 1314, 1315],
    )
    assert resume["g2_local"] is True
    assert resume["g2_gates_failed"] is True
    assert resume["g2_done"] is False
    assert any("Tick 372" in d for d in resume["details"])


def _mk_complete_run(root: Path, run_id: int, *, cost_usd: float = 0.5) -> Path:
    run_dir = root / "runs" / f"run_{run_id}"
    agent = run_dir / "gen_1" / "agent_0"
    agent.mkdir(parents=True, exist_ok=True)
    (agent / "results.json").write_text(
        json.dumps({"accuracy": 0.2, "total_cost_usd": cost_usd}),
        encoding="utf-8",
    )
    return run_dir


def test_sync_spent_bills_partial_g4_pairs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 376: mid-stack complete G4 pairs count toward spent without g4_done."""
    import run_icml_live_pipeline as pipe
    import run_g2_smoke as g2

    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("SIA_BUDGET_SPENT_USD", raising=False)
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

    # G2 complete + gates ok
    g2_dir = _mk_complete_run(tmp_path, 1300, cost_usd=0.4)
    store = g2_dir / "belief_store"
    store.mkdir(parents=True)
    (store / "epistemic_value.jsonl").write_text(
        json.dumps({"generation": 1, "epistemic_value": 1.0}) + "\n",
        encoding="utf-8",
    )
    (store / "contradictions.json").write_text(
        json.dumps([{"topic": "tool_strategy", "a": "selective", "b": "aggressive"}])
        + "\n",
        encoding="utf-8",
    )
    (store / "beliefs.json").write_text(
        json.dumps([{"topic": "tool_strategy", "claim": "selective"}]) + "\n",
        encoding="utf-8",
    )

    # Only first of 5 G4 pairs complete (2 runs)
    b1 = _mk_complete_run(tmp_path, 1211, cost_usd=0.3)
    d1 = _mk_complete_run(tmp_path, 1311, cost_usd=0.3)

    def _run_dir(rid: int):
        mapping = {
            1300: g2_dir,
            1211: b1,
            1311: d1,
        }
        return mapping.get(rid)

    monkeypatch.setattr(g2, "_run_dir_for", _run_dir)
    monkeypatch.setattr(pipe.g3, "_run_dir_for", _run_dir)
    monkeypatch.setattr(
        pipe,
        "_resolve_run_dirs",
        lambda ids: [p for rid in ids if (p := _run_dir(rid)) is not None],
    )
    # Keep G2 gates from failing on missing extras — stub ok.
    monkeypatch.setattr(pipe, "g2_resume_gates_ok", lambda rid: (True, "ok"))

    resume = sync_spent_from_completed_stages(
        g2_run_id=1300,
        g3_b_ids=[1201],
        g3_d_ids=[1301],
        g4_b_ids=[1211, 1212, 1213, 1214, 1215],
        g4_d_ids=[1311, 1312, 1313, 1314, 1315],
    )
    assert resume["g2_done"] is True
    assert resume["g3_done"] is False
    assert resume["g4_done"] is False
    assert any("Tick 376 G4 partial" in d for d in resume["details"])
    assert float(resume["spent"]) > 2.0  # G2 + partial G4, not G2-only undercount
    # Stage G4 must not be marked complete
    ledger = json.loads((docs / "icml_budget_spent.json").read_text(encoding="utf-8"))
    assert "G4" not in (ledger.get("stages_complete") or [])
    assert 1211 in ledger.get("run_ids", [])
    assert 1311 in ledger.get("run_ids", [])


def test_remaining_seed_pairs_counts_incomplete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 376: remaining_seed_pairs ignores complete pairs."""
    import run_icml_live_pipeline as pipe

    b1 = _mk_complete_run(tmp_path, 1211)
    d1 = _mk_complete_run(tmp_path, 1311)

    def _run_dir(rid: int):
        return {1211: b1, 1311: d1}.get(rid)

    monkeypatch.setattr(pipe.g2, "_run_dir_for", _run_dir)
    monkeypatch.setattr(pipe.g3, "_run_dir_for", _run_dir)
    n = remaining_seed_pairs(
        [1211, 1212, 1213, 1214, 1215],
        [1311, 1312, 1313, 1314, 1315],
    )
    assert n == 4
    assert complete_run_ids_among([1211, 1212, 1311]) == [1211, 1311]


def test_project_budget_uses_remaining_pairs_after_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tick 376: stack projection bills remaining pairs only."""
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "8.0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20.0")
    # 2 of 5 G4 pairs remaining → ~$5.6 at $2.80/pair (Nebius default)
    bud = project_budget(
        g3_pairs=0,
        g4_pairs=2,
        skip_g2=True,
        skip_g3=True,
        skip_g4=False,
    )
    from icml_env_checks import default_g4_pair_estimate_usd

    assert bud["g4_pairs"] == 2
    assert bud["g4_estimate"] == pytest.approx(2 * float(default_g4_pair_estimate_usd()))
    assert bud["projected"] == pytest.approx(8.0 + bud["g4_estimate"])
    assert bud["projected"] < 20.0
    # Contrast: full 5 would be larger
    full = project_budget(
        g3_pairs=0,
        g4_pairs=5,
        skip_g2=True,
        skip_g3=True,
        skip_g4=False,
    )
    assert bud["g4_estimate"] < full["g4_estimate"]



def test_g3_resume_rescores_local_when_sidecar_preflight(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 373: resume-complete G3 + preflight sidecar → re-score local, not null."""
    import run_icml_live_pipeline as pipe
    import run_g3_pilot as g3

    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    # Preflight sidecar with null comparison (the mid-stack crash failure mode).
    (docs / "gate3_report.json").write_text(
        json.dumps(
            {
                "mode": "preflight",
                "executed": False,
                "comparison": None,
                "h5_by_d_run": {},
                "h2_by_d_run": {},
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate3_report.md").write_text("# Gate 3\n", encoding="utf-8")

    b_dir = tmp_path / "runs" / "run_1201"
    d_dir = tmp_path / "runs" / "run_1301"
    b_dir.mkdir(parents=True)
    d_dir.mkdir(parents=True)

    monkeypatch.setattr(pipe, "stage_runs_complete", lambda ids: set(ids) <= {1201, 1301})
    monkeypatch.setattr(
        pipe,
        "_resolve_run_dirs",
        lambda ids: [b_dir if i == 1201 else d_dir for i in ids],
    )

    fake_cmp = {
        "n_pairs": 1,
        "d_wins_gens30": 1,
        "d_wins_final": 1,
        "mean_final_gap": 0.05,
        "mean_final_b": 0.2,
        "mean_final_d": 0.25,
    }

    def _fake_score(b_dirs, d_dirs):
        assert b_dirs == [b_dir]
        assert d_dirs == [d_dir]
        return fake_cmp, {"run_1301": {"spearman_rho": 0.6}}, {"run_1301": {"preferred_share": 0.75}}

    monkeypatch.setattr(g3, "score_pilot", _fake_score)
    monkeypatch.setattr(
        g3,
        "g3_d_steering_ok",
        lambda d_dirs: (True, []),
    )

    comparison, h5, h2, src = load_g3_metrics_for_g4(
        g3_b_ids=[1201],
        g3_d_ids=[1301],
        report_md=docs / "gate3_report.md",
    )
    assert comparison == fake_cmp
    assert h5["run_1301"]["spearman_rho"] == 0.6
    assert h2["run_1301"]["preferred_share"] == 0.75
    assert "re-scored G3 from local" in src
    assert "steering ok" in src
    assert g3_pilot_promising(comparison, h5) is True


def test_load_g3_metrics_refuses_never_steer_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 407: local G3 D without gen≥3 agenda → refuse G4 metrics."""
    import run_icml_live_pipeline as pipe
    import run_g3_pilot as g3
    from run_g3_pilot import CheckResult

    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "gate3_report.md").write_text("# Gate 3\n", encoding="utf-8")
    b_dir = tmp_path / "runs" / "run_1201"
    d_dir = tmp_path / "runs" / "run_1301"
    b_dir.mkdir(parents=True)
    d_dir.mkdir(parents=True)

    monkeypatch.setattr(pipe, "stage_runs_complete", lambda ids: set(ids) <= {1201, 1301})
    monkeypatch.setattr(
        pipe,
        "_resolve_run_dirs",
        lambda ids: [b_dir if i == 1201 else d_dir for i in ids],
    )
    monkeypatch.setattr(
        g3,
        "score_pilot",
        lambda b_dirs, d_dirs: (
            {"n_pairs": 1, "d_wins_gens30": 1, "mean_final_gap": 0.05},
            {},
            {},
        ),
    )
    monkeypatch.setattr(
        g3,
        "g3_d_steering_ok",
        lambda d_dirs: (
            False,
            [
                CheckResult(
                    "steering_applied_gen3",
                    False,
                    "Condition D never steered after delay-all",
                )
            ],
        ),
    )

    comparison, h5, h2, src = load_g3_metrics_for_g4(
        g3_b_ids=[1201],
        g3_d_ids=[1301],
        report_md=docs / "gate3_report.md",
    )
    assert comparison is None
    assert h5 == {}
    assert h2 == {}
    assert "Tick 407" in src
    assert "never-steer" in src


def test_g3_resume_refuses_preflight_sidecar_without_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 373: no local G3 + preflight/null sidecar → refuse G4 metrics."""
    import run_icml_live_pipeline as pipe

    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "gate3_report.json").write_text(
        json.dumps(
            {
                "mode": "preflight",
                "executed": False,
                "comparison": {"d_wins_gens30": 1, "mean_final_gap": 0.2},
                "h5_by_d_run": {},
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate3_report.md").write_text("# Gate 3\n", encoding="utf-8")
    monkeypatch.setattr(pipe, "stage_runs_complete", lambda ids: False)

    comparison, h5, h2, src = load_g3_metrics_for_g4(
        g3_b_ids=[1201],
        g3_d_ids=[1301],
        report_md=docs / "gate3_report.md",
    )
    assert comparison is None
    assert h5 == {}
    assert h2 == {}
    assert "refuse G4" in src
    assert g3_pilot_promising(comparison, h5) is False


def test_g3_resume_trusts_live_executed_sidecar_ledger_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 373: ledger-only resume may trust a live-executed gate3 sidecar."""
    import run_icml_live_pipeline as pipe

    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    live_cmp = {
        "n_pairs": 1,
        "d_wins_cost30": 1,
        "mean_final_gap": 0.03,
        "mean_final_b": 0.22,
        "mean_final_d": 0.25,
    }
    (docs / "gate3_report.json").write_text(
        json.dumps(
            {
                "mode": "live",
                "executed": True,
                "comparison": live_cmp,
                "h5_by_d_run": {"run_1301": {"spearman_rho": 0.55}},
                "h2_by_d_run": {"run_1301": {"preferred_share": 0.6}},
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate3_report.md").write_text("# Gate 3\n", encoding="utf-8")
    monkeypatch.setattr(pipe, "stage_runs_complete", lambda ids: False)

    comparison, h5, h2, src = load_g3_metrics_for_g4(
        g3_b_ids=[1201],
        g3_d_ids=[1301],
        report_md=docs / "gate3_report.md",
    )
    assert comparison == live_cmp
    assert h5["run_1301"]["spearman_rho"] == 0.55
    assert h2["run_1301"]["preferred_share"] == 0.6
    assert "trusted live-executed gate3 sidecar" in src
    assert g3_pilot_promising(comparison, h5) is True


def test_g4_resume_refreshes_paper_pack_when_sidecar_preflight(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 374: resume-complete G4 + preflight sidecar → local re-score + pack."""
    import run_g4_multiseed as g4
    import run_icml_live_pipeline as pipe

    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
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
    (docs / "paper_artifacts.md").write_text("# Paper\n", encoding="utf-8")
    (docs / "ICML_READY.md").write_text("**STATUS: IN_PROGRESS**\n", encoding="utf-8")
    (docs / "figures").mkdir()

    b_ids = [1211, 1212, 1213, 1214, 1215]
    d_ids = [1311, 1312, 1313, 1314, 1315]
    b_dirs = [(tmp_path / "runs" / f"run_{i}") for i in b_ids]
    d_dirs = [(tmp_path / "runs" / f"run_{i}") for i in d_ids]
    for p in b_dirs + d_dirs:
        p.mkdir(parents=True)

    id_set = set(b_ids + d_ids)
    monkeypatch.setattr(pipe, "stage_runs_complete", lambda ids: set(ids) <= id_set)
    id_to_dir = {i: d for i, d in zip(b_ids + d_ids, b_dirs + d_dirs)}
    monkeypatch.setattr(
        pipe,
        "_resolve_run_dirs",
        lambda ids: [id_to_dir[i] for i in ids],
    )

    calls: dict[str, object] = {}

    def _fake_apply(report, **kwargs):
        calls["b_dirs"] = kwargs["b_dirs"]
        calls["d_dirs"] = kwargs["d_dirs"]
        calls["allow_ready"] = kwargs["allow_ready"]
        report.primary_pass = True
        report.h2_pass = True
        report.h5_pass = True
        report.ready_status = "READY"
        report.comparison = {"n_pairs": 5, "primary_gens30_pass": True}
        return True

    monkeypatch.setattr(g4, "apply_paper_pack", _fake_apply)
    monkeypatch.setattr(
        g4,
        "write_gate4_report",
        lambda report, out, **kw: calls.setdefault("wrote_report", str(out)),
    )

    report = PipelineReport(timestamp="2026-09-07T18:05:00Z", mode="live")
    note = refresh_g4_paper_pack_on_resume(
        g4_seeds="1,2,3,4,5",
        g4_b_ids=b_ids,
        g4_d_ids=d_ids,
        report=report,
        paper_artifacts=docs / "paper_artifacts.md",
        ready_path=docs / "ICML_READY.md",
        figures_dir=docs / "figures",
        gate4_report_md=docs / "gate4_report.md",
        allow_ready=True,
    )
    assert "re-scored G4 from local" in note
    assert calls["b_dirs"] == b_dirs
    assert calls["d_dirs"] == d_dirs
    assert calls["allow_ready"] is True
    assert calls["wrote_report"]
    assert report.icml_ready_status == "READY"


def test_g4_resume_refuses_preflight_sidecar_without_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 374: no local G4 + preflight sidecar → do not update ICML_READY."""
    import run_icml_live_pipeline as pipe

    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
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
    monkeypatch.setattr(pipe, "stage_runs_complete", lambda ids: False)

    report = PipelineReport(timestamp="2026-09-07T18:05:00Z", mode="live")
    note = refresh_g4_paper_pack_on_resume(
        g4_seeds="1,2,3,4,5",
        g4_b_ids=[1211, 1212, 1213, 1214, 1215],
        g4_d_ids=[1311, 1312, 1313, 1314, 1315],
        report=report,
        gate4_report_md=docs / "gate4_report.md",
    )
    assert "no local G4 artifacts" in note
    assert "ICML_READY not updated" in note
    assert report.icml_ready_status is None


def test_g4_resume_trusts_live_executed_sidecar_ledger_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 374: ledger-only resume may trust a live-executed gate4 paper pack."""
    import run_icml_live_pipeline as pipe

    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "gate4_report.json").write_text(
        json.dumps(
            {
                "mode": "live",
                "executed": True,
                "paper_refreshed": True,
                "ready_status": "READY",
                "comparison": {
                    "n_pairs": 5,
                    "primary_gens30_pass": True,
                    "d_wins_gens30": 4,
                },
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate4_report.md").write_text("# Gate 4\n", encoding="utf-8")
    monkeypatch.setattr(pipe, "stage_runs_complete", lambda ids: False)

    report = PipelineReport(timestamp="2026-09-07T18:05:00Z", mode="live")
    note = refresh_g4_paper_pack_on_resume(
        g4_seeds="1,2,3,4,5",
        g4_b_ids=[1211, 1212, 1213, 1214, 1215],
        g4_d_ids=[1311, 1312, 1313, 1314, 1315],
        report=report,
        gate4_report_md=docs / "gate4_report.md",
    )
    assert "trusted live-executed gate4 sidecar" in note
    assert report.icml_ready_status == "READY"


def test_refresh_g4_paper_pack_on_resume_trusts_prior_live_metrics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 386: prior_live_metrics survives preflight wipe for G4 resume trust."""
    import run_icml_live_pipeline as pipe

    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "gate4_report.json").write_text(
        json.dumps(
            {
                "mode": "preflight",
                "executed": False,
                "paper_refreshed": False,
                "comparison": None,
                "prior_live_metrics": {
                    "comparison": {
                        "n_pairs": 5,
                        "primary_gens30_pass": True,
                        "d_wins_gens30": 4,
                    },
                    "h5_by_d_run": {},
                    "h2_by_d_run": {},
                    "executed": True,
                    "paper_refreshed": True,
                    "primary_pass": True,
                    "h2_pass": True,
                    "h5_pass": True,
                    "ready_status": "READY",
                },
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate4_report.md").write_text("# Gate 4\n", encoding="utf-8")
    monkeypatch.setattr(pipe, "stage_runs_complete", lambda ids: False)

    report = PipelineReport(timestamp="2026-09-08T18:12:00Z", mode="live")
    note = refresh_g4_paper_pack_on_resume(
        g4_seeds="1,2,3,4,5",
        g4_b_ids=[1211, 1212, 1213, 1214, 1215],
        g4_d_ids=[1311, 1312, 1313, 1314, 1315],
        report=report,
        gate4_report_md=docs / "gate4_report.md",
    )
    assert "prior_live_metrics" in note
    assert report.icml_ready_status == "READY"


def test_refresh_g4_paper_pack_refuses_never_steer_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 408: gate4 sidecar steering_applied_gen3=false refuses READY trust."""
    import run_icml_live_pipeline as pipe

    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
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
    (docs / "gate4_report.md").write_text("# Gate 4\n", encoding="utf-8")
    monkeypatch.setattr(pipe, "stage_runs_complete", lambda ids: False)

    report = PipelineReport(timestamp="2026-09-10T16:15:00Z", mode="live")
    note = refresh_g4_paper_pack_on_resume(
        g4_seeds="1,2,3,4,5",
        g4_b_ids=[1211, 1212, 1213, 1214, 1215],
        g4_d_ids=[1311, 1312, 1313, 1314, 1315],
        report=report,
        gate4_report_md=docs / "gate4_report.md",
    )
    assert "steering_applied_gen3=false" in note
    assert "never-steer" in note


def test_refresh_g4_paper_pack_refuses_partial_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 412: gate4 sidecar n_pairs < planned refuses READY trust."""
    import run_icml_live_pipeline as pipe

    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "gate4_report.json").write_text(
        json.dumps(
            {
                "mode": "live",
                "executed": True,
                "paper_refreshed": True,
                "steering_applied_gen3": True,
                "comparison": {"n_pairs": 2, "primary_gens30_pass": True},
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
    (docs / "gate4_report.md").write_text("# Gate 4\n", encoding="utf-8")
    monkeypatch.setattr(pipe, "stage_runs_complete", lambda ids: False)

    report = PipelineReport(timestamp="2026-09-11T00:12:00Z", mode="live")
    note = refresh_g4_paper_pack_on_resume(
        g4_seeds="1,2,3,4,5",
        g4_b_ids=[1211, 1212, 1213, 1214, 1215],
        g4_d_ids=[1311, 1312, 1313, 1314, 1315],
        report=report,
        gate4_report_md=docs / "gate4_report.md",
    )
    assert "n_pairs=2" in note
    assert "planned=5" in note
    assert "refuse" in note.lower()
    assert report.icml_ready_status != "READY"


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
    assert any(
        "Tick 300" in n and "offline Bvd summary matches" in n for n in report.notes
    )
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


def test_write_pipeline_report_surfaces_g3_h2_and_mean_gap(tmp_path: Path) -> None:
    """Tick 369: pipeline G3→G4 gate shows mean_final_gap + H2 preferred (not binary only)."""
    report = PipelineReport(
        timestamp="2026-09-07T08:00:00Z",
        mode="live",
        budget=project_budget(),
        ready_for_live=True,
        g3_promising=True,
        g3_comparison={
            "n_pairs": 1,
            "d_wins_gens30": 1,
            "d_wins_cost30": 1,
            "d_wins_final": 1,
            "mean_final_gap": 0.0615,
            "primary_final_pass": True,
            "d_wins_h2": 1,
            "h2_preferred_pass": False,  # n<5 → aggregate False; per-run still shown
        },
        g3_h2_by_d_run={
            "run_1301": {
                "field": "tool_strategy",
                "preferred_value": "selective",
                "preferred_share": 0.75,
                "in_bias_share": 1.0,
            }
        },
        notes=["g3_promising=True"],
    )
    path = tmp_path / "icml_live_pipeline_report.md"
    write_pipeline_report(report, path)
    text = path.read_text(encoding="utf-8")
    assert "G3 promising: **yes**" in text
    assert "mean_final_gap" in text.lower() or "Mean final gap" in text
    assert "0.0615" in text
    assert "primary_final_pass=True" in text
    assert "h2_preferred_pass" in text
    assert "d_wins_h2" in text or "H2 preferred ≥0.5: **1/1**" in text
    assert "preferred_share=`0.75`" in text or "preferred_share=0.75" in text
    assert "tool_strategy" in text
    sidecar = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    assert sidecar["g3_promising"] is True
    assert sidecar["g3_comparison"]["mean_final_gap"] == 0.0615
    assert sidecar["g3_h2_by_d_run"]["run_1301"]["preferred_share"] == 0.75


def test_load_gate3_sidecar_returns_h2(tmp_path: Path) -> None:
    """Tick 369: sidecar loader returns h2_by_d_run (Tick 368 wrote it; pipeline ignored)."""
    from run_icml_live_pipeline import _load_gate3_sidecar

    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "gate3_report.md"
    md.write_text("# Gate 3\n", encoding="utf-8")
    (docs / "gate3_report.json").write_text(
        json.dumps(
            {
                "comparison": {
                    "n_pairs": 1,
                    "mean_final_gap": 0.04,
                    "d_wins_h2": 1,
                    "h2_preferred_pass": False,
                },
                "h5_by_d_run": {"run_1301": {"spearman_rho": 0.6}},
                "h2_by_d_run": {
                    "run_1301": {
                        "field": "tool_strategy",
                        "preferred_value": "selective",
                        "preferred_share": 0.8,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    cmp_, h5, h2 = _load_gate3_sidecar(md)
    assert cmp_ is not None
    assert cmp_["mean_final_gap"] == 0.04
    assert h5["run_1301"]["spearman_rho"] == 0.6
    assert h2["run_1301"]["preferred_share"] == 0.8


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
    assert any("Tick 300" in n and "refuse live" in n for n in report.notes)


def test_load_g2_post_for_g3_trusts_prior_live_post(tmp_path: Path) -> None:
    """Tick 384: prior_live_post survives preflight mode for G2→G3 trust."""
    import run_icml_live_pipeline as pipe

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "gate2_report.json").write_text(
        json.dumps(
            {
                "mode": "preflight",
                "run_id": 1300,
                "post": [],
                "prior_live_post": [
                    {"name": "nonzero_fitness", "ok": True, "detail": "best=0.2"},
                    {"name": "belief_store", "ok": True, "detail": "present"},
                ],
            }
        ),
        encoding="utf-8",
    )
    # Patch REPO_ROOT via report_md arg; no local run dirs.
    import run_g2_smoke as g2

    g2_orig = g2._run_dir_for
    try:
        g2._run_dir_for = lambda _rid: None  # type: ignore
        ok, note = load_g2_post_for_g3(
            g2_run_id=1300, report_md=docs / "gate2_report.md"
        )
    finally:
        g2._run_dir_for = g2_orig  # type: ignore
    assert ok is True
    assert "prior_live_post" in note


def test_load_g2_post_for_g3_refuses_preflight_without_prior(tmp_path: Path) -> None:
    """Tick 384: bare preflight sidecar must not unlock G3."""
    import run_g2_smoke as g2

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "gate2_report.json").write_text(
        json.dumps({"mode": "preflight", "run_id": 1300, "post": []}),
        encoding="utf-8",
    )
    orig = g2._run_dir_for
    try:
        g2._run_dir_for = lambda _rid: None  # type: ignore
        ok, note = load_g2_post_for_g3(
            g2_run_id=1300, report_md=docs / "gate2_report.md"
        )
    finally:
        g2._run_dir_for = orig  # type: ignore
    assert ok is False
    assert "refuse G3" in note


def test_live_stack_refuses_g3_without_g2_post(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 384: ledger G2 complete + no post → exit 4 before G3 spend."""
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
        "## 2026-09-08 — Tick 384 (test)\n", encoding="utf-8"
    )
    _seed_recipe_lock_docs(docs)
    write_budget_spent_ledger(
        spent_usd=0.85,
        stages_complete=["G2"],
        detail="prior tick G2",
        run_ids=[1300],
        path=docs / "icml_budget_spent.json",
    )
    (docs / "gate2_report.json").write_text(
        json.dumps({"mode": "preflight", "run_id": 1300, "post": []}),
        encoding="utf-8",
    )
    (docs / "gate2_report.md").write_text("# Gate 2\n", encoding="utf-8")
    monkeypatch.setattr(pipe.g2, "_run_dir_for", lambda _rid: None)
    monkeypatch.setattr(pipe.g3, "_run_dir_for", lambda _rid: None)
    monkeypatch.setattr(pipe.g4, "_run_dir_for", lambda _rid: None)

    called: list[str] = []
    monkeypatch.setattr(pipe.g2, "main", lambda *_a, **_k: called.append("g2") or 0)
    monkeypatch.setattr(pipe.g3, "main", lambda *_a, **_k: called.append("g3") or 0)
    monkeypatch.setattr(pipe, "_fetch_diamond", lambda **_k: ["fetched"])

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
    assert rc == 4
    assert "g2" not in called
    assert "g3" not in called
    text = (docs / "pipe.md").read_text(encoding="utf-8")
    assert "Tick 384" in text or "refuse G3" in text


def test_load_g3_metrics_for_g4_trusts_prior_live_metrics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 385: prior_live_metrics survives preflight mode for G3→G4 trust."""
    import run_icml_live_pipeline as pipe

    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    live_cmp = {
        "n_pairs": 1,
        "d_wins_gens30": 1,
        "d_wins_cost30": 1,
        "mean_final_gap": 0.04,
        "mean_final_b": 0.22,
        "mean_final_d": 0.26,
        "primary_final_pass": True,
    }
    (docs / "gate3_report.json").write_text(
        json.dumps(
            {
                "mode": "preflight",
                "executed": False,
                "comparison": None,
                "prior_live_metrics": {
                    "comparison": live_cmp,
                    "h5_by_d_run": {"run_1301": {"spearman_rho": 0.55}},
                    "h2_by_d_run": {"run_1301": {"preferred_share": 0.6}},
                    "executed": True,
                },
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate3_report.md").write_text("# Gate 3\n", encoding="utf-8")
    monkeypatch.setattr(pipe, "stage_runs_complete", lambda ids: False)

    comparison, h5, h2, src = load_g3_metrics_for_g4(
        g3_b_ids=[1201],
        g3_d_ids=[1301],
        report_md=docs / "gate3_report.md",
    )
    assert comparison == live_cmp
    assert h5["run_1301"]["spearman_rho"] == 0.55
    assert h2["run_1301"]["preferred_share"] == 0.6
    assert "prior_live_metrics" in src
    assert g3_pilot_promising(comparison, h5) is True
