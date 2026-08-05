#!/usr/bin/env python3
"""ICML Gate G2 preflight + Condition D smoke runner.

Largest remaining ICML gap is live GPQA G2. This script makes the next tick
turnkey and hard-stops unsafe paid runs:

  - missing ANTHROPIC_API_KEY / NEBIUS_API_KEY for --live
  - synthetic smoke GPQA answers for --live (refuse paid eval on fake labels)
  - existing run directory (never overwrite)
  - optional budget ceiling via SIA_BUDGET_SPENT_USD / SIA_BUDGET_CEILING_USD

Modes:
  --preflight-only   check keys/data/run_id; write docs/gate2_report.md; no sia run
  --dry-run          harness Condition D (smoke fixture OK; no API)
  --live             paid G2 smoke (keys + non-smoke GPQA required)

Examples:
  python scripts/run_g2_smoke.py --preflight-only --run-id 1850
  python scripts/run_g2_smoke.py --dry-run --run-id 1850
  python scripts/run_g2_smoke.py --live --run-id 1300 --seed 1
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from prepare_gpqa_smoke_data import (  # noqa: E402
    check_task_tree,
    is_synthetic_smoke,
    prepare_task_tree,
    ensure_shared,
)

DEFAULT_BUDGET_CEILING = 20.0
DEFAULT_LIVE_RUN_ID = 1300
DEFAULT_DRY_RUN_ID = 1850


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


@dataclass
class PreflightReport:
    timestamp: str
    mode: str
    run_id: int
    checks: list[CheckResult] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    ready_for_live: bool = False
    ready_for_dry_run: bool = False
    command: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.checks.append(CheckResult(name=name, ok=ok, detail=detail))
        if not ok:
            self.blockers.append(f"{name}: {detail}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _env_key(name: str) -> str | None:
    val = (os.environ.get(name) or "").strip()
    return val or None


def _budget_spent() -> float:
    raw = (os.environ.get("SIA_BUDGET_SPENT_USD") or "0").strip()
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _budget_ceiling() -> float:
    raw = (os.environ.get("SIA_BUDGET_CEILING_USD") or str(DEFAULT_BUDGET_CEILING)).strip()
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_BUDGET_CEILING


def _task_dir(root_name: str = "SIA") -> Path:
    return REPO_ROOT / root_name / "sia" / "tasks" / "gpqa"


def _runs_dir() -> Path:
    # Prefer monorepo runs/; SIA CLI often uses cwd/runs when invoked from SIA/.
    return REPO_ROOT / "runs"


def _sia_runs_dir() -> Path:
    return REPO_ROOT / "SIA" / "runs"


def _run_dir_for(run_id: int) -> Path | None:
    for base in (_runs_dir(), _sia_runs_dir()):
        path = base / f"run_{run_id}"
        if path.exists():
            return path
    return None


def _find_sia_python() -> list[str]:
    """Return argv prefix to invoke ``sia`` CLI without assuming PATH install."""
    venv_sia = REPO_ROOT / ".venv" / "bin" / "sia"
    if venv_sia.is_file():
        return [str(venv_sia)]
    sia_pkg = REPO_ROOT / "SIA"
    if (sia_pkg / "sia" / "cli.py").is_file():
        return [sys.executable, "-m", "sia"]
    which = shutil.which("sia")
    if which:
        return [which]
    return [sys.executable, "-m", "sia"]


def build_sia_command(
    *,
    run_id: int,
    seed: int,
    dry_run: bool,
    eval_subset: int = 5,
    population_size: int = 2,
    elite_count: int = 1,
    max_gen: int = 2,
) -> list[str]:
    cmd = _find_sia_python() + [
        "run",
        "--task",
        "gpqa",
        "--darwinian",
        "--cabs",
        "--cabs-inline",
        "--population_size",
        str(population_size),
        "--elite_count",
        str(elite_count),
        "--max_gen",
        str(max_gen),
        "--run_id",
        str(run_id),
        "--eval_subset",
        str(eval_subset),
        "--no-web",
        "--seed",
        str(seed),
    ]
    if dry_run:
        cmd.append("--dry-run")
    return cmd


def run_preflight(
    *,
    mode: str,
    run_id: int,
    ensure_smoke_layout: bool = True,
) -> PreflightReport:
    report = PreflightReport(timestamp=_utc_now(), mode=mode, run_id=run_id)
    task = _task_dir("SIA")

    if ensure_smoke_layout and mode in {"preflight", "dry-run"}:
        if check_task_tree(task):
            prepare_task_tree(task, n=5)
            ensure_shared(REPO_ROOT / "SIA")
            report.notes.append("materialized synthetic GPQA smoke fixture under SIA/")

    missing = check_task_tree(task)
    report.add(
        "gpqa_layout",
        not missing,
        "ok" if not missing else f"missing: {', '.join(missing)}",
    )

    smoke = is_synthetic_smoke(task) if not missing else False
    if mode == "live":
        report.add(
            "gpqa_not_synthetic",
            (not missing) and (not smoke),
            "real/non-smoke diamond_questions.json present"
            if (not missing and not smoke)
            else "synthetic smoke fixture detected — replace with real GPQA diamond before paid G2",
        )
    else:
        report.add(
            "gpqa_smoke_or_real",
            not missing,
            ("synthetic smoke OK for dry-run/preflight" if smoke else "non-smoke questions present")
            if not missing
            else "layout missing",
        )

    anth = _env_key("ANTHROPIC_API_KEY")
    neb = _env_key("NEBIUS_API_KEY")
    hf = _env_key("HF_TOKEN") or _env_key("HUGGINGFACE_HUB_TOKEN")
    if mode == "live":
        report.add("anthropic_key", bool(anth), "set" if anth else "ANTHROPIC_API_KEY missing")
        report.add("nebius_key", bool(neb), "set" if neb else "NEBIUS_API_KEY missing")
    else:
        report.add(
            "api_keys_optional",
            True,
            f"ANTHROPIC={'set' if anth else 'missing'}; NEBIUS={'set' if neb else 'missing'} "
            f"(not required for {mode})",
        )
    report.add(
        "hf_token_optional",
        True,
        "set (can fetch gated GPQA when authorized)" if hf else "missing (optional; needed for HF gpqa download)",
    )

    spent = _budget_spent()
    ceiling = _budget_ceiling()
    budget_ok = spent < ceiling
    report.add(
        "budget",
        budget_ok if mode == "live" else True,
        f"spent=${spent:.2f} ceiling=${ceiling:.2f}"
        + ("" if budget_ok else " — at/over ceiling; refuse paid G2"),
    )

    existing = _run_dir_for(run_id)
    report.add(
        "run_id_free",
        existing is None,
        f"run_{run_id} unused"
        if existing is None
        else f"exists at {existing} — pick unused integer (never overwrite)",
    )

    # python3-venv presence (SIA per-run venvs)
    try:
        import venv  # noqa: F401

        report.add("python_venv_module", True, f"{sys.executable} has venv")
    except Exception as exc:  # pragma: no cover
        report.add("python_venv_module", False, f"venv import failed: {exc}")

    report.ready_for_dry_run = all(
        c.ok
        for c in report.checks
        if c.name in {"gpqa_layout", "gpqa_smoke_or_real", "run_id_free", "python_venv_module"}
    )
    live_needed = {
        "gpqa_layout",
        "gpqa_not_synthetic",
        "anthropic_key",
        "nebius_key",
        "budget",
        "run_id_free",
        "python_venv_module",
    }
    report.ready_for_live = all(c.ok for c in report.checks if c.name in live_needed)

    dry = mode != "live"
    report.command = build_sia_command(run_id=run_id, seed=42, dry_run=dry)
    if mode == "live":
        report.command = build_sia_command(run_id=run_id, seed=1, dry_run=False)
    return report


def validate_g2_artifacts(run_dir: Path) -> list[CheckResult]:
    checks: list[CheckResult] = []
    store = run_dir / "belief_store"
    checks.append(
        CheckResult(
            "belief_store",
            store.is_dir(),
            str(store) if store.is_dir() else "missing belief_store/",
        )
    )
    epi = store / "epistemic_value.jsonl"
    epi_ok = epi.is_file() and epi.stat().st_size > 0
    checks.append(
        CheckResult("epistemic_value_jsonl", epi_ok, "present" if epi_ok else "missing/empty")
    )
    contra = store / "contradictions.json"
    beliefs = store / "beliefs.json"

    def _nonempty_json(path: Path) -> bool:
        if not path.is_file():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        if isinstance(data, list):
            return len(data) > 0
        if isinstance(data, dict):
            # common shapes: {"contradictions": [...]} or {"beliefs": [...]}
            for key in ("contradictions", "beliefs", "items"):
                if isinstance(data.get(key), list) and data[key]:
                    return True
            return len(data) > 0
        return False

    has_cabs = _nonempty_json(contra) or _nonempty_json(beliefs)
    checks.append(
        CheckResult(
            "cabs_json",
            has_cabs,
            "contradictions/beliefs present" if has_cabs else "no contradictions/beliefs JSON",
        )
    )

    # Scoped mutation bias after inline analyze (best-effort; import may need SIA on path)
    bias_ok = False
    bias_detail = "skipped (cabs_bridge import failed)"
    try:
        sys.path.insert(0, str(REPO_ROOT / "SIA"))
        from sia.evolution.cabs_bridge import load_mutation_bias  # type: ignore

        bias = load_mutation_bias(str(run_dir))
        bias_ok = isinstance(bias, dict) and any(bias.values())
        bias_detail = f"fields={sorted(bias)}" if bias_ok else f"empty bias dict: {bias}"
    except Exception as exc:  # pragma: no cover
        bias_detail = f"import/load error: {exc}"
    checks.append(CheckResult("scoped_mutation_bias", bias_ok, bias_detail))
    return checks


def write_gate2_report(report: PreflightReport, out: Path, post: list[CheckResult] | None = None) -> None:
    lines = [
        "# Gate 2 report — GPQA smoke (Condition D)",
        "",
        f"**Timestamp:** {report.timestamp}",
        f"**Mode:** `{report.mode}`",
        f"**Run ID:** `{report.run_id}`",
        "",
        "## Preflight checks",
        "",
        "| Check | OK | Detail |",
        "|-------|----|--------|",
    ]
    for c in report.checks:
        lines.append(f"| `{c.name}` | {'yes' if c.ok else 'NO'} | {c.detail} |")

    lines.extend(
        [
            "",
            f"**Ready for dry-run:** {'yes' if report.ready_for_dry_run else 'no'}",
            f"**Ready for live G2:** {'yes' if report.ready_for_live else 'no'}",
            "",
            "## Planned command",
            "",
            "```bash",
            " ".join(report.command),
            "```",
            "",
        ]
    )
    if report.blockers:
        lines.append("## Blockers")
        lines.append("")
        for b in report.blockers:
            lines.append(f"- {b}")
        lines.append("")
    if report.notes:
        lines.append("## Notes")
        lines.append("")
        for n in report.notes:
            lines.append(f"- {n}")
        lines.append("")
    if post is not None:
        lines.extend(
            [
                "## Post-run artifact validation",
                "",
                "| Check | OK | Detail |",
                "|-------|----|--------|",
            ]
        )
        for c in post:
            lines.append(f"| `{c.name}` | {'yes' if c.ok else 'NO'} | {c.detail} |")
        lines.append("")
        g2_pass = all(c.ok for c in post) and report.mode in {"dry-run", "live"}
        if report.mode == "live" and g2_pass:
            lines.append("**G2 live status:** PASS")
        elif report.mode == "dry-run" and g2_pass:
            lines.append("**G2 dry-run harness status:** PASS (not live G2)")
        else:
            lines.append("**G2 status:** FAIL / incomplete")
        lines.append("")
    else:
        lines.append(
            "**G2 live status:** NOT RUN this tick"
            if report.mode == "preflight"
            else "**G2 status:** command not executed"
        )
        lines.append("")

    lines.extend(
        [
            "## Next",
            "",
            "1. Add `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` to the cloud environment.",
            "2. Accept HF access for `Idavidrein/gpqa` and replace synthetic "
            "`diamond_questions.json` (or set `HF_TOKEN` and fetch).",
            "3. Re-run: `python scripts/run_g2_smoke.py --live --run-id <unused>` "
            "after budget check.",
            "4. Only then start live G3 B vs D pilot (Section 21.5).",
            "",
        ]
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Machine-readable sidecar for automation ticks
    sidecar = out.with_suffix(".json")
    payload = {
        "timestamp": report.timestamp,
        "mode": report.mode,
        "run_id": report.run_id,
        "ready_for_live": report.ready_for_live,
        "ready_for_dry_run": report.ready_for_dry_run,
        "blockers": report.blockers,
        "checks": [asdict(c) for c in report.checks],
        "command": report.command,
        "post": [asdict(c) for c in (post or [])],
    }
    sidecar.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--preflight-only",
        action="store_true",
        help="Only check blockers and write docs/gate2_report.md (default)",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Run Condition D harness smoke with --dry-run (no API)",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Run paid G2 smoke (keys + real GPQA required)",
    )
    p.add_argument("--run-id", type=int, default=None, help="Unused integer run id")
    p.add_argument("--seed", type=int, default=None, help="RNG seed (default 42 dry / 1 live)")
    p.add_argument(
        "--report",
        type=Path,
        default=REPO_ROOT / "docs" / "gate2_report.md",
        help="Markdown report path",
    )
    p.add_argument(
        "--cwd",
        type=Path,
        default=REPO_ROOT / "SIA",
        help="Working directory for sia invocation",
    )
    args = p.parse_args(argv)

    if args.live:
        selected = "live"
        run_id = args.run_id if args.run_id is not None else DEFAULT_LIVE_RUN_ID
        seed = args.seed if args.seed is not None else 1
    elif args.dry_run:
        selected = "dry-run"
        run_id = args.run_id if args.run_id is not None else DEFAULT_DRY_RUN_ID
        seed = args.seed if args.seed is not None else 42
    else:
        selected = "preflight"
        run_id = args.run_id if args.run_id is not None else DEFAULT_DRY_RUN_ID
        seed = args.seed if args.seed is not None else 42

    report = run_preflight(mode=selected, run_id=run_id)
    report.command = build_sia_command(
        run_id=run_id, seed=seed, dry_run=(selected != "live")
    )

    if selected == "preflight":
        write_gate2_report(report, args.report)
        print(f"G2 preflight written → {args.report}")
        print(f"ready_for_dry_run={report.ready_for_dry_run} ready_for_live={report.ready_for_live}")
        for b in report.blockers:
            print(f"  BLOCK: {b}")
        # Preflight success means the checker ran; live blockers are expected without keys.
        return 0

    if selected == "dry-run" and not report.ready_for_dry_run:
        write_gate2_report(report, args.report)
        print("G2 dry-run refused — preflight failed", file=sys.stderr)
        return 2
    if selected == "live" and not report.ready_for_live:
        write_gate2_report(report, args.report)
        print("G2 live refused — preflight failed (keys / real GPQA / budget / run_id)", file=sys.stderr)
        for b in report.blockers:
            print(f"  BLOCK: {b}", file=sys.stderr)
        return 3

    cmd = report.command
    print("Running:", " ".join(cmd))
    env = os.environ.copy()
    # Ensure monorepo cabs importable for --cabs-inline
    env.setdefault("SIA_CABS_ROOT", str(REPO_ROOT))
    proc = subprocess.run(cmd, cwd=str(args.cwd), env=env)
    if proc.returncode != 0:
        report.notes.append(f"sia exited {proc.returncode}")
        write_gate2_report(report, args.report)
        return proc.returncode

    run_dir = _run_dir_for(run_id)
    if run_dir is None:
        # CLI may have written under --cwd/runs
        candidate = Path(args.cwd) / "runs" / f"run_{run_id}"
        run_dir = candidate if candidate.exists() else None
    post: list[CheckResult] = []
    if run_dir is None:
        post.append(CheckResult("run_dir", False, f"run_{run_id} not found after sia"))
    else:
        post.append(CheckResult("run_dir", True, str(run_dir)))
        post.extend(validate_g2_artifacts(run_dir))

    write_gate2_report(report, args.report, post=post)
    print(f"G2 report → {args.report}")
    return 0 if all(c.ok for c in post) else 4


if __name__ == "__main__":
    raise SystemExit(main())
