#!/usr/bin/env python3
"""ICML Thesis 1 — one-command live G2 → G3 → G4 pipeline.

After Tick 28 the individual gate runners + G4 paper pack are turnkey, but a
cron tick with freshly injected keys still risked stopping after G2 (or G3)
and wasting a cycle. This orchestrator chains the gates **serially** so one
unblocked tick can reach STATUS: READY.

Hard stops (delegated to gate runners; never violate here either):
  - no two GPQA jobs in parallel
  - no --focus weights / no LawBench
  - refuse without ANTHROPIC_API_KEY + NEBIUS_API_KEY for --live
  - refuse synthetic smoke for --live (fetch real diamond once, n=15)
  - never overwrite existing run IDs
  - project full-stack spend ≤ SIA_BUDGET_CEILING_USD (~$20)
  - update SIA_BUDGET_SPENT_USD between stages from stage estimates

Modes:
  --preflight-only   chain G2/G3/G4 preflights + budget projection; no API
  --live             G2 → (pass) G3 → (promising + budget) G4 paper pack

Examples:
  python scripts/run_icml_live_pipeline.py --preflight-only
  python scripts/run_icml_live_pipeline.py --live --fetch-diamond
  python scripts/run_icml_live_pipeline.py --live --fetch-diamond --stop-after g3
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import run_g2_smoke as g2  # noqa: E402
import run_g3_pilot as g3  # noqa: E402
import run_g4_multiseed as g4  # noqa: E402
from prepare_gpqa_diamond import materialize_from_csv, materialize_from_hf  # noqa: E402

DEFAULT_BUDGET_CEILING = 20.0
DEFAULT_G2_ESTIMATE_USD = 1.0
DEFAULT_G3_PAIR_ESTIMATE_USD = 4.0
DEFAULT_G4_PAIR_ESTIMATE_USD = 3.0

DEFAULT_G2_RUN_ID = 1300
DEFAULT_G3_SEEDS = "1"
DEFAULT_G3_B_IDS = "1201"
DEFAULT_G3_D_IDS = "1301"
DEFAULT_G4_SEEDS = "1,2,3,4,5"
DEFAULT_G4_B_IDS = "1211,1212,1213,1214,1215"
DEFAULT_G4_D_IDS = "1311,1312,1313,1314,1315"


@dataclass
class StageResult:
    name: str
    attempted: bool
    exit_code: int | None = None
    ok: bool = False
    skipped_reason: str | None = None
    detail: str = ""


@dataclass
class PipelineReport:
    timestamp: str
    mode: str
    stages: list[StageResult] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    budget: dict[str, Any] = field(default_factory=dict)
    ready_for_live: bool = False
    g3_promising: bool | None = None
    stopped_after: str | None = None
    icml_ready_status: str | None = None

    def add_stage(self, stage: StageResult) -> None:
        self.stages.append(stage)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def _env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or str(default)).strip()
    try:
        return float(raw)
    except ValueError:
        return default


def g2_estimate_usd() -> float:
    return _env_float("SIA_G2_ESTIMATE_USD", DEFAULT_G2_ESTIMATE_USD)


def g3_pair_estimate_usd() -> float:
    return _env_float("SIA_G3_PAIR_ESTIMATE_USD", DEFAULT_G3_PAIR_ESTIMATE_USD)


def g4_pair_estimate_usd() -> float:
    return _env_float("SIA_G4_PAIR_ESTIMATE_USD", DEFAULT_G4_PAIR_ESTIMATE_USD)


def project_budget(*, g3_pairs: int = 1, g4_pairs: int = 5) -> dict[str, Any]:
    spent = _budget_spent()
    ceiling = _budget_ceiling()
    g2_e = g2_estimate_usd()
    g3_e = g3_pair_estimate_usd() * g3_pairs
    g4_e = g4_pair_estimate_usd() * g4_pairs
    total = g2_e + g3_e + g4_e
    projected = spent + total
    return {
        "spent": spent,
        "ceiling": ceiling,
        "g2_estimate": g2_e,
        "g3_estimate": g3_e,
        "g4_estimate": g4_e,
        "stack_estimate": total,
        "projected": projected,
        "ok": projected <= ceiling + 1e-9,
        "g3_pairs": g3_pairs,
        "g4_pairs": g4_pairs,
    }


def bump_spent(delta: float) -> float:
    """Increment SIA_BUDGET_SPENT_USD so later gate preflights see remaining headroom."""
    new_spent = _budget_spent() + max(0.0, float(delta))
    os.environ["SIA_BUDGET_SPENT_USD"] = f"{new_spent:.4f}"
    return new_spent


def g3_pilot_promising(comparison: dict[str, Any] | None, h5_by_d_run: dict[str, Any]) -> bool:
    """Cheap G3→G4 gate: any PRIMARY-shaped D win on the pilot seed, or H5 ρ>0.3."""
    if comparison:
        for key in (
            "d_wins_gens30",
            "d_wins_gens25",
            "d_wins_cost30",
            "d_wins_cost25",
            "d_wins_final",
        ):
            if int(comparison.get(key) or 0) >= 1:
                return True
        mean_gap = comparison.get("mean_final_gap")
        if isinstance(mean_gap, (int, float)) and float(mean_gap) > 0.01:
            return True
        # Some compare payloads use mean_b / mean_d
        mb = comparison.get("mean_final_b")
        md = comparison.get("mean_final_d")
        if isinstance(mb, (int, float)) and isinstance(md, (int, float)):
            if float(md) - float(mb) > 0.01:
                return True
    for payload in (h5_by_d_run or {}).values():
        if not isinstance(payload, dict) or "error" in payload:
            continue
        rho = payload.get("spearman_rho")
        if isinstance(rho, (int, float)) and float(rho) > 0.3:
            return True
    return False


def _read_icml_ready_status(path: Path) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    m = re.search(r"\*\*STATUS:\s*([A-Z_]+)\*\*", text)
    return m.group(1) if m else None


def _load_gate3_sidecar(report_md: Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    sidecar = report_md.with_suffix(".json")
    if not sidecar.is_file():
        return None, {}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, {}
    return data.get("comparison"), data.get("h5_by_d_run") or {}


def write_pipeline_report(report: PipelineReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# ICML live pipeline report — G2 → G3 → G4",
        "",
        f"**Timestamp:** {report.timestamp}",
        f"**Mode:** `{report.mode}`",
        f"**Ready for live stack:** {'yes' if report.ready_for_live else 'no'}",
        f"**ICML_READY:** {report.icml_ready_status or 'n/a'}",
        "",
        "## Budget projection",
        "",
        "| Item | USD |",
        "|------|-----|",
        f"| spent (env) | {report.budget.get('spent', 0):.2f} |",
        f"| G2 estimate | {report.budget.get('g2_estimate', 0):.2f} |",
        f"| G3 estimate | {report.budget.get('g3_estimate', 0):.2f} |",
        f"| G4 estimate | {report.budget.get('g4_estimate', 0):.2f} |",
        f"| stack estimate | {report.budget.get('stack_estimate', 0):.2f} |",
        f"| projected total | {report.budget.get('projected', 0):.2f} |",
        f"| ceiling | {report.budget.get('ceiling', DEFAULT_BUDGET_CEILING):.2f} |",
        f"| within ceiling | {'yes' if report.budget.get('ok') else 'NO'} |",
        "",
        "## Stages",
        "",
        "| Stage | Attempted | OK | Exit | Detail |",
        "|-------|-----------|----|------|--------|",
    ]
    for s in report.stages:
        detail = s.skipped_reason or s.detail or ""
        lines.append(
            f"| {s.name} | {'yes' if s.attempted else 'no'} | "
            f"{'yes' if s.ok else 'no'} | {s.exit_code if s.exit_code is not None else '—'} | "
            f"{detail} |"
        )
    lines.extend(["", "## G3→G4 gate", ""])
    if report.g3_promising is None:
        lines.append("G3 promising: n/a (G3 not scored this run)")
    else:
        lines.append(f"G3 promising: **{'yes' if report.g3_promising else 'no'}**")
    if report.stopped_after:
        lines.append(f"Stopped after: `{report.stopped_after}`")
    if report.blockers:
        lines.extend(["", "## Blockers", ""])
        for b in report.blockers:
            lines.append(f"- {b}")
    if report.notes:
        lines.extend(["", "## Notes", ""])
        for n in report.notes:
            lines.append(f"- {n}")
    lines.extend(
        [
            "",
            "## Next",
            "",
            "1. Link a Cursor environment and inject `ANTHROPIC_API_KEY` + "
            "`NEBIUS_API_KEY` + `HF_TOKEN` (accepted `Idavidrein/gpqa`).",
            "2. Budget-check, then:",
            "   `python scripts/run_icml_live_pipeline.py --live --fetch-diamond`",
            "3. Do **not** set STATUS: READY from offline / preflight alone.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    sidecar = path.with_suffix(".json")
    sidecar.write_text(
        json.dumps(
            {
                "timestamp": report.timestamp,
                "mode": report.mode,
                "ready_for_live": report.ready_for_live,
                "budget": report.budget,
                "stages": [asdict(s) for s in report.stages],
                "blockers": report.blockers,
                "notes": report.notes,
                "g3_promising": report.g3_promising,
                "stopped_after": report.stopped_after,
                "icml_ready_status": report.icml_ready_status,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _fetch_diamond(
    *,
    diamond_csv: Path | None,
    diamond_n: int,
    seed: int,
) -> list[str]:
    notes: list[str] = []
    if diamond_csv is not None:
        wrote = materialize_from_csv(
            diamond_csv,
            ["SIA", "sia-upstream"],
            n=diamond_n,
            seed=seed,
            force=True,
            repo_root=REPO_ROOT,
        )
        notes.append(f"materialized diamond from CSV → {wrote}")
    else:
        wrote = materialize_from_hf(
            ["SIA", "sia-upstream"],
            n=diamond_n,
            seed=seed,
            force=True,
            repo_root=REPO_ROOT,
        )
        notes.append(f"materialized diamond from HF → {wrote}")
    return notes


def run_preflight_stack(
    report: PipelineReport,
    *,
    g2_run_id: int,
    g3_seeds: str,
    g3_b: str,
    g3_d: str,
    g4_seeds: str,
    g4_b: str,
    g4_d: str,
) -> None:
    """Run G2/G3/G4 preflights (no paid API) and aggregate readiness."""
    # G2
    rc = g2.main(["--preflight-only", "--run-id", str(g2_run_id)])
    report.add_stage(
        StageResult(
            name="G2",
            attempted=True,
            exit_code=rc,
            ok=rc == 0,
            detail="preflight invoked",
        )
    )
    # G3
    rc = g3.main(
        [
            "--preflight-only",
            "--seeds",
            g3_seeds,
            "--b-run-ids",
            g3_b,
            "--d-run-ids",
            g3_d,
        ]
    )
    report.add_stage(
        StageResult(
            name="G3",
            attempted=True,
            exit_code=rc,
            ok=rc == 0,
            detail="preflight invoked",
        )
    )
    # G4
    rc = g4.main(
        [
            "--preflight-only",
            "--seeds",
            g4_seeds,
            "--b-run-ids",
            g4_b,
            "--d-run-ids",
            g4_d,
        ]
    )
    report.add_stage(
        StageResult(
            name="G4",
            attempted=True,
            exit_code=rc,
            ok=rc == 0,
            detail="preflight invoked",
        )
    )

    # Live readiness: keys + non-smoke + budget stack + free IDs (from gate reports).
    g2_json = (REPO_ROOT / "docs" / "gate2_report.json")
    g3_json = (REPO_ROOT / "docs" / "gate3_report.json")
    g4_json = (REPO_ROOT / "docs" / "gate4_report.json")
    ready_flags: list[bool] = []
    for path, label in (
        (g2_json, "G2"),
        (g3_json, "G3"),
        (g4_json, "G4"),
    ):
        if not path.is_file():
            report.blockers.append(f"{label}: missing {path.name}")
            ready_flags.append(False)
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            report.blockers.append(f"{label}: bad sidecar ({exc})")
            ready_flags.append(False)
            continue
        live_ok = bool(data.get("ready_for_live"))
        ready_flags.append(live_ok)
        if not live_ok:
            for b in data.get("blockers") or []:
                report.blockers.append(f"{label}: {b}")
    if not report.budget.get("ok"):
        report.blockers.append(
            f"budget: projected ${report.budget.get('projected', 0):.2f} "
            f"> ceiling ${report.budget.get('ceiling', 0):.2f}"
        )
        ready_flags.append(False)
    report.ready_for_live = all(ready_flags) and bool(report.budget.get("ok"))


def run_live_stack(
    report: PipelineReport,
    *,
    g2_run_id: int,
    g3_seeds: str,
    g3_b: str,
    g3_d: str,
    g4_seeds: str,
    g4_b: str,
    g4_d: str,
    stop_after: str,
    force_g4: bool,
    fetch_diamond: bool,
    diamond_csv: Path | None,
    diamond_n: int,
) -> int:
    """Execute G2→G3→G4 serially. Returns process exit code."""
    if not report.budget.get("ok"):
        report.blockers.append(
            f"budget: projected ${report.budget.get('projected', 0):.2f} "
            f"> ceiling ${report.budget.get('ceiling', 0):.2f} — refuse live stack"
        )
        report.add_stage(
            StageResult(
                name="G2",
                attempted=False,
                ok=False,
                skipped_reason="stack budget projection exceeds ceiling",
            )
        )
        return 3

    if fetch_diamond or diamond_csv is not None:
        try:
            notes = _fetch_diamond(
                diamond_csv=diamond_csv, diamond_n=diamond_n, seed=1
            )
            report.notes.extend(notes)
        except Exception as exc:
            report.blockers.append(f"diamond fetch failed: {exc}")
            report.add_stage(
                StageResult(
                    name="G2",
                    attempted=False,
                    ok=False,
                    skipped_reason=f"diamond fetch failed: {exc}",
                )
            )
            return 3

    # --- G2 ---
    g2_argv = ["--live", "--run-id", str(g2_run_id)]
    # Diamond already materialized above at n=15; do not re-fetch with G2's n=5.
    rc = g2.main(g2_argv)
    g2_ok = rc == 0
    report.add_stage(
        StageResult(
            name="G2",
            attempted=True,
            exit_code=rc,
            ok=g2_ok,
            detail="Condition D smoke",
        )
    )
    if not g2_ok:
        report.blockers.append(f"G2 live failed (exit {rc})")
        report.stopped_after = "G2"
        return rc if rc else 4
    bump_spent(float(report.budget.get("g2_estimate") or g2_estimate_usd()))
    if stop_after == "g2":
        report.stopped_after = "G2"
        report.notes.append("stop-after=g2")
        return 0

    # --- G3 ---
    g3_argv = [
        "--live",
        "--seeds",
        g3_seeds,
        "--b-run-ids",
        g3_b,
        "--d-run-ids",
        g3_d,
    ]
    rc = g3.main(g3_argv)
    g3_ok = rc == 0
    report.add_stage(
        StageResult(
            name="G3",
            attempted=True,
            exit_code=rc,
            ok=g3_ok,
            detail="sequential B then D pilot",
        )
    )
    if not g3_ok:
        report.blockers.append(f"G3 live failed (exit {rc})")
        report.stopped_after = "G3"
        return rc if rc else 4
    bump_spent(float(report.budget.get("g3_estimate") or g3_pair_estimate_usd()))

    comparison, h5 = _load_gate3_sidecar(REPO_ROOT / "docs" / "gate3_report.md")
    promising = g3_pilot_promising(comparison, h5)
    report.g3_promising = promising
    report.notes.append(f"g3_promising={promising}")

    if stop_after == "g3":
        report.stopped_after = "G3"
        report.notes.append("stop-after=g3")
        return 0

    if not promising and not force_g4:
        report.add_stage(
            StageResult(
                name="G4",
                attempted=False,
                ok=False,
                skipped_reason="G3 not promising (no D win / H5); pass --force-g4 to override",
            )
        )
        report.stopped_after = "G3"
        report.notes.append("skipped G4 — G3 pilot not promising")
        return 0

    # Remaining budget for G4
    remaining = _budget_ceiling() - _budget_spent()
    g4_need = float(report.budget.get("g4_estimate") or (g4_pair_estimate_usd() * 5))
    if remaining + 1e-9 < g4_need:
        report.add_stage(
            StageResult(
                name="G4",
                attempted=False,
                ok=False,
                skipped_reason=(
                    f"remaining ${remaining:.2f} < G4 estimate ${g4_need:.2f}"
                ),
            )
        )
        report.blockers.append("budget: insufficient remaining for G4")
        report.stopped_after = "G3"
        return 3

    # --- G4 ---
    g4_argv = [
        "--live",
        "--seeds",
        g4_seeds,
        "--b-run-ids",
        g4_b,
        "--d-run-ids",
        g4_d,
    ]
    rc = g4.main(g4_argv)
    g4_ok = rc == 0
    report.add_stage(
        StageResult(
            name="G4",
            attempted=True,
            exit_code=rc,
            ok=g4_ok,
            detail="5-seed B vs D + paper pack",
        )
    )
    bump_spent(g4_need)
    report.stopped_after = "G4"
    if not g4_ok:
        report.blockers.append(f"G4 live failed (exit {rc})")
        return rc if rc else 4
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--preflight-only",
        action="store_true",
        help="Chain G2/G3/G4 preflights + budget projection (default)",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Paid sequential G2 → G3 → G4 (keys + real GPQA required)",
    )
    p.add_argument("--g2-run-id", type=int, default=DEFAULT_G2_RUN_ID)
    p.add_argument("--g3-seeds", type=str, default=DEFAULT_G3_SEEDS)
    p.add_argument("--g3-b-run-ids", type=str, default=DEFAULT_G3_B_IDS)
    p.add_argument("--g3-d-run-ids", type=str, default=DEFAULT_G3_D_IDS)
    p.add_argument("--g4-seeds", type=str, default=DEFAULT_G4_SEEDS)
    p.add_argument("--g4-b-run-ids", type=str, default=DEFAULT_G4_B_IDS)
    p.add_argument("--g4-d-run-ids", type=str, default=DEFAULT_G4_D_IDS)
    p.add_argument(
        "--stop-after",
        choices=("g2", "g3", "g4"),
        default="g4",
        help="Stop after this gate on --live (default: g4)",
    )
    p.add_argument(
        "--force-g4",
        action="store_true",
        help="Run G4 even if G3 pilot is not promising (still needs budget)",
    )
    p.add_argument(
        "--fetch-diamond",
        action="store_true",
        help="Materialize real GPQA diamond once (n=15) before live stack",
    )
    p.add_argument("--diamond-csv", type=Path, default=None)
    p.add_argument("--diamond-n", type=int, default=15)
    p.add_argument(
        "--report",
        type=Path,
        default=REPO_ROOT / "docs" / "icml_live_pipeline_report.md",
    )
    p.add_argument(
        "--icml-ready",
        type=Path,
        default=REPO_ROOT / "docs" / "ICML_READY.md",
    )
    args = p.parse_args(argv)

    selected = "live" if args.live else "preflight"
    g3_pairs = len(g3.parse_int_list(args.g3_seeds))
    report = PipelineReport(
        timestamp=_utc_now(),
        mode=selected,
        budget=project_budget(g3_pairs=g3_pairs, g4_pairs=5),
    )

    if selected == "preflight":
        # Optional diamond fetch during preflight (e.g. CSV path validation).
        if args.fetch_diamond or args.diamond_csv is not None:
            try:
                report.notes.extend(
                    _fetch_diamond(
                        diamond_csv=args.diamond_csv,
                        diamond_n=args.diamond_n,
                        seed=1,
                    )
                )
            except Exception as exc:
                report.notes.append(f"diamond fetch failed (preflight continues): {exc}")
        run_preflight_stack(
            report,
            g2_run_id=args.g2_run_id,
            g3_seeds=args.g3_seeds,
            g3_b=args.g3_b_run_ids,
            g3_d=args.g3_d_run_ids,
            g4_seeds=args.g4_seeds,
            g4_b=args.g4_b_run_ids,
            g4_d=args.g4_d_run_ids,
        )
        report.icml_ready_status = _read_icml_ready_status(args.icml_ready)
        write_pipeline_report(report, args.report)
        print(f"Pipeline preflight → {args.report}")
        print(f"ready_for_live={report.ready_for_live}")
        for b in report.blockers:
            print(f"  BLOCK: {b}")
        return 0

    rc = run_live_stack(
        report,
        g2_run_id=args.g2_run_id,
        g3_seeds=args.g3_seeds,
        g3_b=args.g3_b_run_ids,
        g3_d=args.g3_d_run_ids,
        g4_seeds=args.g4_seeds,
        g4_b=args.g4_b_run_ids,
        g4_d=args.g4_d_run_ids,
        stop_after=args.stop_after,
        force_g4=args.force_g4,
        fetch_diamond=args.fetch_diamond,
        diamond_csv=args.diamond_csv,
        diamond_n=args.diamond_n,
    )
    report.icml_ready_status = _read_icml_ready_status(args.icml_ready)
    # Recompute ready_for_live hint from whether we completed without blockers on keys.
    report.ready_for_live = rc == 0 and not any(
        "key" in b.lower() or "synthetic" in b.lower() for b in report.blockers
    )
    write_pipeline_report(report, args.report)
    print(f"Pipeline report → {args.report}")
    print(f"ICML_READY={report.icml_ready_status} exit={rc}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
