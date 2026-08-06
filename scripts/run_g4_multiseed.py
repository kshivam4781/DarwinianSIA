#!/usr/bin/env python3
"""ICML Gate G4 — sequential 5-seed Condition B vs D runner + paper pack refresh.

Section 21.5 Gate G4: full 5-seed B vs D under budget; compute PRIMARY + H2 + H5;
refresh ``docs/paper_artifacts.md`` live tables when pairs complete.

Hard stops (never violate):
  - exactly 5 seeds (G3 is 1–2; do not mix)
  - no two GPQA jobs in parallel (B then D, sequential per seed)
  - ``--live`` requires ANTHROPIC_API_KEY + NEBIUS_API_KEY
  - ``--live`` refuses synthetic smoke GPQA answers
  - refuses existing run IDs (never overwrite)
  - respects ``SIA_BUDGET_SPENT_USD`` / ``SIA_BUDGET_CEILING_USD`` (~$20)
  - projects spend: ``SIA_G4_PAIR_ESTIMATE_USD`` × 5 ≤ remaining budget

Modes:
  --preflight-only   check blockers; write docs/gate4_report.md
  --live             paid sequential B then D × 5 seeds (keys + non-smoke GPQA)

Examples:
  python scripts/run_g4_multiseed.py --preflight-only
  python scripts/run_g4_multiseed.py --live \\
    --seeds 1,2,3,4,5 --b-run-ids 1211,1212,1213,1214,1215 \\
    --d-run-ids 1311,1312,1313,1314,1315 --fetch-diamond
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
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
from run_g3_pilot import (  # noqa: E402
    CheckResult,
    PilotPlan,
    _budget_ceiling,
    _budget_spent,
    _env_key,
    _run_dir_for,
    _task_dir,
    _utc_now,
    build_sia_command,
    parse_int_list,
    run_sequential_live,
    score_pilot,
)

DEFAULT_BUDGET_CEILING = 20.0
# Slightly tighter than G3 default so 5 pairs fit under $20 when G2/G3 already spent some.
DEFAULT_PAIR_ESTIMATE_USD = 3.0
DEFAULT_SEEDS = (1, 2, 3, 4, 5)
DEFAULT_B_RUN_IDS = (1211, 1212, 1213, 1214, 1215)
DEFAULT_D_RUN_IDS = (1311, 1312, 1313, 1314, 1315)
LIVE_TABLE_MARKER = "### Live GPQA"
LIVE_TABLE_END_MARKER = "## Table 2"


@dataclass
class G4PreflightReport:
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
    primary_pass: bool = False

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.checks.append(CheckResult(name=name, ok=ok, detail=detail))
        if not ok:
            self.blockers.append(f"{name}: {detail}")


def _pair_estimate_usd() -> float:
    raw = (os.environ.get("SIA_G4_PAIR_ESTIMATE_USD") or str(DEFAULT_PAIR_ESTIMATE_USD)).strip()
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_PAIR_ESTIMATE_USD


def build_g4_plans(
    seeds: list[int],
    b_run_ids: list[int],
    d_run_ids: list[int],
) -> list[PilotPlan]:
    if len(seeds) != 5:
        raise ValueError("G4 requires exactly 5 seeds (Section 21.5); use G3 for 1–2 seed pilots")
    if len(b_run_ids) != 5 or len(d_run_ids) != 5:
        raise ValueError("seeds, --b-run-ids, and --d-run-ids must each have length 5")
    plans = [
        PilotPlan(seed=s, b_run_id=b, d_run_id=d)
        for s, b, d in zip(seeds, b_run_ids, d_run_ids)
    ]
    ids = [p.b_run_id for p in plans] + [p.d_run_id for p in plans]
    if len(ids) != len(set(ids)):
        raise ValueError("run IDs must be unique across B and D plans")
    return plans


def run_preflight(
    *,
    mode: str,
    plans: list[PilotPlan],
    pair_estimate_usd: float | None = None,
) -> G4PreflightReport:
    report = G4PreflightReport(timestamp=_utc_now(), mode=mode, plans=list(plans))
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
        else "synthetic smoke fixture detected — fetch real GPQA diamond before paid G4",
    )

    anth = _env_key("ANTHROPIC_API_KEY")
    neb = _env_key("NEBIUS_API_KEY")
    hf = _env_key("HF_TOKEN") or _env_key("HUGGINGFACE_HUB_TOKEN")
    report.add("anthropic_key", bool(anth), "set" if anth else "ANTHROPIC_API_KEY missing")
    report.add("nebius_key", bool(neb), "set" if neb else "NEBIUS_API_KEY missing")
    report.add(
        "hf_token_optional",
        True,
        "set (can fetch gated GPQA when authorized)" if hf else "missing (optional; needed for HF gpqa download)",
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
        + ("" if budget_ok else " — would exceed ceiling; refuse paid G4"),
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
        else f"occupied: {', '.join(occupied)} — pick unused integers",
    )

    report.add(
        "sequential_only",
        True,
        f"{n_pairs} seed pair(s); runner executes B then D serially (no parallel GPQA)",
    )

    if n_pairs != 5:
        report.add("seed_count", False, f"G4 requires exactly 5 seeds; got {n_pairs}")
    else:
        report.add("seed_count", True, "5 seeds (G4 full multi-seed shape)")

    try:
        import venv  # noqa: F401

        report.add("python_venv_module", True, f"{sys.executable} has venv")
    except Exception as exc:  # pragma: no cover
        report.add("python_venv_module", False, f"venv import failed: {exc}")

    by_name = {c.name: c.ok for c in report.checks}
    live_needed = (
        "gpqa_layout",
        "gpqa_not_synthetic",
        "anthropic_key",
        "nebius_key",
        "budget",
        "run_ids_free",
        "seed_count",
        "python_venv_module",
    )
    report.ready_for_live = all(by_name.get(n, False) for n in live_needed)

    for plan in plans:
        report.commands.append(
            build_sia_command(condition="B", run_id=plan.b_run_id, seed=plan.seed)
        )
        report.commands.append(
            build_sia_command(condition="D", run_id=plan.d_run_id, seed=plan.seed)
        )
    return report


def primary_criteria_pass(comparison: dict[str, Any] | None) -> bool:
    """PRIMARY: D beats B on ≥3/5 for gens30, cost30, or non-trivial final wins (≥3)."""
    if not comparison or int(comparison.get("n_pairs") or 0) < 5:
        return False
    if comparison.get("primary_gens30_pass") or comparison.get("primary_cost30_pass"):
        return True
    if comparison.get("primary_gens25_pass") or comparison.get("primary_cost25_pass"):
        return True
    # Criterion (c): non-trivial mean gap via ≥3/5 final wins (>1pp each)
    return int(comparison.get("d_wins_final") or 0) >= 3


def h5_pass_count(h5_by_d_run: dict[str, Any]) -> tuple[int, int]:
    """Return (n_pass, n_total) where pass = Spearman ρ > 0.3."""
    n_pass = 0
    n_total = 0
    for payload in h5_by_d_run.values():
        if not isinstance(payload, dict) or "error" in payload:
            continue
        n_total += 1
        rho = payload.get("spearman_rho")
        if isinstance(rho, (int, float)) and float(rho) > 0.3:
            n_pass += 1
    return n_pass, n_total


def _fmt_num(val: Any, digits: int = 4) -> str:
    if val is None:
        return "—"
    if isinstance(val, float):
        return f"{val:.{digits}f}".rstrip("0").rstrip(".")
    return str(val)


def _cost_cell(cost_payload: Any) -> str:
    if not isinstance(cost_payload, dict):
        return "—"
    cost = cost_payload.get("cost")
    unit = cost_payload.get("unit") or "units"
    if cost is None:
        return "—"
    return f"{_fmt_num(cost, 2)} {unit}"


def render_live_table1_rows(
    plans: list[PilotPlan],
    comparison: dict[str, Any],
) -> list[str]:
    """Markdown table rows for paper_artifacts Live GPQA Table 1."""
    rows_out: list[str] = []
    cmp_rows = comparison.get("rows") or []
    for i, plan in enumerate(plans):
        if i >= len(cmp_rows):
            rows_out.append(
                f"| {plan.seed} | — | — | — | — | — | — | incomplete |"
            )
            continue
        pair = cmp_rows[i]
        b = pair.get("B") or {}
        d = pair.get("D") or {}
        b_final = b.get("final_best")
        d_final = d.get("final_best")
        b_g30 = b.get("gens_to_30")
        d_g30 = d.get("gens_to_30")
        b_cost = _cost_cell(b.get("cost_to_30"))
        d_cost = _cost_cell(d.get("cost_to_30"))
        winners: list[str] = []
        if isinstance(d_final, (int, float)) and isinstance(b_final, (int, float)):
            if d_final > b_final + 0.01:
                winners.append("D_final")
            elif b_final > d_final + 0.01:
                winners.append("B_final")
            else:
                winners.append("tie_final")
        if d_g30 is not None and (b_g30 is None or (isinstance(b_g30, int) and d_g30 < b_g30)):
            winners.append("D_gens30")
        elif b_g30 is not None and (d_g30 is None or (isinstance(d_g30, int) and b_g30 < d_g30)):
            winners.append("B_gens30")
        rows_out.append(
            "| {seed} | {bf} | {df} | {bg} | {dg} | {bc} | {dc} | {w} |".format(
                seed=plan.seed,
                bf=_fmt_num(b_final),
                df=_fmt_num(d_final),
                bg=_fmt_num(b_g30, 0) if b_g30 is not None else "—",
                dg=_fmt_num(d_g30, 0) if d_g30 is not None else "—",
                bc=b_cost,
                dc=d_cost,
                w=", ".join(winners) if winners else "—",
            )
        )
    return rows_out


def refresh_paper_artifacts_live(
    *,
    docs_path: Path,
    plans: list[PilotPlan],
    comparison: dict[str, Any],
    h5_by_d_run: dict[str, Any],
    timestamp: str,
) -> bool:
    """Replace the Live GPQA stub table in paper_artifacts.md with scored rows."""
    if not docs_path.is_file():
        return False
    text = docs_path.read_text(encoding="utf-8")
    start = text.find(LIVE_TABLE_MARKER)
    end = text.find(LIVE_TABLE_END_MARKER)
    if start == -1 or end == -1 or end <= start:
        return False

    header = (
        f"{LIVE_TABLE_MARKER}\n\n"
        f"_Auto-filled by `scripts/run_g4_multiseed.py` at {timestamp}_\n\n"
        "| Seed | B final acc | D final acc | B gens@30% | D gens@30% | B cost@30% | D cost@30% | Winner |\n"
        "|------|-------------|-------------|------------|------------|------------|------------|--------|\n"
    )
    body = "\n".join(render_live_table1_rows(plans, comparison)) + "\n"
    summary = (
        f"\nPRIMARY flags: gens30={comparison.get('primary_gens30_pass')} "
        f"cost30={comparison.get('primary_cost30_pass')} "
        f"gens25={comparison.get('primary_gens25_pass')} "
        f"cost25={comparison.get('primary_cost25_pass')}; "
        f"D final wins={comparison.get('d_wins_final')}/"
        f"{comparison.get('n_pairs')}. "
        f"Run IDs B={[p.b_run_id for p in plans]} D={[p.d_run_id for p in plans]}.\n"
    )
    h5_n_pass, h5_n = h5_pass_count(h5_by_d_run)
    h5_line = f"H5 ρ>0.3 on live D runs: **{h5_n_pass}/{h5_n}**.\n\n"
    new_block = header + body + summary + h5_line
    text = text[:start] + new_block + text[end:]

    # Update reproducible run ID live rows if still empty stubs.
    b_ids = ", ".join(str(p.b_run_id) for p in plans)
    d_ids = ", ".join(str(p.d_run_id) for p in plans)
    text = re.sub(
        r"\| B darwinian-only \| — \| — \| none yet \(live\) \|",
        f"| B darwinian-only | {','.join(str(p.seed) for p in plans)} | {b_ids} | **G4 live** |",
        text,
        count=1,
    )
    text = re.sub(
        r"\| D epistemic_full \| — \| — \| none yet \(live\) \|",
        f"| D epistemic_full | {','.join(str(p.seed) for p in plans)} | {d_ids} | **G4 live** |",
        text,
        count=1,
    )

    docs_path.write_text(text, encoding="utf-8")
    return True


def write_gate4_report(
    report: G4PreflightReport,
    out: Path,
    *,
    executed: bool = False,
    paper_refreshed: bool = False,
) -> None:
    plan_rows = [
        f"| {p.seed} | B `{p.b_run_id}` | D `{p.d_run_id}` |" for p in report.plans
    ]
    lines = [
        "# Gate 4 report — 5-seed B vs D",
        "",
        f"**Timestamp:** {report.timestamp}",
        f"**Mode:** `{report.mode}`",
        f"**Live G4 ready:** {'yes' if report.ready_for_live else 'no'}",
        f"**PRIMARY pass (≥3/5):** {'yes' if report.primary_pass else 'no'}",
        "",
        "## Live G4 preflight",
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
        lines.append("## Blockers (live G4)")
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
        h5_pass, h5_n = h5_pass_count(report.h5_by_d_run)
        lines.extend(
            [
                "## Live G4 metrics",
                "",
                f"- Pairs scored: **{cmp_.get('n_pairs', 0)}**",
                f"- D gens30 wins: **{cmp_.get('d_wins_gens30', 0)}** / B: **{cmp_.get('b_wins_gens30', 0)}** "
                f"(PRIMARY gens30={cmp_.get('primary_gens30_pass')})",
                f"- D cost30 wins: **{cmp_.get('d_wins_cost30', 0)}** / B: **{cmp_.get('b_wins_cost30', 0)}** "
                f"(PRIMARY cost30={cmp_.get('primary_cost30_pass')})",
                f"- D final wins (>1pp): **{cmp_.get('d_wins_final', 0)}** / B: **{cmp_.get('b_wins_final', 0)}**",
                f"- H5 ρ>0.3: **{h5_pass}/{h5_n}**",
                f"- PRIMARY aggregate: **{'PASS' if report.primary_pass else 'FAIL'}**",
                f"- paper_artifacts Live table refreshed: **{'yes' if paper_refreshed else 'no'}**",
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
            lines.append(
                "**Live G4 status:** RUN COMPLETE — update `docs/ICML_READY.md` only if "
                "PRIMARY + live H2/H5 + paper pack all pass"
            )
        lines.append("")
    elif executed:
        lines.append("**Live G4 status:** executed but comparison unavailable")
        lines.append("")
    else:
        lines.append(
            "**Live G4 status:** NOT RUN this tick"
            if report.mode == "preflight"
            else "**Live G4 status:** command not executed"
        )
        lines.append("")

    lines.extend(
        [
            "## Next",
            "",
            "1. Ensure live G2 smoke + G3 pilot passed before spending on G4.",
            "2. Add `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` (+ `HF_TOKEN` for `--fetch-diamond`).",
            "3. Budget-check (`SIA_BUDGET_*` + `SIA_G4_PAIR_ESTIMATE_USD`), then:",
            "   `python scripts/run_g4_multiseed.py --live --seeds 1,2,3,4,5 "
            "--b-run-ids 1211,1212,1213,1214,1215 --d-run-ids 1311,1312,1313,1314,1315 --fetch-diamond`",
            "4. If PRIMARY passes, refresh Figs 1–2 from live runs and set `ICML_READY` only when H2/H5/paper also pass.",
            "5. Do **not** set STATUS: READY from offline / G4 preflight alone.",
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
        "primary_pass": report.primary_pass,
        "plans": [asdict(p) for p in report.plans],
        "blockers": report.blockers,
        "checks": [asdict(c) for c in report.checks],
        "commands": report.commands,
        "comparison": report.comparison,
        "h5_by_d_run": report.h5_by_d_run,
        "notes": report.notes,
        "executed": executed,
        "paper_refreshed": paper_refreshed,
    }
    sidecar.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--preflight-only",
        action="store_true",
        help="Only check blockers and write docs/gate4_report.md (default)",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Paid sequential B then D × 5 seeds (keys + real GPQA required)",
    )
    p.add_argument(
        "--seeds",
        type=str,
        default=",".join(str(s) for s in DEFAULT_SEEDS),
        help="Comma-separated seeds (exactly 5; default: 1,2,3,4,5)",
    )
    p.add_argument(
        "--b-run-ids",
        type=str,
        default=",".join(str(i) for i in DEFAULT_B_RUN_IDS),
        help="Comma-separated unused Condition B run IDs (aligned with --seeds)",
    )
    p.add_argument(
        "--d-run-ids",
        type=str,
        default=",".join(str(i) for i in DEFAULT_D_RUN_IDS),
        help="Comma-separated unused Condition D run IDs (aligned with --seeds)",
    )
    p.add_argument("--eval-subset", type=int, default=15)
    p.add_argument("--population-size", type=int, default=4)
    p.add_argument("--elite-count", type=int, default=2)
    p.add_argument("--max-gen", type=int, default=5)
    p.add_argument(
        "--report",
        type=Path,
        default=REPO_ROOT / "docs" / "gate4_report.md",
        help="Markdown report path",
    )
    p.add_argument(
        "--paper-artifacts",
        type=Path,
        default=REPO_ROOT / "docs" / "paper_artifacts.md",
        help="Paper pack path to refresh Live GPQA table after live scoring",
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
    p.add_argument(
        "--skip-paper-refresh",
        action="store_true",
        help="Do not rewrite docs/paper_artifacts.md Live table after scoring",
    )
    args = p.parse_args(argv)

    selected = "live" if args.live else "preflight"
    try:
        seeds = parse_int_list(args.seeds)
        b_ids = parse_int_list(args.b_run_ids)
        d_ids = parse_int_list(args.d_run_ids)
        plans = build_g4_plans(seeds, b_ids, d_ids)
    except ValueError as exc:
        print(f"G4 plan error: {exc}", file=sys.stderr)
        return 2

    if args.max_gen > 5:
        print("G4 refuses max_gen > 5 (Section 21.5 budget shape)", file=sys.stderr)
        return 2

    fetch_notes: list[str] = []
    if args.fetch_diamond or args.diamond_csv is not None:
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
                print(f"G4 live refused — --fetch-diamond failed: {exc}", file=sys.stderr)
                report = run_preflight(mode=selected, plans=plans)
                report.notes.extend(fetch_notes)
                write_gate4_report(report, args.report)
                return 3

    report = run_preflight(mode=selected, plans=plans)
    report.notes.extend(fetch_notes)

    if selected == "preflight":
        write_gate4_report(report, args.report)
        print(f"G4 preflight written → {args.report}")
        print(f"ready_for_live={report.ready_for_live}")
        for b in report.blockers:
            print(f"  BLOCK: {b}")
        return 0

    if not report.ready_for_live:
        write_gate4_report(report, args.report)
        print("G4 live refused — preflight failed", file=sys.stderr)
        for b in report.blockers:
            print(f"  BLOCK: {b}", file=sys.stderr)
        return 3

    # Reuse G3 sequential executor (same hard-stop: never parallel).
    # Adapt report type: run_sequential_live only needs .plans
    class _Compat:
        pass

    compat = _Compat()
    compat.plans = report.plans
    b_dirs, d_dirs, run_notes = run_sequential_live(
        compat,  # type: ignore[arg-type]
        cwd=args.cwd,
        eval_subset=args.eval_subset,
        population_size=args.population_size,
        elite_count=args.elite_count,
        max_gen=args.max_gen,
    )
    report.notes.extend(run_notes)

    paper_refreshed = False
    if b_dirs and d_dirs and len(b_dirs) == len(d_dirs):
        comparison, h5 = score_pilot(b_dirs, d_dirs)
        report.comparison = comparison
        report.h5_by_d_run = h5
        report.primary_pass = primary_criteria_pass(comparison)
        if not args.skip_paper_refresh:
            paper_refreshed = refresh_paper_artifacts_live(
                docs_path=args.paper_artifacts,
                plans=report.plans,
                comparison=comparison,
                h5_by_d_run=h5,
                timestamp=report.timestamp,
            )
            report.notes.append(
                f"paper_artifacts refreshed={paper_refreshed} → {args.paper_artifacts}"
            )
    else:
        report.notes.append("incomplete B/D pairs — skipped compare_b_vs_d / paper refresh")

    write_gate4_report(
        report, args.report, executed=True, paper_refreshed=paper_refreshed
    )
    print(f"G4 report → {args.report}")
    print(f"primary_pass={report.primary_pass}")
    if report.comparison is None:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
