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
    assert "--meta-agent-profile" in dry
    assert "kimi-nebius-pydantic-meta" in dry
    assert "--target-agent-profile" in dry
    assert "kimi-nebius-target" in dry
    live = build_sia_command(run_id=1300, seed=1, dry_run=False)
    assert "--dry-run" not in live
    assert "1300" in live
    assert "--meta-agent-profile" in live
    assert "kimi-nebius-pydantic-meta" in live
    assert "--target-agent-profile" in live
    assert "kimi-nebius-target" in live


def test_build_sia_command_honors_icml_profile_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ICML_TARGET_AGENT_PROFILE", "qwen-nebius-target")
    cmd = build_sia_command(run_id=1300, seed=1, dry_run=False)
    assert "qwen-nebius-target" in cmd
    assert "kimi-nebius-target" not in cmd


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
    # Tick 289: Nebius meta → anthropic optional (check still present, ok=True)
    assert names["anthropic_key"] is True
    assert names["nebius_key"] is False
    assert names["gpqa_not_synthetic"] is False  # smoke fixture


def test_preflight_mode_also_reports_live_not_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression: ready_for_live must not be vacuously true when mode!=live."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    import run_g2_smoke as mod

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    task.mkdir(parents=True)
    prepare_task_tree(task, n=5)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")

    report = run_preflight(mode="preflight", run_id=1850, ensure_smoke_layout=False)
    assert report.ready_for_dry_run is True
    assert report.ready_for_live is False
    assert any(not c.ok and c.name == "nebius_key" for c in report.checks)
    assert any(c.name == "nebius_meta_profile" and c.ok for c in report.checks)


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
    # Tick 306: stub tip lineage green (tmp tree has no ICML_PROGRESS tip).
    monkeypatch.setattr(
        mod,
        "write_icml_tip_status",
        lambda *_a, **_k: {
            "tip_ok_for_live": True,
            "local_tick": 306,
            "remote_tip_ref": "refs/remotes/origin/cursor/icml-epistemic-results-test",
            "blockers": [],
        },
    )

    report = run_preflight(mode="live", run_id=1300, ensure_smoke_layout=False)
    assert report.ready_for_live is True
    assert report.blockers == []


def test_preflight_refuses_stale_tip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 306: direct G2 --live refuses when tip lineage lags (not only pipeline)."""
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
    monkeypatch.setattr(
        mod,
        "write_icml_tip_status",
        lambda *_a, **_k: {
            "tip_ok_for_live": False,
            "local_tick": 300,
            "remote_tip_tick": 306,
            "remote_tip_ref": "refs/remotes/origin/cursor/icml-epistemic-results-tip",
            "blockers": [
                "local Tick 300 behind remote tip Tick 306 "
                "(refs/remotes/origin/cursor/icml-epistemic-results-tip)"
            ],
        },
    )

    report = run_preflight(mode="live", run_id=1300, ensure_smoke_layout=False)
    assert report.ready_for_live is False
    names = {c.name: c.ok for c in report.checks}
    assert names["tip_ok_for_live"] is False
    assert names["nebius_key"] is True
    assert names["gpqa_not_synthetic"] is True

    report2 = run_preflight(
        mode="live",
        run_id=1300,
        ensure_smoke_layout=False,
        allow_stale_tip=True,
    )
    assert report2.ready_for_live is True
    names2 = {c.name: c.ok for c in report2.checks}
    assert names2["tip_ok_for_live"] is True
    assert any("allow-stale-tip" in n for n in report2.notes)


def _write_fair_gen2_agent(
    run_dir: Path, agent_id: int = 0, *, agenda: bool = False, seeds=None
) -> Path:
    """Tick 406 helper: minimal fair gen2 agent artifacts for G2 post-checks."""
    agent2 = run_dir / "gen_2" / f"agent_{agent_id}"
    agent2.mkdir(parents=True, exist_ok=True)
    fb = "# Dry-run: offspring\n### Darwinian Evolution Context\n"
    if agenda:
        fb = "## CABS: Contradiction-Aware Research Agenda\n" + fb
    (agent2 / "feedback_agent_prompt.txt").write_text(fb, encoding="utf-8")
    (agent2 / "agent_dna.json").write_text(
        json.dumps(
            {
                "tool_strategy": "selective",
                "technique_seeds": list(seeds or []),
            }
        ),
        encoding="utf-8",
    )
    return agent2


def test_validate_g2_artifacts_reads_belief_store(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_1850"
    store = run_dir / "belief_store"
    store.mkdir(parents=True)
    (store / "epistemic_value.jsonl").write_text(
        json.dumps({"generation": 1, "epistemic_value": 1.0}) + "\n", encoding="utf-8"
    )
    (store / "contradictions.json").write_text("[]\n", encoding="utf-8")
    (store / "beliefs.json").write_text("[]\n", encoding="utf-8")
    _write_fair_gen2_agent(run_dir)
    checks = {c.name: c for c in validate_g2_artifacts(run_dir)}
    assert checks["belief_store"].ok
    assert checks["epistemic_value_jsonl"].ok
    # empty JSON arrays are size>2? "[]\n" is 3 bytes — has_cabs true; bias may fail
    assert "scoped_mutation_bias" in checks
    # Tick 371: no fitness artifacts → nonzero_fitness fails (blocks G3 burn).
    assert checks["nonzero_fitness"].ok is False
    assert checks["delay_all_feedback_skip"].ok is True
    assert checks["delay_all_technique_seeds_skip"].ok is True


def test_validate_g2_artifacts_nonzero_fitness_gate(tmp_path: Path) -> None:
    """Tick 371: G2 PASS requires best fitness > floor (default 0)."""
    run_dir = tmp_path / "run_1852"
    store = run_dir / "belief_store"
    store.mkdir(parents=True)
    (store / "epistemic_value.jsonl").write_text(
        json.dumps({"generation": 1, "epistemic_value": 1.0}) + "\n", encoding="utf-8"
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
    _write_fair_gen2_agent(run_dir)
    checks = {c.name: c for c in validate_g2_artifacts(run_dir)}
    assert checks["nonzero_fitness"].ok is False

    (agent / "results.json").write_text(
        json.dumps({"accuracy": 0.2}), encoding="utf-8"
    )
    checks_ok = {c.name: c for c in validate_g2_artifacts(run_dir)}
    assert checks_ok["nonzero_fitness"].ok is True
    assert "0.2000" in checks_ok["nonzero_fitness"].detail


def test_validate_g2_artifacts_delay_all_gates(tmp_path: Path) -> None:
    """Tick 406: G2 post-checks refuse agenda / technique_seeds on fair gen2."""
    run_dir = tmp_path / "run_1953"
    store = run_dir / "belief_store"
    store.mkdir(parents=True)
    (store / "epistemic_value.jsonl").write_text(
        json.dumps({"generation": 1, "epistemic_value": 1.0}) + "\n", encoding="utf-8"
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
    (agent / "results.json").write_text(json.dumps({"accuracy": 0.25}), encoding="utf-8")

    missing = {c.name: c for c in validate_g2_artifacts(run_dir)}
    assert missing["delay_all_feedback_skip"].ok is False
    assert missing["delay_all_technique_seeds_skip"].ok is False

    _write_fair_gen2_agent(run_dir, agenda=True, seeds=["self_consistency"])
    leaked = {c.name: c for c in validate_g2_artifacts(run_dir)}
    assert leaked["delay_all_feedback_skip"].ok is False
    assert "leaked" in leaked["delay_all_feedback_skip"].detail
    assert leaked["delay_all_technique_seeds_skip"].ok is False
    assert "technique_seeds" in leaked["delay_all_technique_seeds_skip"].detail

    _write_fair_gen2_agent(run_dir, agenda=False, seeds=[])
    fair = {c.name: c for c in validate_g2_artifacts(run_dir)}
    assert fair["delay_all_feedback_skip"].ok is True
    assert fair["delay_all_technique_seeds_skip"].ok is True


def test_validate_g2_artifacts_steering_lift_gen3(tmp_path: Path) -> None:
    """Tick 509: max_gen≥3 / gen_3 artifacts require delay-all lift (Tick 407)."""
    run_dir = tmp_path / "run_1955"
    store = run_dir / "belief_store"
    store.mkdir(parents=True)
    (store / "epistemic_value.jsonl").write_text(
        json.dumps({"generation": 1, "epistemic_value": 1.0}) + "\n", encoding="utf-8"
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
    agent1 = run_dir / "gen_1" / "agent_0"
    agent1.mkdir(parents=True)
    (agent1 / "results.json").write_text(json.dumps({"accuracy": 0.25}), encoding="utf-8")
    _write_fair_gen2_agent(run_dir, agenda=False, seeds=[])

    # max_gen=2 path: no gen_3 → no steering_lift checks required
    no_lift = {c.name: c for c in validate_g2_artifacts(run_dir)}
    assert not any(n.startswith("steering_applied_") for n in no_lift)

    # require_steering_lift without gen_3 → fail (cannot prove lift)
    forced = {
        c.name: c
        for c in validate_g2_artifacts(run_dir, require_steering_lift=True)
    }
    assert any(n.startswith("steering_applied_") for n in forced)
    steer_forced = next(c for n, c in forced.items() if n.startswith("steering_applied_"))
    assert steer_forced.ok is False

    # gen_3 without agenda → auto-detected never-steer fail
    agent3 = run_dir / "gen_3" / "agent_0"
    agent3.mkdir(parents=True)
    (agent3 / "feedback_agent_prompt.txt").write_text(
        "# Dry-run: offspring\n### Darwinian Evolution Context\n",
        encoding="utf-8",
    )
    never = {c.name: c for c in validate_g2_artifacts(run_dir)}
    steer_never = next(c for n, c in never.items() if n.startswith("steering_applied_"))
    assert steer_never.ok is False
    assert "never steered" in steer_never.detail or "lacks" in steer_never.detail

    # gen_3 with Contradiction-Aware agenda → PASS lift
    (agent3 / "feedback_agent_prompt.txt").write_text(
        "## CABS: Contradiction-Aware Research Agenda\n"
        "# Dry-run: offspring\n### Darwinian Evolution Context\n",
        encoding="utf-8",
    )
    lifted = {c.name: c for c in validate_g2_artifacts(run_dir)}
    steer_ok = next(c for n, c in lifted.items() if n.startswith("steering_applied_"))
    assert steer_ok.ok is True
    assert "delay-all lifted" in steer_ok.detail
    assert lifted["delay_all_feedback_skip"].ok is True
    assert lifted["delay_all_technique_seeds_skip"].ok is True


def test_main_fetch_diamond_from_csv_clears_synthetic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 25: --fetch-diamond --diamond-csv replaces smoke before preflight."""
    import csv
    import run_g2_smoke as mod

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)

    root = tmp_path
    for name in ("SIA", "sia-upstream"):
        task = root / name / "sia" / "tasks" / "gpqa"
        task.mkdir(parents=True)
        prepare_task_tree(task, n=5)
        assert is_synthetic_smoke(task) is True

    csv_path = root / "fake_diamond.csv"
    fieldnames = [
        "Question",
        "Correct Answer",
        "Incorrect Answer 1",
        "Incorrect Answer 2",
        "Incorrect Answer 3",
        "High-level domain",
        "Subdomain",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for i in range(5):
            w.writerow(
                {
                    "Question": f"Harness chem item {i}?",
                    "Correct Answer": "yes",
                    "Incorrect Answer 1": "no",
                    "Incorrect Answer 2": "maybe",
                    "Incorrect Answer 3": "never",
                    "High-level domain": "Chemistry",
                    "Subdomain": "General",
                }
            )

    monkeypatch.setattr(mod, "REPO_ROOT", root)
    report_path = root / "docs" / "gate2_report.md"
    rc = mod.main(
        [
            "--preflight-only",
            "--run-id",
            "1851",
            "--fetch-diamond",
            "--diamond-csv",
            str(csv_path),
            "--report",
            str(report_path),
        ]
    )
    assert rc == 0
    sia_task = root / "SIA" / "sia" / "tasks" / "gpqa"
    assert is_synthetic_smoke(sia_task) is False
    text = report_path.read_text(encoding="utf-8")
    assert "materialized diamond from CSV" in text
    # Still not live-ready without API keys
    payload = json.loads(report_path.with_suffix(".json").read_text())
    assert payload["ready_for_live"] is False
    assert any(c["name"] == "gpqa_not_synthetic" and c["ok"] for c in payload["checks"])


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
    # Diamond not ready → still offers public-mirror materialize (not HF-only).
    assert "--from-public-mirror" in text
    assert "Accept HF access for `Idavidrein/gpqa`" not in text


def test_write_gate2_report_persists_next_steps_json(tmp_path: Path) -> None:
    """Tick 536: gate2 JSON next_steps mirrors MD ## Next (pipeline Tick 535 parity)."""
    from run_g2_smoke import CheckResult, PreflightReport, write_gate2_report

    report = PreflightReport(
        timestamp="2026-10-04T22:00:00Z",
        mode="preflight",
        run_id=1850,
        ready_for_dry_run=True,
        ready_for_live=False,
        command=["python3", "-m", "sia", "run", "--dry-run"],
        blockers=["nebius_key: NEBIUS_API_KEY missing"],
        notes=["diamond already ready via public mirror"],
    )
    report.checks.append(CheckResult("gpqa_not_synthetic", True, "ok"))
    report.checks.append(CheckResult("nebius_key", False, "missing"))
    out = tmp_path / "gate2_report.md"
    write_gate2_report(report, out)
    text = out.read_text(encoding="utf-8")
    sidecar = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert isinstance(sidecar.get("next_steps"), list)
    assert sidecar["next_steps"]
    assert any("NEBIUS_API_KEY" in s for s in sidecar["next_steps"])
    after = text.split("## Next", 1)[-1]
    md_steps = [
        line.split(". ", 1)[1]
        for line in after.splitlines()
        if line and line[0].isdigit() and ". " in line
    ]
    assert md_steps == sidecar["next_steps"]


def test_gate2_next_steps_json_source_lock() -> None:
    """Tick 536: gate2 writer + tests keep JSON next_steps with MD ## Next."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    src = (root / "scripts" / "run_g2_smoke.py").read_text(encoding="utf-8")
    tests = (root / "tests" / "test_run_g2_smoke.py").read_text(encoding="utf-8")
    assert "extract_numbered_next_steps" in src
    assert '"next_steps": cleaned_next' in src or "'next_steps': cleaned_next" in src
    assert "test_write_gate2_report_persists_next_steps_json" in tests


def test_write_gate2_report_sanitizes_absolute_paths(tmp_path: Path) -> None:
    """Tick 528: notes/blockers/check details drop absolute /workspace and /tmp diamond."""
    from run_g2_smoke import (
        CheckResult,
        PreflightReport,
        _sanitize_gate_report_text,
        write_gate2_report,
    )

    workspace = Path("/workspace")
    abs_note = (
        f"runtime deps before diamond: PYTHONPATH={workspace}/SIA; "
        f"materialized → ['{workspace}/SIA/sia/tasks/gpqa']; "
        f"auto-wired --diamond-csv from /tmp/gpqa_diamond.csv"
    )
    report = PreflightReport(
        timestamp="2026-10-04T06:00:00Z",
        mode="preflight",
        run_id=1850,
        ready_for_dry_run=True,
        ready_for_live=False,
        command=["python3", "-m", "sia", "run", "--dry-run"],
        blockers=[f"diamond fetch failed: No such file: {workspace}/missing.csv"],
        notes=[abs_note],
    )
    report.checks.append(
        CheckResult(
            "runtime_deps",
            True,
            f"PYTHONPATH={workspace}/SIA; ok under {workspace}/runs",
        )
    )
    out = tmp_path / "gate2_report.md"
    write_gate2_report(report, out)
    text = out.read_text(encoding="utf-8")
    sidecar = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert "/workspace" not in text
    assert "/tmp/gpqa_diamond.csv" not in text
    assert "$TMPDIR/gpqa_diamond.csv" in text or "gpqa_diamond.csv" in text
    blob = json.dumps(sidecar)
    assert "/workspace" not in blob
    assert "/tmp/gpqa_diamond.csv" not in blob
    cleaned = _sanitize_gate_report_text(abs_note, repo_root=Path("/workspace"))
    assert "/workspace" not in cleaned
    assert "/tmp/gpqa_diamond.csv" not in cleaned


def test_write_gate2_report_sanitize_source_lock() -> None:
    """Tick 528: gate2 writer must keep sanitize helper + write-time wiring."""
    from pathlib import Path

    src = Path("scripts/run_g2_smoke.py").read_text(encoding="utf-8")
    tests = Path("tests/test_run_g2_smoke.py").read_text(encoding="utf-8")
    assert "def _sanitize_gate_report_text" in src
    assert "sanitize_repo_paths_in_text" in src
    assert "Tick 528" in src
    assert "test_write_gate2_report_sanitizes_absolute_paths" in tests


def test_gate2_next_nebius_first_when_diamond_ready(tmp_path: Path) -> None:
    """Tick 498: non-synthetic diamond → Next leads with NEBIUS, no HF-accept step."""
    from run_g2_smoke import (
        PreflightReport,
        CheckResult,
        gate2_diamond_ready,
        gate2_next_markdown_lines,
        write_gate2_report,
    )

    report = PreflightReport(
        timestamp="2026-10-01T18:20:00Z",
        mode="preflight",
        run_id=1850,
        ready_for_dry_run=True,
        ready_for_live=False,
        command=["sia", "run", "--dry-run"],
        blockers=["nebius_key: NEBIUS_API_KEY missing"],
    )
    report.checks.append(
        CheckResult(
            "gpqa_not_synthetic",
            True,
            "real/non-smoke diamond_questions.json present",
        )
    )
    report.checks.append(CheckResult("nebius_key", False, "NEBIUS_API_KEY missing"))
    report.notes.append("Tick 278: auto-wired --diamond-csv from /tmp/gpqa_diamond.csv")
    assert gate2_diamond_ready(report) is True
    next_text = "\n".join(gate2_next_markdown_lines(report))
    assert "NEBIUS_API_KEY" in next_text
    assert "Accept HF access" not in next_text
    assert "--from-hf" not in next_text
    assert "--live --run-id <unused> --fetch-diamond" in next_text

    out = tmp_path / "gate2_report.md"
    write_gate2_report(report, out)
    text = out.read_text(encoding="utf-8")
    assert "Add **`NEBIUS_API_KEY`**" in text
    assert "Accept HF access for `Idavidrein/gpqa`" not in text
    assert "--from-hf" not in text

def test_preflight_require_hf_for_diamond_blocks_without_hf(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 275: --fetch-diamond path requires HF in ready_for_live."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-ant")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-neb")
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)

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
    monkeypatch.setattr(
        mod,
        "write_icml_tip_status",
        lambda *_a, **_k: {
            "tip_ok_for_live": True,
            "local_tick": 306,
            "remote_tip_ref": "refs/remotes/origin/cursor/icml-epistemic-results-test",
            "blockers": [],
        },
    )

    report = run_preflight(
        mode="live", run_id=1300, ensure_smoke_layout=False, require_hf_for_diamond=True
    )
    assert report.ready_for_live is False
    names = {c.name: c.ok for c in report.checks}
    assert names["hf_token"] is False
    assert names["anthropic_key"] is True
    assert names["tip_ok_for_live"] is True


def test_main_live_fetch_diamond_refuses_without_hf(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 275: G2 --live --fetch-diamond exits 4 before materialize without HF."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("NEBIUS_API_KEY", "nb-test")
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    monkeypatch.delenv("ICML_DIAMOND_CSV", raising=False)

    import run_g2_smoke as mod

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    # Isolate from host /tmp/gpqa_diamond.csv + public mirror (Tick 502 VM noise).
    monkeypatch.setattr(mod, "autowire_diamond_csv", lambda *a, **k: (None, False))
    monkeypatch.setattr(
        "icml_env_checks.resolve_diamond_csv_path", lambda **_k: None
    )
    monkeypatch.setattr(
        "icml_env_checks.ensure_diamond_csv_via_public_mirror", lambda **_k: None
    )
    monkeypatch.setattr(
        "icml_env_checks.detect_gpqa_is_synthetic", lambda *_a, **_k: None
    )
    (tmp_path / "docs").mkdir()
    called: list[str] = []

    def boom(*_a, **_k):
        called.append("hf")
        raise AssertionError("must not materialize from HF")

    monkeypatch.setattr(mod, "materialize_from_hf", boom)
    report_path = tmp_path / "docs" / "gate2_report.md"
    rc = mod.main(
        [
            "--live",
            "--run-id",
            "1300",
            "--fetch-diamond",
            "--report",
            str(report_path),
        ]
    )
    assert rc == 4
    assert called == []
    text = report_path.read_text(encoding="utf-8")
    assert "HF_TOKEN" in text or "fetch_diamond" in text.lower()


def test_main_live_fetch_diamond_refuse_csv_autowire_without_nebius(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 503: CSV auto-wire clears require_hf but missing NEBIUS still refuses."""
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    monkeypatch.delenv("ICML_DIAMOND_CSV", raising=False)

    import run_g2_smoke as mod

    csv_path = tmp_path / "gpqa_diamond.csv"
    csv_path.write_text("Question,Correct Answer\nx,y\n" + ("z,w\n" * 20), encoding="utf-8")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "autowire_diamond_csv", lambda *a, **k: (csv_path, True))
    monkeypatch.setattr(
        "icml_env_checks.resolve_diamond_csv_path", lambda **_k: csv_path
    )
    monkeypatch.setattr(
        "icml_env_checks.ensure_diamond_csv_via_public_mirror", lambda **_k: None
    )
    monkeypatch.setattr(
        "icml_env_checks.detect_gpqa_is_synthetic", lambda *_a, **_k: False
    )
    (tmp_path / "docs").mkdir()
    called: list[str] = []

    def boom_csv(*_a, **_k):
        called.append("csv")
        raise AssertionError("must not materialize when NEBIUS missing")

    def boom_hf(*_a, **_k):
        called.append("hf")
        raise AssertionError("must not materialize from HF")

    monkeypatch.setattr(mod, "materialize_from_csv", boom_csv)
    monkeypatch.setattr(mod, "materialize_from_hf", boom_hf)
    report_path = tmp_path / "docs" / "gate2_report.md"
    rc = mod.main(
        [
            "--live",
            "--run-id",
            "1300",
            "--fetch-diamond",
            "--report",
            str(report_path),
        ]
    )
    assert rc == 4
    assert called == []
    text = report_path.read_text(encoding="utf-8")
    assert "NEBIUS" in text
    assert "diamond already ready" in text.lower() or "HF optional" in text


def test_main_live_fetch_diamond_skips_hf_when_ondisk_nonsynthetic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 502: on-disk non-synthetic diamond ⇒ no HF rematerialize under --fetch-diamond."""
    monkeypatch.setenv("NEBIUS_API_KEY", "nb-test")
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ICML_DIAMOND_CSV", raising=False)

    import run_g2_smoke as mod

    # Non-synthetic GPQA layout (no CSV, no HF).
    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    (task / "data" / "private").mkdir(parents=True)
    (task / "data" / "public").mkdir(parents=True)
    rows = [
        {
            "domain": "physics",
            "Question": "Real diamond Q1?",
            "correct_answer_letter": "A",
            "choices": {"A": "a", "B": "b", "C": "c", "D": "d"},
        }
    ]
    payload = json.dumps(rows)
    (task / "data" / "private" / "diamond_questions.json").write_text(
        payload, encoding="utf-8"
    )
    (task / "data" / "public" / "diamond_questions.json").write_text(
        payload, encoding="utf-8"
    )

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    (tmp_path / "docs").mkdir()
    called: list[str] = []

    def boom_hf(*_a, **_k):
        called.append("hf")
        raise AssertionError("must not materialize from HF when ondisk ready")

    def boom_csv(*_a, **_k):
        called.append("csv")
        raise AssertionError("must not materialize from CSV when none wired")

    monkeypatch.setattr(mod, "materialize_from_hf", boom_hf)
    monkeypatch.setattr(mod, "materialize_from_csv", boom_csv)
    monkeypatch.setattr(mod, "autowire_diamond_csv", lambda *a, **k: (None, False))
    # Tick 503: early live refuse always collects secrets (even when require_hf is
    # false). Avoid host git via the subprocess.run stub below.
    monkeypatch.setattr(
        mod,
        "collect_icml_secrets_status",
        lambda: {
            "fetch_diamond_ok": True,
            "diamond_ready": True,
            "blockers": [],
            "secrets_ok_for_paid_sia": True,
        },
    )
    # Tip status OK so ready_for_live is not blocked on tip lineage.
    monkeypatch.setattr(
        mod,
        "write_icml_tip_status",
        lambda *a, **k: {
            "tip_ok_for_live": True,
            "local_tick": 502,
            "remote_tip_tick": 502,
            "blockers": [],
        },
    )
    # Avoid real uv/profile probes failing the assert path — we only care that
    # HF was not called and notes mention Tick 502 keep.
    monkeypatch.setattr(mod, "probe_per_run_venv_capable", lambda **k: (True, "ok"))
    monkeypatch.setattr(mod, "ensure_icml_runtime_deps", lambda **k: (True, "ok"))
    monkeypatch.setattr(mod, "probe_icml_meta_profile", lambda: (True, "ok"))
    monkeypatch.setattr(mod, "probe_icml_target_profile_nebius", lambda: (True, "ok"))
    monkeypatch.setattr(
        mod,
        "ensure_deps_before_diamond_fetch",
        lambda **k: (_ for _ in ()).throw(AssertionError("deps only for HF/CSV")),
    )

    # Short-circuit sia run — if we reach live, return success without subprocess.
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *a, **k: type("R", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(
        mod,
        "validate_g2_artifacts",
        lambda *a, **k: [
            mod.CheckResult("belief_store", True, "ok"),
            mod.CheckResult("best_fitness_nonzero", True, "0.2"),
        ],
    )
    monkeypatch.setattr(mod, "_run_dir_for", lambda rid: tmp_path / "runs" / f"run_{rid}")
    (tmp_path / "runs" / "run_1300").mkdir(parents=True)

    report_path = tmp_path / "docs" / "gate2_report.md"
    rc = mod.main(
        [
            "--live",
            "--run-id",
            "1300",
            "--fetch-diamond",
            "--report",
            str(report_path),
        ]
    )
    assert called == []
    text = report_path.read_text(encoding="utf-8")
    assert "Tick 502" in text
    assert "skip" in text and "rematerialize" in text
    # Live may still fail other preflight bits; must not be the HF-missing exit 4.
    assert rc != 4 or "HF_TOKEN" not in text


def test_main_live_fetch_diamond_keeps_ondisk_when_csv_autowired(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 504: auto-wired CSV + ondisk ready ⇒ keep ondisk (no rematerialize)."""
    monkeypatch.setenv("NEBIUS_API_KEY", "nb-test")
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ICML_DIAMOND_CSV", raising=False)

    import run_g2_smoke as mod

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    (task / "data" / "private").mkdir(parents=True)
    (task / "data" / "public").mkdir(parents=True)
    rows = [
        {
            "domain": "physics",
            "Question": "Real diamond Q1?",
            "correct_answer_letter": "A",
            "choices": {"A": "a", "B": "b", "C": "c", "D": "d"},
        }
    ]
    payload = json.dumps(rows)
    (task / "data" / "private" / "diamond_questions.json").write_text(
        payload, encoding="utf-8"
    )
    (task / "data" / "public" / "diamond_questions.json").write_text(
        payload, encoding="utf-8"
    )

    csv_path = tmp_path / "gpqa_diamond.csv"
    csv_path.write_text(
        "Question,Correct Answer\nx,y\n" + ("z,w\n" * 20), encoding="utf-8"
    )

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    (tmp_path / "docs").mkdir()
    called: list[str] = []

    def boom_csv(*_a, **_k):
        called.append("csv")
        raise AssertionError("must not rematerialize from auto-wired CSV")

    def boom_hf(*_a, **_k):
        called.append("hf")
        raise AssertionError("must not materialize from HF")

    monkeypatch.setattr(mod, "materialize_from_csv", boom_csv)
    monkeypatch.setattr(mod, "materialize_from_hf", boom_hf)
    monkeypatch.setattr(mod, "autowire_diamond_csv", lambda *a, **k: (csv_path, True))
    monkeypatch.setattr(
        mod,
        "collect_icml_secrets_status",
        lambda: {
            "fetch_diamond_ok": True,
            "diamond_ready": True,
            "blockers": [],
            "secrets_ok_for_paid_sia": True,
        },
    )
    monkeypatch.setattr(
        mod,
        "write_icml_tip_status",
        lambda *a, **k: {
            "tip_ok_for_live": True,
            "local_tick": 504,
            "remote_tip_tick": 504,
            "blockers": [],
        },
    )
    monkeypatch.setattr(mod, "probe_per_run_venv_capable", lambda **k: (True, "ok"))
    monkeypatch.setattr(mod, "ensure_icml_runtime_deps", lambda **k: (True, "ok"))
    monkeypatch.setattr(mod, "probe_icml_meta_profile", lambda: (True, "ok"))
    monkeypatch.setattr(mod, "probe_icml_target_profile_nebius", lambda: (True, "ok"))
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *a, **k: type("R", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(
        mod,
        "validate_g2_artifacts",
        lambda *a, **k: [
            mod.CheckResult("belief_store", True, "ok"),
            mod.CheckResult("best_fitness_nonzero", True, "0.2"),
        ],
    )
    monkeypatch.setattr(
        mod, "_run_dir_for", lambda rid: tmp_path / "runs" / f"run_{rid}"
    )
    (tmp_path / "runs" / "run_1300").mkdir(parents=True)

    report_path = tmp_path / "docs" / "gate2_report.md"
    rc = mod.main(
        [
            "--live",
            "--run-id",
            "1300",
            "--fetch-diamond",
            "--report",
            str(report_path),
        ]
    )
    assert called == []
    text = report_path.read_text(encoding="utf-8")
    assert "Tick 502/504" in text or "auto-wired CSV is fallback" in text
    assert rc != 4 or "HF_TOKEN" not in text


def test_main_fetch_diamond_bootstraps_deps_before_hf(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 282: ensure_deps_before_diamond_fetch runs before materialize_from_hf."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("NEBIUS_API_KEY", "nb-test")
    monkeypatch.setenv("HF_TOKEN", "hf-test")
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")

    import run_g2_smoke as mod

    order: list[str] = []

    def _deps(*, allow_install: bool = True) -> tuple[bool, str]:
        order.append("deps")
        return True, "deps-ok"

    def _hf(*_a, **_k):
        order.append("hf")
        return ["SIA/sia/tasks/gpqa"]

    monkeypatch.setattr(mod, "ensure_deps_before_diamond_fetch", _deps)
    monkeypatch.setattr(mod, "materialize_from_hf", _hf)
    monkeypatch.setattr(
        mod,
        "run_preflight",
        lambda **_k: mod.PreflightReport(
            timestamp="t", mode="preflight", run_id=1399
        ),
    )
    monkeypatch.setattr(mod, "write_gate2_report", lambda *a, **k: None)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    (tmp_path / "docs").mkdir(exist_ok=True)

    rc = mod.main(
        [
            "--preflight-only",
            "--run-id",
            "1399",
            "--fetch-diamond",
            "--report",
            str(tmp_path / "docs" / "gate2_report.md"),
        ]
    )
    assert rc == 0
    assert order == ["deps", "hf"]


def test_g2_preflight_hydrates_budget_from_ledger(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 378: direct G2 preflight loads ledger spent when env is unset."""
    import os

    import run_g2_smoke as mod

    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("SIA_BUDGET_SPENT_USD", raising=False)
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {
                "spent_usd": 17.5,
                "stages_complete": ["G2", "G3"],
                "run_ids": [1300, 1201, 1301],
                "detail": "prior stack",
            }
        ),
        encoding="utf-8",
    )

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    task.mkdir(parents=True)
    prepare_task_tree(task, n=5)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    monkeypatch.setattr(mod, "probe_per_run_venv_capable", lambda **_k: (True, "ok"))
    monkeypatch.setattr(mod, "ensure_icml_runtime_deps", lambda **_k: (True, "ok"))
    monkeypatch.setattr(mod, "probe_icml_meta_profile", lambda: (True, "ok"))
    monkeypatch.setattr(mod, "probe_icml_target_profile_nebius", lambda: (True, "ok"))
    monkeypatch.setattr(
        mod,
        "write_icml_tip_status",
        lambda *a, **k: {"tip_ok_for_live": True, "local_tick": 378},
    )

    report = run_preflight(mode="preflight", run_id=1400, ensure_smoke_layout=False)
    names = {c.name: c for c in report.checks}
    assert names["budget"].ok is True
    assert "17.50" in names["budget"].detail or "17.5" in names["budget"].detail
    assert any("hydrate" in n.lower() for n in report.notes)
    assert float(os.environ.get("SIA_BUDGET_SPENT_USD", "0")) == pytest.approx(17.5)


def test_g2_preflight_hydrates_budget_from_unbilled_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 378: direct G2 bills a complete unbilled local smoke into spent."""
    import os

    import run_g2_smoke as mod

    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("SIA_BUDGET_SPENT_USD", raising=False)
    monkeypatch.setenv("SIA_BUDGET_CEILING_USD", "20")
    monkeypatch.setenv("SIA_G2_ESTIMATE_USD", "1.25")

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {
                "spent_usd": 2.0,
                "stages_complete": [],
                "run_ids": [],
                "detail": "empty",
            }
        ),
        encoding="utf-8",
    )

    # Planned run_id already complete locally but not in ledger
    agent = tmp_path / "runs" / "run_1300" / "gen_1" / "agent_0"
    agent.mkdir(parents=True, exist_ok=True)
    (agent / "results.json").write_text(
        json.dumps({"accuracy": 0.2, "total_cost_usd": 0.4}),
        encoding="utf-8",
    )

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    task.mkdir(parents=True)
    prepare_task_tree(task, n=5)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    monkeypatch.setattr(mod, "probe_per_run_venv_capable", lambda **_k: (True, "ok"))
    monkeypatch.setattr(mod, "ensure_icml_runtime_deps", lambda **_k: (True, "ok"))
    monkeypatch.setattr(mod, "probe_icml_meta_profile", lambda: (True, "ok"))
    monkeypatch.setattr(mod, "probe_icml_target_profile_nebius", lambda: (True, "ok"))
    monkeypatch.setattr(
        mod,
        "write_icml_tip_status",
        lambda *a, **k: {"tip_ok_for_live": True, "local_tick": 378},
    )

    report = run_preflight(mode="preflight", run_id=1300, ensure_smoke_layout=False)
    names = {c.name: c for c in report.checks}
    assert names["budget"].ok is True
    assert any("Tick 377/378" in n or "hydrate" in n.lower() for n in report.notes)
    assert float(os.environ.get("SIA_BUDGET_SPENT_USD", "0")) > 2.0
    ledger = json.loads((docs / "icml_budget_spent.json").read_text(encoding="utf-8"))
    assert 1300 in ledger["run_ids"]
    assert "G2" not in ledger["stages_complete"]


def test_g2_live_skips_when_ledger_stage_complete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 380: direct --live no-ops when ledger already marks G2 complete."""
    import run_g2_smoke as mod

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
                "spent_usd": 1.5,
                "stages_complete": ["G2"],
                "run_ids": [1300],
                "detail": "prior G2",
            }
        ),
        encoding="utf-8",
    )

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    task.mkdir(parents=True)
    prepare_task_tree(task, n=5)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    monkeypatch.setattr(mod, "probe_per_run_venv_capable", lambda **_k: (True, "ok"))
    monkeypatch.setattr(mod, "ensure_icml_runtime_deps", lambda **_k: (True, "ok"))
    monkeypatch.setattr(mod, "probe_icml_meta_profile", lambda: (True, "ok"))
    monkeypatch.setattr(mod, "probe_icml_target_profile_nebius", lambda: (True, "ok"))
    monkeypatch.setattr(
        mod,
        "write_icml_tip_status",
        lambda *a, **k: {"tip_ok_for_live": True, "local_tick": 380},
    )

    # No local runs/ — cross-VM resume. Must not call sia.
    called: list[list[str]] = []

    def _fake_run(cmd, **_kwargs):
        called.append(list(cmd))

        class _P:
            returncode = 0

        return _P()

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)

    report_path = docs / "gate2_report.md"
    rc = mod.main(
        [
            "--live",
            "--run-id",
            "1300",
            "--report",
            str(report_path),
            "--cwd",
            str(tmp_path),
        ]
    )
    assert rc == 0
    assert called == []
    text = report_path.read_text(encoding="utf-8")
    assert "Tick 380" in text or "ledger" in text.lower()


def test_refresh_g2_post_on_ledger_skip_local_dirs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 383: ledger-skip re-validates local G2 into post-checks."""
    import run_g2_smoke as mod

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    (tmp_path / "runs").mkdir(parents=True)
    docs = tmp_path / "docs"
    docs.mkdir()

    run_dir = tmp_path / "runs" / "run_1300"
    agent = run_dir / "gen_1" / "agent_0"
    agent.mkdir(parents=True)
    (agent / "results.json").write_text('{"accuracy": 0.2}', encoding="utf-8")

    report = mod.PreflightReport(
        timestamp="2026-09-08T12:05:00Z",
        mode="live",
        run_id=1300,
        ready_for_live=True,
        ledger_skip=True,
    )
    fake_post = [
        mod.CheckResult("belief_store", True, "ok"),
        mod.CheckResult("nonzero_fitness", True, "best=0.2000 > min=0"),
    ]

    def _fake_validate(path: Path):  # noqa: ANN001
        assert path == run_dir
        return fake_post

    monkeypatch.setattr(mod, "validate_g2_artifacts", _fake_validate)
    post, note = mod.refresh_g2_post_on_ledger_skip(
        report, gate2_report_md=docs / "gate2_report.md"
    )
    assert post is not None
    assert all(c.ok for c in post)
    assert "re-validated local G2" in note
    assert any("re-validated local G2" in n for n in report.notes)


def test_refresh_g2_post_on_ledger_skip_trusts_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 383: no local run → trust live-executed gate2 sidecar post."""
    import run_g2_smoke as mod

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    (tmp_path / "runs").mkdir(parents=True)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "gate2_report.json").write_text(
        json.dumps(
            {
                "mode": "live",
                "run_id": 1300,
                "post": [
                    {"name": "belief_store", "ok": True, "detail": "present"},
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

    report = mod.PreflightReport(
        timestamp="2026-09-08T12:05:00Z",
        mode="live",
        run_id=1300,
        ready_for_live=True,
        ledger_skip=True,
    )
    post, note = mod.refresh_g2_post_on_ledger_skip(
        report, gate2_report_md=docs / "gate2_report.md"
    )
    assert post is not None
    assert len(post) == 2
    assert all(c.ok for c in post)
    assert "trusted live-executed gate2 sidecar" in note


def test_refresh_g2_post_on_ledger_skip_refuses_preflight_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 383: preflight sidecar must not invent G2 post on ledger-skip."""
    import run_g2_smoke as mod

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    (tmp_path / "runs").mkdir(parents=True)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "gate2_report.json").write_text(
        json.dumps(
            {
                "mode": "preflight",
                "run_id": 1300,
                "post": [],
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate2_report.md").write_text("# Gate 2\n", encoding="utf-8")

    report = mod.PreflightReport(
        timestamp="2026-09-08T12:05:00Z",
        mode="live",
        run_id=1300,
        ready_for_live=True,
        ledger_skip=True,
    )
    post, note = mod.refresh_g2_post_on_ledger_skip(
        report, gate2_report_md=docs / "gate2_report.md"
    )
    assert post is None
    assert "post-checks not updated" in note


def test_g2_live_ledger_skip_refreshes_post(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 383: direct --live ledger-skip calls post refresh (no sia)."""
    import run_g2_smoke as mod

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
                "spent_usd": 1.5,
                "stages_complete": ["G2"],
                "run_ids": [1300],
                "detail": "prior G2",
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate2_report.json").write_text(
        json.dumps(
            {
                "mode": "live",
                "run_id": 1300,
                "post": [
                    {"name": "belief_store", "ok": True, "detail": "present"},
                    {
                        "name": "nonzero_fitness",
                        "ok": True,
                        "detail": "best=0.2500 > min=0",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    task.mkdir(parents=True)
    prepare_task_tree(task, n=5)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    monkeypatch.setattr(mod, "probe_per_run_venv_capable", lambda **_k: (True, "ok"))
    monkeypatch.setattr(mod, "ensure_icml_runtime_deps", lambda **_k: (True, "ok"))
    monkeypatch.setattr(mod, "probe_icml_meta_profile", lambda: (True, "ok"))
    monkeypatch.setattr(mod, "probe_icml_target_profile_nebius", lambda: (True, "ok"))
    monkeypatch.setattr(
        mod,
        "write_icml_tip_status",
        lambda *a, **k: {"tip_ok_for_live": True, "local_tick": 383},
    )

    called: list[list[str]] = []

    def _fake_run(cmd, **_kwargs):
        called.append(list(cmd))

        class _P:
            returncode = 0

        return _P()

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)

    report_path = docs / "gate2_report.md"
    rc = mod.main(
        [
            "--live",
            "--run-id",
            "1300",
            "--report",
            str(report_path),
            "--cwd",
            str(tmp_path),
        ]
    )
    assert rc == 0
    assert called == []
    text = report_path.read_text(encoding="utf-8")
    assert "Tick 383" in text
    assert "nonzero_fitness" in text
    sidecar = json.loads(report_path.with_suffix(".json").read_text(encoding="utf-8"))
    assert sidecar["post"]
    assert any(c["name"] == "nonzero_fitness" and c["ok"] for c in sidecar["post"])


def test_write_gate2_preflight_preserves_prior_live_post(tmp_path: Path) -> None:
    """Tick 384: preflight rewrite keeps prior_live_post for pipeline trust."""
    import run_g2_smoke as mod

    report_md = tmp_path / "gate2_report.md"
    sidecar = report_md.with_suffix(".json")
    live_post = [
        {"name": "belief_store", "ok": True, "detail": "present"},
        {"name": "nonzero_fitness", "ok": True, "detail": "best=0.2 > min=0"},
    ]
    sidecar.write_text(
        json.dumps({"mode": "live", "run_id": 1300, "post": live_post}),
        encoding="utf-8",
    )
    report = mod.PreflightReport(
        timestamp="2026-09-08T14:00:00Z",
        mode="preflight",
        run_id=1300,
        ready_for_live=False,
        ready_for_dry_run=True,
        blockers=["nebius_key"],
        checks=[],
        command=["sia", "run"],
        notes=[],
    )
    mod.write_gate2_report(report, report_md, post=None)
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["mode"] == "preflight"
    assert data["post"] == []
    assert data["prior_live_post"]
    assert any(c["name"] == "nonzero_fitness" and c["ok"] for c in data["prior_live_post"])
    # Trust path still finds the preserved post.
    post, source = mod._live_post_from_gate2_sidecar(data)
    assert source == "prior_live_post"
    assert post and all(c.ok for c in post)


def test_write_gate2_dry_run_does_not_stamp_prior_live_post(tmp_path: Path) -> None:
    """Tick 405: dry-run post must not become prior_live_post (G2→G3 poison)."""
    from dataclasses import asdict as dc_asdict

    import run_g2_smoke as mod

    report_md = tmp_path / "gate2_report.md"
    dry_post = [
        mod.CheckResult(name="belief_store", ok=True, detail="present"),
        mod.CheckResult(name="nonzero_fitness", ok=True, detail="best=0.2 > min=0"),
    ]
    report = mod.PreflightReport(
        timestamp="2026-09-10T08:00:00Z",
        mode="dry-run",
        run_id=1952,
        ready_for_live=False,
        ready_for_dry_run=True,
        blockers=[],
        checks=[],
        command=["sia", "run", "--dry-run"],
        notes=[],
    )
    mod.write_gate2_report(report, report_md, post=dry_post)
    data = json.loads(report_md.with_suffix(".json").read_text(encoding="utf-8"))
    assert data["mode"] == "dry-run"
    assert data["post"]
    assert "prior_live_post" not in data

    # Polluted dry-run sidecar must be scrubbed on rewrite.
    report_md.with_suffix(".json").write_text(
        json.dumps(
            {
                "mode": "dry-run",
                "run_id": 1952,
                "post": [dc_asdict(c) for c in dry_post],
                "prior_live_post": [
                    {"name": "nonzero_fitness", "ok": True, "detail": "poison"}
                ],
            }
        ),
        encoding="utf-8",
    )
    mod.write_gate2_report(report, report_md, post=dry_post)
    scrubbed = json.loads(report_md.with_suffix(".json").read_text(encoding="utf-8"))
    assert "prior_live_post" not in scrubbed


def test_g2_live_ledger_skip_refuses_without_post(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 384: ledger-skip without trustable post → exit 4 (no false-green)."""
    import run_g2_smoke as mod

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
                "spent_usd": 1.5,
                "stages_complete": ["G2"],
                "run_ids": [1300],
                "detail": "prior G2",
            }
        ),
        encoding="utf-8",
    )
    # Preflight-only sidecar — no live post / prior_live_post.
    (docs / "gate2_report.json").write_text(
        json.dumps({"mode": "preflight", "run_id": 1300, "post": []}),
        encoding="utf-8",
    )

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    task.mkdir(parents=True)
    prepare_task_tree(task, n=5)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_task_dir", lambda root_name="SIA": task)
    monkeypatch.setattr(mod, "_runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(mod, "_sia_runs_dir", lambda: tmp_path / "SIA" / "runs")
    monkeypatch.setattr(mod, "probe_per_run_venv_capable", lambda **_k: (True, "ok"))
    monkeypatch.setattr(mod, "ensure_icml_runtime_deps", lambda **_k: (True, "ok"))
    monkeypatch.setattr(mod, "probe_icml_meta_profile", lambda: (True, "ok"))
    monkeypatch.setattr(mod, "probe_icml_target_profile_nebius", lambda: (True, "ok"))
    monkeypatch.setattr(
        mod,
        "write_icml_tip_status",
        lambda *a, **k: {"tip_ok_for_live": True, "local_tick": 384},
    )
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("sia must not run")),
    )

    report_path = docs / "gate2_report.md"
    rc = mod.main(
        [
            "--live",
            "--run-id",
            "1300",
            "--report",
            str(report_path),
            "--cwd",
            str(tmp_path),
        ]
    )
    assert rc == 4


def _steering_lift_pass_post() -> list[dict]:
    return [
        {"name": "run_dir", "ok": True, "detail": "/tmp/run_1955"},
        {
            "name": "delay_all_feedback_skip",
            "ok": True,
            "detail": "gen2 n=2 feedback prompts lack agenda",
        },
        {
            "name": "delay_all_technique_seeds_skip",
            "ok": True,
            "detail": "gen2 n=2 DNA technique_seeds empty",
        },
        {
            "name": "steering_applied_gen3",
            "ok": True,
            "detail": "Condition D n=1 gen≥3 steering evidenced",
        },
        {"name": "nonzero_fitness", "ok": True, "detail": "best=0.2440 > min=0"},
    ]


def test_steering_lift_proof_roundtrip_and_bootstrap(tmp_path: Path) -> None:
    """Tick 510: durable proof sidecar + gate2 dry-run bootstrap."""
    import run_g2_smoke as mod

    docs = tmp_path / "docs"
    docs.mkdir()
    post = _steering_lift_pass_post()
    assert mod.post_checks_satisfy_steering_lift(post)[0] is True

    path = mod.write_steering_lift_proof(
        run_id=1955,
        post=post,
        source="unit",
        repo_root=tmp_path,
    )
    assert path.name == mod.STEERING_LIFT_PROOF_NAME
    ok, detail = mod.steering_lift_proof_ok(tmp_path)
    assert ok is True
    assert "1955" in detail

    # Bootstrap from gate2_report when durable proof missing
    path.unlink()
    assert mod.steering_lift_proof_ok(tmp_path)[0] is False
    (docs / "gate2_report.json").write_text(
        json.dumps(
            {
                "timestamp": "2026-10-02T16:08:15Z",
                "mode": "dry-run",
                "run_id": 1955,
                "post": post,
            }
        ),
        encoding="utf-8",
    )
    boot_ok, boot_detail = mod.maybe_bootstrap_steering_lift_proof_from_gate2(tmp_path)
    assert boot_ok is True
    assert mod.steering_lift_proof_ok(tmp_path)[0] is True
    assert "1955" in boot_detail


def test_write_steering_lift_proof_stamps_explicit_or_progress_tick(
    tmp_path: Path,
) -> None:
    """Tick 513: durable proof tick must not stay frozen at 510 forever."""
    import run_g2_smoke as mod

    docs = tmp_path / "docs"
    docs.mkdir()
    post = _steering_lift_pass_post()

    path = mod.write_steering_lift_proof(
        run_id=1957,
        post=post,
        source="unit",
        repo_root=tmp_path,
        tick=513,
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["tick"] == 513
    assert data["run_id"] == 1957

    (docs / "ICML_PROGRESS.md").write_text(
        "## 2026-10-03T00:04Z — Tick 512 (automation cron)\n",
        encoding="utf-8",
    )
    path2 = mod.write_steering_lift_proof(
        run_id=1957,
        post=post,
        source="unit",
        repo_root=tmp_path,
    )
    data2 = json.loads(path2.read_text(encoding="utf-8"))
    assert data2["tick"] == 512


def test_ensure_steering_lift_proof_without_autorun_uses_durable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tick 510: ensure trusts durable sidecar; does not invoke sia."""
    import run_g2_smoke as mod

    docs = tmp_path / "docs"
    docs.mkdir()
    mod.write_steering_lift_proof(
        run_id=1955,
        post=_steering_lift_pass_post(),
        source="unit",
        repo_root=tmp_path,
    )
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        mod,
        "main",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("sia must not run")),
    )
    ok, detail = mod.ensure_g2_steering_lift_proof(
        repo_root=tmp_path, auto_run=True
    )
    assert ok is True
    assert "durable" in detail


def test_steering_lift_proof_ok_when_local_run_dir_gone(tmp_path: Path) -> None:
    """Tick 514: vanished gitignored runs/ must not invalidate durable proof."""
    import run_g2_smoke as mod

    docs = tmp_path / "docs"
    docs.mkdir()
    mod.write_steering_lift_proof(
        run_id=1957,
        post=_steering_lift_pass_post(),
        source="unit",
        repo_root=tmp_path,
        tick=514,
    )
    data = json.loads(
        (docs / mod.STEERING_LIFT_PROOF_NAME).read_text(encoding="utf-8")
    )
    assert data["ok"] is True
    assert data["local_run_present"] is False
    assert data["vm_ephemeral_safe"] is True

    ok, detail = mod.steering_lift_proof_ok(tmp_path)
    assert ok is True
    assert "1957" in detail
    assert "durable JSON authoritative" in detail

    flag_ok, flag_detail = mod.refresh_steering_lift_proof_local_run_flag(
        tmp_path, tick=514
    )
    assert flag_ok is True
    assert "local absent" in flag_detail or "VM-ephemeral-safe" in flag_detail
    refreshed = json.loads(
        (docs / mod.STEERING_LIFT_PROOF_NAME).read_text(encoding="utf-8")
    )
    assert refreshed["local_run_present"] is False
    assert refreshed["tick"] == 514


def test_ensure_steering_lift_does_not_autorun_when_only_run_dir_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tick 514: cold boot with JSON-only proof must not invent a new dry-run."""
    import run_g2_smoke as mod

    docs = tmp_path / "docs"
    docs.mkdir()
    mod.write_steering_lift_proof(
        run_id=1957,
        post=_steering_lift_pass_post(),
        source="unit",
        repo_root=tmp_path,
        tick=513,
    )
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        mod,
        "main",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not auto dry-run")),
    )
    ok, detail = mod.ensure_g2_steering_lift_proof(
        repo_root=tmp_path, auto_run=True
    )
    assert ok is True
    assert "durable" in detail
    data = json.loads(
        (docs / mod.STEERING_LIFT_PROOF_NAME).read_text(encoding="utf-8")
    )
    assert data["local_run_present"] is False
    assert data["vm_ephemeral_safe"] is True
    assert data["run_id"] == 1957  # must not invent 1958+


def test_write_gate2_report_persists_steering_lift_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tick 510: dry-run write_gate2_report also stamps durable lift proof."""
    import run_g2_smoke as mod

    docs = tmp_path / "docs"
    docs.mkdir()
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        mod, "persist_prior_live_stash_from_working_tree", lambda *_a, **_k: None
    )
    report = mod.PreflightReport(
        timestamp="2026-10-02T18:00:00Z",
        mode="dry-run",
        run_id=1956,
        ready_for_dry_run=True,
    )
    report.command = ["python3", "-m", "sia", "run", "--dry-run"]
    post = [
        mod.CheckResult(c["name"], c["ok"], c["detail"])
        for c in _steering_lift_pass_post()
    ]
    mod.write_gate2_report(report, docs / "gate2_report.md", post=post)
    ok, detail = mod.steering_lift_proof_ok(tmp_path)
    assert ok is True
    assert "1956" in detail


def test_post_checks_accept_foreign_checkresult_dataclass() -> None:
    """Tick 512: G3 CheckResult rows must count toward steering-lift proof.

    ``validate_g3_d_steering`` returns ``run_g3_pilot.CheckResult``. Dropping
    those rows left durable proof stuck on bootstrap ``run_1955`` after a PASS
    dry-run ``run_1956``.
    """
    from dataclasses import dataclass

    import run_g2_smoke as mod

    @dataclass
    class ForeignCheckResult:
        name: str
        ok: bool
        detail: str

    post = [
        mod.CheckResult("run_dir", True, "/tmp/run_1956"),
        mod.CheckResult(
            "delay_all_feedback_skip", True, "gen2 n=2 feedback prompts lack agenda"
        ),
        mod.CheckResult(
            "delay_all_technique_seeds_skip",
            True,
            "gen2 n=2 DNA technique_seeds empty",
        ),
        # Foreign class — historically dropped by isinstance(local CheckResult).
        ForeignCheckResult(
            "steering_applied_run_1956",
            True,
            "gen3 n=2 agenda in ['agent_0', 'agent_1']",
        ),
        ForeignCheckResult(
            "steering_applied_gen3",
            True,
            "Condition D n=1 gen≥3 steering evidenced",
        ),
        mod.CheckResult("nonzero_fitness", True, "best=0.2440 > min=0"),
    ]
    ok, detail = mod.post_checks_satisfy_steering_lift(post)
    assert ok is True, detail
    names = [c["name"] for c in mod._post_as_check_dicts(post)]
    assert "steering_applied_gen3" in names
    assert "steering_applied_run_1956" in names


def test_write_gate2_report_refreshes_proof_with_foreign_gen3_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tick 512: dry-run report with mixed CheckResult classes refreshes proof."""
    from dataclasses import dataclass

    import run_g2_smoke as mod

    @dataclass
    class ForeignCheckResult:
        name: str
        ok: bool
        detail: str

    docs = tmp_path / "docs"
    docs.mkdir()
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        mod, "persist_prior_live_stash_from_working_tree", lambda *_a, **_k: None
    )
    # Stale bootstrap proof must be overwritten by dry-run write.
    mod.write_steering_lift_proof(
        run_id=1955,
        post=_steering_lift_pass_post(),
        source="bootstrap_stale",
        repo_root=tmp_path,
    )
    report = mod.PreflightReport(
        timestamp="2026-10-02T22:04:56Z",
        mode="dry-run",
        run_id=1956,
        ready_for_dry_run=True,
    )
    report.command = ["python3", "-m", "sia", "run", "--dry-run", "--max_gen", "3"]
    post = [
        mod.CheckResult("run_dir", True, "/tmp/run_1956"),
        mod.CheckResult(
            "delay_all_feedback_skip", True, "gen2 n=2 feedback prompts lack agenda"
        ),
        mod.CheckResult(
            "delay_all_technique_seeds_skip",
            True,
            "gen2 n=2 DNA technique_seeds empty",
        ),
        ForeignCheckResult(
            "steering_applied_gen3",
            True,
            "Condition D n=1 gen≥3 steering evidenced",
        ),
        mod.CheckResult("nonzero_fitness", True, "best=0.2440 > min=0"),
    ]
    mod.write_gate2_report(report, docs / "gate2_report.md", post=post)
    ok, detail = mod.steering_lift_proof_ok(tmp_path)
    assert ok is True, detail
    assert "1956" in detail
    payload = json.loads((docs / mod.STEERING_LIFT_PROOF_NAME).read_text(encoding="utf-8"))
    assert payload["run_id"] == 1956
    assert payload["source"] == "gate2_dry_run_write"


def test_repo_relative_detail_rewrites_absolute_in_repo_paths(tmp_path: Path) -> None:
    """Tick 523: absolute in-repo paths become repo-relative; prose unchanged."""
    import run_g2_smoke as mod

    root = Path(__file__).resolve().parents[1]
    abs_run = root / "SIA" / "runs" / "run_1957"
    got = mod._repo_relative_detail(abs_run, repo_root=root)
    assert got == "SIA/runs/run_1957"
    assert not got.startswith("/")
    assert mod._repo_relative_detail("present", repo_root=root) == "present"
    assert (
        mod._repo_relative_detail("best=0.2440 > min=0", repo_root=root)
        == "best=0.2440 > min=0"
    )
    outside = tmp_path / "elsewhere" / "run_x"
    outside.parent.mkdir(parents=True)
    assert mod._repo_relative_detail(outside, repo_root=root) == str(outside)


def test_validate_g2_belief_store_detail_repo_relative(tmp_path: Path) -> None:
    """Tick 523: belief_store post detail is repo-relative when under REPO_ROOT."""
    import run_g2_smoke as mod

    # Place run under real repo so relative_to(REPO_ROOT) succeeds.
    run_dir = mod.REPO_ROOT / "SIA" / "runs" / "run_1958_tick523_unit"
    store = run_dir / "belief_store"
    store.mkdir(parents=True, exist_ok=True)
    try:
        (store / "epistemic_value.jsonl").write_text(
            json.dumps({"generation": 1, "epistemic_value": 1.0}) + "\n",
            encoding="utf-8",
        )
        (store / "contradictions.json").write_text("[]\n", encoding="utf-8")
        (store / "beliefs.json").write_text("[]\n", encoding="utf-8")
        _write_fair_gen2_agent(run_dir)
        checks = {c.name: c for c in validate_g2_artifacts(run_dir)}
        assert checks["belief_store"].ok
        detail = checks["belief_store"].detail
        assert detail == "SIA/runs/run_1958_tick523_unit/belief_store"
        assert "/workspace" not in detail
    finally:
        import shutil

        shutil.rmtree(run_dir, ignore_errors=True)


def test_write_steering_lift_proof_normalizes_absolute_post_paths(
    tmp_path: Path,
) -> None:
    """Tick 523: durable lift proof rewrites absolute run_dir/belief_store details."""
    import run_g2_smoke as mod

    docs = tmp_path / "docs"
    docs.mkdir()
    root = Path(__file__).resolve().parents[1]
    abs_run = str(root / "SIA" / "runs" / "run_1957")
    abs_store = str(root / "SIA" / "runs" / "run_1957" / "belief_store")
    post = [
        {"name": "run_dir", "ok": True, "detail": abs_run},
        {"name": "belief_store", "ok": True, "detail": abs_store},
        {
            "name": "delay_all_feedback_skip",
            "ok": True,
            "detail": "gen2 n=2 feedback prompts lack agenda",
        },
        {
            "name": "delay_all_technique_seeds_skip",
            "ok": True,
            "detail": "gen2 n=2 DNA technique_seeds empty",
        },
        {
            "name": "steering_applied_gen3",
            "ok": True,
            "detail": "Condition D n=1 gen≥3 steering evidenced",
        },
        {"name": "nonzero_fitness", "ok": True, "detail": "best=0.2440 > min=0"},
    ]
    path = mod.write_steering_lift_proof(
        run_id=1957,
        post=post,
        source="unit_tick523",
        repo_root=tmp_path,
        tick=523,
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    by_name = {row["name"]: row["detail"] for row in data["post"]}
    assert by_name["run_dir"] == "SIA/runs/run_1957"
    assert by_name["belief_store"] == "SIA/runs/run_1957/belief_store"
    assert "/workspace" not in by_name["run_dir"]
    assert by_name["nonzero_fitness"] == "best=0.2440 > min=0"


def test_refresh_steering_lift_proof_rewrites_absolute_paths(tmp_path: Path) -> None:
    """Tick 523: cold-boot refresh sanitizes absolute paths without a new dry-run."""
    import run_g2_smoke as mod

    docs = tmp_path / "docs"
    docs.mkdir()
    root = Path(__file__).resolve().parents[1]
    abs_run = str(root / "SIA" / "runs" / "run_1957")
    payload = {
        "timestamp": "2026-10-03T14:03:47Z",
        "tick": 522,
        "source": "gate2_dry_run_write",
        "mode": "dry-run",
        "run_id": 1957,
        "max_gen": 3,
        "ok": True,
        "detail": "delay-all skip + gen≥3 lift",
        "post": [
            {"name": "run_dir", "ok": True, "detail": abs_run},
            {
                "name": "belief_store",
                "ok": True,
                "detail": abs_run + "/belief_store",
            },
            {
                "name": "delay_all_feedback_skip",
                "ok": True,
                "detail": "gen2 n=2 feedback prompts lack agenda",
            },
            {
                "name": "delay_all_technique_seeds_skip",
                "ok": True,
                "detail": "gen2 n=2 DNA technique_seeds empty",
            },
            {
                "name": "steering_applied_gen3",
                "ok": True,
                "detail": "Condition D n=1 gen≥3 steering evidenced",
            },
            {"name": "nonzero_fitness", "ok": True, "detail": "best=0.2440 > min=0"},
        ],
        "required_checks": list(mod.STEERING_LIFT_REQUIRED_CHECKS),
        "local_run_present": True,
        "vm_ephemeral_safe": True,
    }
    (docs / mod.STEERING_LIFT_PROOF_NAME).write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    ok, detail = mod.refresh_steering_lift_proof_local_run_flag(tmp_path, tick=523)
    assert ok is True, detail
    data = json.loads(
        (docs / mod.STEERING_LIFT_PROOF_NAME).read_text(encoding="utf-8")
    )
    assert data["tick"] == 523
    assert data["local_run_present"] is False
    by_name = {row["name"]: row["detail"] for row in data["post"]}
    assert by_name["run_dir"] == "SIA/runs/run_1957"
    assert "/workspace" not in json.dumps(data["post"])
