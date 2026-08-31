#!/usr/bin/env python3
"""ICML Gate G3 — sequential Condition B vs D pilot runner.

Section 21.5 Gate G3: pilot B vs D on 1–2 seeds, ``--eval_subset 15``,
``max_gen ≤ 5``, before full 5-seed G4 spend.

Hard stops (never violate):
  - no two GPQA jobs in parallel (B then D, sequential)
  - ``--live`` requires NEBIUS_API_KEY (ANTHROPIC optional under Nebius meta; Tick 289/292)
  - ``--live`` refuses synthetic smoke GPQA answers
  - refuses existing run IDs (never overwrite)
  - respects ``SIA_BUDGET_SPENT_USD`` / ``SIA_BUDGET_CEILING_USD`` (~$20)
  - optional rough spend estimate before launching paid pairs

Modes:
  --preflight-only   check blockers; refresh live section of docs/gate3_report.md
  --live             paid sequential B then D (keys + non-smoke GPQA required)

Examples:
  python scripts/run_g3_pilot.py --preflight-only
  python scripts/run_g3_pilot.py --live --seeds 1 --b-run-ids 1201 --d-run-ids 1301
  python scripts/run_g3_pilot.py --live --seeds 1,2 --fetch-diamond
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from prepare_gpqa_smoke_data import (  # noqa: E402
    check_task_tree,
    is_synthetic_smoke,
)
from prepare_gpqa_diamond import (  # noqa: E402
    materialize_from_csv,
    materialize_from_hf,
)
from epistemic_results import compare_b_vs_d, compute_h5  # noqa: E402
from icml_env_checks import (  # noqa: E402
    autowire_diamond_csv,
    collect_icml_secrets_status,
    ensure_deps_before_diamond_fetch,
    ensure_icml_runtime_deps,
    icml_human_required_secrets_phrase,
    icml_meta_profile_cli_flags,
    icml_meta_requires_anthropic,
    icml_target_profile_cli_flags,
    probe_icml_meta_profile,
    probe_icml_target_profile_nebius,
    probe_per_run_venv_capable,
)

DEFAULT_BUDGET_CEILING = 20.0
# Rough upper bound for one G3-shaped seed pair (B+D): pop4 × eval15 × max_gen5 × 2 conds
DEFAULT_PAIR_ESTIMATE_USD = 4.0
DEFAULT_SEEDS = (1,)
DEFAULT_B_RUN_IDS = (1201,)
DEFAULT_D_RUN_IDS = (1301,)
OFFLINE_MARKER = "<!-- OFFLINE_G3_PILOT_START -->"
OFFLINE_MARKER_END = "<!-- OFFLINE_G3_PILOT_END -->"


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


@dataclass
class PilotPlan:
    seed: int
    b_run_id: int
    d_run_id: int


@dataclass
class G3PreflightReport:
    timestamp: str
    mode: str
    plans: list[PilotPlan] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    ready_for_live: bool = False
    commands: list[list[str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    comparison: dict[str, Any] | None = None
    h5_by_d_run: dict[str, Any] = field(default_factory=dict)

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


def _pair_estimate_usd() -> float:
    raw = (os.environ.get("SIA_G3_PAIR_ESTIMATE_USD") or str(DEFAULT_PAIR_ESTIMATE_USD)).strip()
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_PAIR_ESTIMATE_USD


def _task_dir(root_name: str = "SIA") -> Path:
    return REPO_ROOT / root_name / "sia" / "tasks" / "gpqa"


def _runs_dir() -> Path:
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


def parse_int_list(raw: str) -> list[int]:
    parts = [p.strip() for p in raw.replace(" ", "").split(",") if p.strip()]
    if not parts:
        raise ValueError("empty integer list")
    return [int(p) for p in parts]


def build_plans(
    seeds: list[int],
    b_run_ids: list[int],
    d_run_ids: list[int],
) -> list[PilotPlan]:
    if not (1 <= len(seeds) <= 2):
        raise ValueError("G3 allows 1–2 seeds only (Section 21.5); use G4 for 5-seed")
    if len(b_run_ids) != len(seeds) or len(d_run_ids) != len(seeds):
        raise ValueError("seeds, --b-run-ids, and --d-run-ids must have equal length")
    plans = [
        PilotPlan(seed=s, b_run_id=b, d_run_id=d)
        for s, b, d in zip(seeds, b_run_ids, d_run_ids)
    ]
    ids = [p.b_run_id for p in plans] + [p.d_run_id for p in plans]
    if len(ids) != len(set(ids)):
        raise ValueError("run IDs must be unique across B and D plans")
    return plans


def build_sia_command(
    *,
    condition: str,
    run_id: int,
    seed: int,
    dry_run: bool = False,
    eval_subset: int = 15,
    population_size: int = 4,
    elite_count: int = 2,
    max_gen: int = 5,
) -> list[str]:
    if condition not in {"B", "D"}:
        raise ValueError(f"condition must be B or D, got {condition!r}")
    if max_gen > 5:
        raise ValueError("G3 max_gen must be ≤ 5 (Section 21.5)")
    cmd = _find_sia_python() + [
        "run",
        "--task",
        "gpqa",
        "--darwinian",
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
    if condition == "D":
        cmd.extend(["--cabs", "--cabs-inline"])
    if dry_run:
        cmd.append("--dry-run")
    # Tick 289: Nebius pydantic-ai meta (Anthropic optional).
    cmd.extend(icml_meta_profile_cli_flags())
    # Tick 288: Nebius target profile (not default-target / Tinker seed).
    cmd.extend(icml_target_profile_cli_flags())
    return cmd


def run_preflight(
    *,
    mode: str,
    plans: list[PilotPlan],
    pair_estimate_usd: float | None = None,
    require_hf_for_diamond: bool = False,
) -> G3PreflightReport:
    report = G3PreflightReport(timestamp=_utc_now(), mode=mode, plans=list(plans))
    task = _task_dir("SIA")
    estimate = _pair_estimate_usd() if pair_estimate_usd is None else pair_estimate_usd

    missing = check_task_tree(task)
    report.add(
        "gpqa_layout",
        not missing,
        "ok" if not missing else f"missing: {', '.join(missing)}",
    )

    smoke = is_synthetic_smoke(task) if not missing else True
    report.add(
        "gpqa_not_synthetic",
        (not missing) and (not smoke),
        "real/non-smoke diamond_questions.json present"
        if (not missing and not smoke)
        else "synthetic smoke fixture detected — fetch real GPQA diamond before paid G3",
    )

    anth = _env_key("ANTHROPIC_API_KEY")
    neb = _env_key("NEBIUS_API_KEY")
    hf = _env_key("HF_TOKEN") or _env_key("HUGGINGFACE_HUB_TOKEN")
    # Tick 289: Anthropic required only when meta provider is anthropic.
    need_anth = icml_meta_requires_anthropic()
    if need_anth:
        report.add(
            "anthropic_key",
            bool(anth),
            "set" if anth else "ANTHROPIC_API_KEY missing",
        )
    else:
        report.add(
            "anthropic_key",
            True,
            "optional (Nebius meta; "
            + ("present but unused" if anth else "ANTHROPIC unused")
            + ")",
        )
    report.add("nebius_key", bool(neb), "set" if neb else "NEBIUS_API_KEY missing")
    # Tick 275: --fetch-diamond (no CSV) requires HF; else optional.
    if require_hf_for_diamond:
        report.add(
            "hf_token",
            bool(hf),
            "set"
            if hf
            else "HF_TOKEN / HUGGINGFACE_HUB_TOKEN missing (required for --fetch-diamond)",
        )
    else:
        report.add(
            "hf_token_optional",
            True,
            "set (can fetch gated GPQA when authorized)"
            if hf
            else "missing (optional; needed for HF gpqa download)",
        )

    spent = _budget_spent()
    ceiling = _budget_ceiling()
    n_pairs = len(plans)
    projected = spent + estimate * n_pairs
    budget_ok = spent < ceiling and projected <= ceiling
    report.add(
        "budget",
        budget_ok,
        (
            f"spent=${spent:.2f} ceiling=${ceiling:.2f} "
            f"estimate=${estimate:.2f}/pair × {n_pairs} → projected=${projected:.2f}"
        )
        + ("" if budget_ok else " — would exceed ceiling; refuse paid G3"),
    )

    occupied: list[str] = []
    for plan in plans:
        for rid, label in ((plan.b_run_id, "B"), (plan.d_run_id, "D")):
            existing = _run_dir_for(rid)
            if existing is not None:
                occupied.append(f"{label} run_{rid} @ {existing}")
    report.add(
        "run_ids_free",
        not occupied,
        "all planned run IDs unused"
        if not occupied
        else f"occupied: {'; '.join(occupied)} — pick unused integers",
    )

    # Sequential-only invariant (documentation check — runner never forks)
    report.add(
        "sequential_only",
        True,
        f"{n_pairs} seed pair(s); runner executes B then D serially (no parallel GPQA)",
    )

    if not (1 <= n_pairs <= 2):
        report.add("seed_count", False, f"G3 requires 1–2 seeds; got {n_pairs}")
    else:
        report.add("seed_count", True, f"{n_pairs} seed(s) (G3 pilot shape)")

    # Tick 265: bootstrap Astral uv when missing so Portal Save is not required
    venv_ok, venv_detail = probe_per_run_venv_capable(bootstrap_uv=True)
    report.add("per_run_venv", venv_ok, venv_detail)

    # Tick 266: huggingface_hub + SIA PYTHONPATH without Portal-Saved install
    deps_ok, deps_detail = ensure_icml_runtime_deps(allow_install=True)
    report.add("runtime_deps", deps_ok, deps_detail)

    # Tick 289: Nebius pydantic-ai meta (refuse silent default-meta Anthropic)
    meta_ok, meta_detail = probe_icml_meta_profile()
    report.add("nebius_meta_profile", meta_ok, meta_detail)

    # Tick 288: Nebius target profile (refuse default-target / Tinker latent abort)
    profile_ok, profile_detail = probe_icml_target_profile_nebius()
    report.add("nebius_target_profile", profile_ok, profile_detail)

    by_name = {c.name: c.ok for c in report.checks}
    live_needed_list = [
        "gpqa_layout",
        "gpqa_not_synthetic",
        "anthropic_key",
        "nebius_key",
        "budget",
        "run_ids_free",
        "seed_count",
        "per_run_venv",
        "runtime_deps",
        "nebius_meta_profile",
        "nebius_target_profile",
    ]
    if require_hf_for_diamond:
        live_needed_list.append("hf_token")
    report.ready_for_live = all(by_name.get(n, False) for n in live_needed_list)

    for plan in plans:
        report.commands.append(
            build_sia_command(condition="B", run_id=plan.b_run_id, seed=plan.seed)
        )
        report.commands.append(
            build_sia_command(condition="D", run_id=plan.d_run_id, seed=plan.seed)
        )
    return report


def resolve_run_dir(run_id: int, cwd: Path) -> Path | None:
    found = _run_dir_for(run_id)
    if found is not None:
        return found
    candidate = cwd / "runs" / f"run_{run_id}"
    return candidate if candidate.exists() else None


def score_pilot(b_dirs: list[Path], d_dirs: list[Path]) -> tuple[dict[str, Any], dict[str, Any]]:
    comparison = compare_b_vs_d(b_dirs, d_dirs)
    h5: dict[str, Any] = {}
    for d_dir in d_dirs:
        try:
            h5[d_dir.name] = compute_h5(d_dir)
        except Exception as exc:  # pragma: no cover
            h5[d_dir.name] = {"error": str(exc)}
    return comparison, h5


def _extract_offline_block(existing: str | None) -> str:
    """Preserve prior offline pilot narrative when refreshing the live section."""
    if not existing:
        return (
            f"{OFFLINE_MARKER}\n"
            "## Offline synthetic pilot (not a live G3 substitute)\n\n"
            "See prior ticks / `docs/offline_bvd_summary.json` for offline B vs D "
            "(Tick 23: gens30/cost30 **4/5**, H5 **5/5**, post-steer H2).\n"
            f"{OFFLINE_MARKER_END}\n"
        )
    start = existing.find(OFFLINE_MARKER)
    end = existing.find(OFFLINE_MARKER_END)
    if start != -1 and end != -1:
        return existing[start : end + len(OFFLINE_MARKER_END)] + "\n"
    # Legacy gate3_report without markers: keep the offline section heuristically.
    m = re.search(
        r"(## Offline synthetic pilot[\s\S]*?)(?=\n## Blockers|\n## Live |\n## Prerequisites|\Z)",
        existing,
    )
    if m:
        return f"{OFFLINE_MARKER}\n{m.group(1).rstrip()}\n{OFFLINE_MARKER_END}\n"
    return (
        f"{OFFLINE_MARKER}\n"
        "## Offline synthetic pilot (not a live G3 substitute)\n\n"
        "Prior offline evidence retained in git history / `docs/offline_bvd_summary.json`.\n"
        f"{OFFLINE_MARKER_END}\n"
    )


def write_gate3_report(
    report: G3PreflightReport,
    out: Path,
    *,
    existing_text: str | None = None,
    executed: bool = False,
) -> None:
    if existing_text is None and out.is_file():
        existing_text = out.read_text(encoding="utf-8")
    offline = _extract_offline_block(existing_text)

    plan_rows = [
        f"| {p.seed} | B `{p.b_run_id}` | D `{p.d_run_id}` |" for p in report.plans
    ]
    lines = [
        "# Gate 3 report — Pilot B vs D",
        "",
        f"**Timestamp:** {report.timestamp}",
        f"**Mode:** `{report.mode}`",
        f"**Live G3 ready:** {'yes' if report.ready_for_live else 'no'}",
        "",
        offline.rstrip(),
        "",
        "## Live G3 preflight",
        "",
        "| Check | OK | Detail |",
        "|-------|----|--------|",
    ]
    for c in report.checks:
        lines.append(f"| `{c.name}` | {'yes' if c.ok else 'NO'} | {c.detail} |")

    lines.extend(
        [
            "",
            "### Planned seed pairs",
            "",
            "| Seed | Condition B | Condition D |",
            "|------|-------------|-------------|",
            *plan_rows,
            "",
            "### Planned commands (sequential: B then D per seed; never parallel)",
            "",
        ]
    )
    for i, cmd in enumerate(report.commands, 1):
        lines.append(f"{i}. `{ ' '.join(cmd) }`")
    lines.append("")

    if report.blockers:
        lines.append("## Blockers (live G3)")
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

    if report.comparison is not None:
        cmp_ = report.comparison
        lines.extend(
            [
                "## Live pilot metrics",
                "",
                f"- Pairs scored: **{cmp_.get('n_pairs', 0)}**",
                f"- D gens30 wins: **{cmp_.get('d_wins_gens30', 0)}** / B: **{cmp_.get('b_wins_gens30', 0)}**",
                f"- D cost30 wins: **{cmp_.get('d_wins_cost30', 0)}** / B: **{cmp_.get('b_wins_cost30', 0)}**",
                f"- D final wins (>1pp): **{cmp_.get('d_wins_final', 0)}** / B: **{cmp_.get('b_wins_final', 0)}**",
                "",
                "### H5 (Condition D)",
                "",
            ]
        )
        for name, h5 in report.h5_by_d_run.items():
            rho = h5.get("spearman_rho") if isinstance(h5, dict) else None
            lines.append(f"- `{name}`: Spearman ρ = `{rho}`")
        lines.append("")
        if executed and report.mode == "live":
            lines.append("**Live G3 status:** RUN COMPLETE — inspect metrics before G4")
        lines.append("")
    elif executed:
        lines.append("**Live G3 status:** executed but comparison unavailable")
        lines.append("")
    else:
        lines.append(
            "**Live G3 status:** NOT RUN this tick"
            if report.mode == "preflight"
            else "**Live G3 status:** command not executed"
        )
        lines.append("")

    secrets_line = icml_human_required_secrets_phrase(for_fetch_diamond=True)
    lines.extend(
        [
            "## Next",
            "",
            "1. Ensure live G2 smoke passed (`scripts/run_g2_smoke.py --live ...`).",
            f"2. Add `{secrets_line}` (see `docs/ICML_HUMAN_UNBLOCK.md`).",
            "3. Budget-check, then:",
            "   `python scripts/run_g3_pilot.py --live --seeds 1 --b-run-ids 1201 --d-run-ids 1301 --fetch-diamond`",
            "4. If pilot looks promising, G4 5-seed under remaining budget (never parallel full GPQA).",
            "5. Do **not** set `ICML_READY` STATUS: READY from offline / preflight alone.",
            "",
        ]
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    sidecar = out.with_suffix(".json")
    payload = {
        "timestamp": report.timestamp,
        "mode": report.mode,
        "ready_for_live": report.ready_for_live,
        "plans": [asdict(p) for p in report.plans],
        "blockers": report.blockers,
        "checks": [asdict(c) for c in report.checks],
        "commands": report.commands,
        "comparison": report.comparison,
        "h5_by_d_run": report.h5_by_d_run,
        "notes": report.notes,
        "executed": executed,
    }
    sidecar.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_sequential_live(
    report: G3PreflightReport,
    *,
    cwd: Path,
    eval_subset: int,
    population_size: int,
    elite_count: int,
    max_gen: int,
) -> tuple[list[Path], list[Path], list[str]]:
    """Execute B then D for each seed. Never launches two GPQA jobs at once."""
    env = os.environ.copy()
    env.setdefault("SIA_CABS_ROOT", str(REPO_ROOT))
    b_dirs: list[Path] = []
    d_dirs: list[Path] = []
    notes: list[str] = []

    for plan in report.plans:
        for condition, run_id, bucket in (
            ("B", plan.b_run_id, b_dirs),
            ("D", plan.d_run_id, d_dirs),
        ):
            cmd = build_sia_command(
                condition=condition,
                run_id=run_id,
                seed=plan.seed,
                dry_run=False,
                eval_subset=eval_subset,
                population_size=population_size,
                elite_count=elite_count,
                max_gen=max_gen,
            )
            print(f"G3 live [{condition} seed={plan.seed} run_id={run_id}]:", " ".join(cmd))
            proc = subprocess.run(cmd, cwd=str(cwd), env=env)
            if proc.returncode != 0:
                notes.append(
                    f"{condition} run_{run_id} exited {proc.returncode}; aborting remaining pairs"
                )
                return b_dirs, d_dirs, notes
            run_dir = resolve_run_dir(run_id, cwd)
            if run_dir is None:
                notes.append(f"{condition} run_{run_id} directory missing after sia")
                return b_dirs, d_dirs, notes
            bucket.append(run_dir)
            notes.append(f"{condition} run_{run_id} ok → {run_dir}")
    return b_dirs, d_dirs, notes


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--preflight-only",
        action="store_true",
        help="Only check blockers and refresh docs/gate3_report.md (default)",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Paid sequential B then D pilot (keys + real GPQA required)",
    )
    p.add_argument(
        "--seeds",
        type=str,
        default="1",
        help="Comma-separated seeds (1–2 for G3; default: 1)",
    )
    p.add_argument(
        "--b-run-ids",
        type=str,
        default="1201",
        help="Comma-separated unused Condition B run IDs (aligned with --seeds)",
    )
    p.add_argument(
        "--d-run-ids",
        type=str,
        default="1301",
        help="Comma-separated unused Condition D run IDs (aligned with --seeds)",
    )
    p.add_argument("--eval-subset", type=int, default=15)
    p.add_argument("--population-size", type=int, default=4)
    p.add_argument("--elite-count", type=int, default=2)
    p.add_argument("--max-gen", type=int, default=5)
    p.add_argument(
        "--report",
        type=Path,
        default=REPO_ROOT / "docs" / "gate3_report.md",
        help="Markdown report path (preserves offline pilot block)",
    )
    p.add_argument(
        "--cwd",
        type=Path,
        default=REPO_ROOT / "SIA",
        help="Working directory for sia invocation",
    )
    p.add_argument(
        "--fetch-diamond",
        action="store_true",
        help="Materialize real GPQA diamond before preflight/live (HF or --diamond-csv)",
    )
    p.add_argument("--diamond-csv", type=Path, default=None)
    p.add_argument("--diamond-n", type=int, default=15)
    args = p.parse_args(argv)

    selected = "live" if args.live else "preflight"
    try:
        seeds = parse_int_list(args.seeds)
        b_ids = parse_int_list(args.b_run_ids)
        d_ids = parse_int_list(args.d_run_ids)
        plans = build_plans(seeds, b_ids, d_ids)
    except ValueError as exc:
        print(f"G3 plan error: {exc}", file=sys.stderr)
        return 2

    if args.max_gen > 5:
        print("G3 refuses max_gen > 5 (Section 21.5)", file=sys.stderr)
        return 2

    # Tick 278: auto-wire local diamond CSV under --fetch-diamond (match cron).
    diamond_csv, csv_auto = autowire_diamond_csv(
        args.diamond_csv, fetch_diamond=bool(args.fetch_diamond), repo_root=REPO_ROOT
    )
    args.diamond_csv = diamond_csv
    require_hf = bool(args.fetch_diamond) and args.diamond_csv is None

    # Tick 275/278: refuse --live --fetch-diamond without HF/CSV before materialize.
    if selected == "live" and require_hf:
        secrets_status = collect_icml_secrets_status()
        if not secrets_status.get("fetch_diamond_ok"):
            report = run_preflight(
                mode=selected, plans=plans, require_hf_for_diamond=True
            )
            for b in secrets_status.get("blockers") or [
                "fetch_diamond_ok=false (need "
                + icml_human_required_secrets_phrase(for_fetch_diamond=True)
                + ")"
            ]:
                report.notes.append(f"secrets: {b}")
            report.notes.append(
                "Add HF_TOKEN (+ API keys) per docs/ICML_HUMAN_UNBLOCK.md; "
                "or pass --diamond-csv / drop gpqa_diamond.csv to skip HF."
            )
            write_gate3_report(report, args.report)
            print(
                "G3 refused --live --fetch-diamond "
                f"(fetch_diamond_ok=false) → {args.report}",
                file=sys.stderr,
            )
            for b in report.blockers:
                print(f"  BLOCK: {b}", file=sys.stderr)
            return 4

    fetch_notes: list[str] = []
    if csv_auto and args.diamond_csv is not None:
        fetch_notes.append(
            f"Tick 278: auto-wired --diamond-csv from {args.diamond_csv}"
        )
    if args.fetch_diamond or args.diamond_csv is not None:
        # Tick 282: bootstrap huggingface_hub (+ uv/SIA) BEFORE materialize.
        deps_ok, deps_detail = ensure_deps_before_diamond_fetch(allow_install=True)
        fetch_notes.append(f"runtime deps before diamond: {deps_detail}")
        if not deps_ok and args.diamond_csv is None:
            fetch_notes.append(
                "runtime_deps failed before HF materialize — "
                "cannot import/bootstrap huggingface_hub"
            )
            if selected == "live":
                print(
                    f"G3 live refused — runtime deps before diamond failed: {deps_detail}",
                    file=sys.stderr,
                )
                report = run_preflight(
                    mode=selected, plans=plans, require_hf_for_diamond=require_hf
                )
                report.notes.extend(fetch_notes)
                write_gate3_report(report, args.report)
                return 3
        try:
            if args.diamond_csv is not None:
                wrote = materialize_from_csv(
                    args.diamond_csv,
                    ["SIA", "sia-upstream"],
                    n=args.diamond_n,
                    seed=seeds[0],
                    force=True,
                    repo_root=REPO_ROOT,
                )
                fetch_notes.append(f"materialized diamond from CSV → {wrote}")
            else:
                wrote = materialize_from_hf(
                    ["SIA", "sia-upstream"],
                    n=args.diamond_n,
                    seed=seeds[0],
                    force=True,
                    repo_root=REPO_ROOT,
                )
                fetch_notes.append(f"materialized diamond from HF → {wrote}")
        except Exception as exc:
            fetch_notes.append(f"diamond fetch failed: {exc}")
            if selected == "live":
                print(f"G3 live refused — --fetch-diamond failed: {exc}", file=sys.stderr)
                report = run_preflight(
                    mode=selected, plans=plans, require_hf_for_diamond=require_hf
                )
                report.notes.extend(fetch_notes)
                write_gate3_report(report, args.report)
                return 3

    report = run_preflight(
        mode=selected, plans=plans, require_hf_for_diamond=require_hf
    )
    report.notes.extend(fetch_notes)

    if selected == "preflight":
        write_gate3_report(report, args.report)
        print(f"G3 preflight written → {args.report}")
        print(f"ready_for_live={report.ready_for_live}")
        for b in report.blockers:
            print(f"  BLOCK: {b}")
        return 0

    if not report.ready_for_live:
        write_gate3_report(report, args.report)
        print("G3 live refused — preflight failed", file=sys.stderr)
        for b in report.blockers:
            print(f"  BLOCK: {b}", file=sys.stderr)
        return 3

    b_dirs, d_dirs, run_notes = run_sequential_live(
        report,
        cwd=args.cwd,
        eval_subset=args.eval_subset,
        population_size=args.population_size,
        elite_count=args.elite_count,
        max_gen=args.max_gen,
    )
    report.notes.extend(run_notes)

    if b_dirs and d_dirs and len(b_dirs) == len(d_dirs):
        comparison, h5 = score_pilot(b_dirs, d_dirs)
        report.comparison = comparison
        report.h5_by_d_run = h5
    else:
        report.notes.append("incomplete B/D pairs — skipped compare_b_vs_d")

    write_gate3_report(report, args.report, executed=True)
    print(f"G3 report → {args.report}")
    if report.comparison is None:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
