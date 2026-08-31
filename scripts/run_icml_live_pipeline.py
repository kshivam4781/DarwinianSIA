#!/usr/bin/env python3
"""ICML Thesis 1 — one-command live G2 → G3 → G4 pipeline.

After Tick 28 the individual gate runners + G4 paper pack are turnkey, but a
cron tick with freshly injected keys still risked stopping after G2 (or G3)
and wasting a cycle. This orchestrator chains the gates **serially** so one
unblocked tick can reach STATUS: READY.

Hard stops (delegated to gate runners; never violate here either):
  - no two GPQA jobs in parallel
  - no --focus weights / no LawBench
  - refuse without NEBIUS_API_KEY for --live (ANTHROPIC optional under Nebius meta; Tick 289/292)
  - refuse --live --fetch-diamond without HF_TOKEN (Tick 274; match cron)
  - refuse synthetic smoke for --live (fetch real diamond once, n=15)
  - never overwrite existing run IDs
  - project full-stack spend ≤ SIA_BUDGET_CEILING_USD (~$20)
  - update SIA_BUDGET_SPENT_USD between stages from actual run USD
    (Tick 283) and persist to docs/icml_budget_spent.json (Tick 284/285)
  - resume: skip completed G2/G3/G4 run IDs; never overwrite (Tick 284)
  - cross-VM resume: trust committed ledger stages when runs/ absent (Tick 285)

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
from icml_env_checks import (  # noqa: E402
    apply_persisted_spent_to_env,
    autowire_diamond_csv,
    budget_spent_ledger_path,
    collect_icml_secrets_status,
    darwinian_run_complete,
    default_g2_estimate_usd,
    default_g3_pair_estimate_usd,
    default_g4_pair_estimate_usd,
    ensure_deps_before_diamond_fetch,
    icml_diamond_n_for_stack,
    icml_g3g4_live_shape,
    icml_human_required_secrets_phrase,
    ledger_stage_complete,
    live_pipeline_next_steps,
    load_budget_spent_ledger,
    write_budget_spent_ledger,
    write_icml_secrets_status,
    write_icml_tip_status,
)
from prepare_gpqa_diamond import materialize_from_csv, materialize_from_hf  # noqa: E402

DEFAULT_BUDGET_CEILING = 20.0
# Tick 293: Nebius-aware defaults (module import snapshot; helpers re-resolve).
DEFAULT_G2_ESTIMATE_USD = default_g2_estimate_usd()
DEFAULT_G3_PAIR_ESTIMATE_USD = default_g3_pair_estimate_usd()
DEFAULT_G4_PAIR_ESTIMATE_USD = default_g4_pair_estimate_usd()
DEFAULT_DIAMOND_N = icml_diamond_n_for_stack()

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
    # Prefer env override inside default_g2_estimate_usd; keep _env_float path
    # only when callers set SIA_G2_ESTIMATE_USD to a non-default string that the
    # helper already honors.
    return float(default_g2_estimate_usd())


def g3_pair_estimate_usd() -> float:
    return float(default_g3_pair_estimate_usd())


def g4_pair_estimate_usd() -> float:
    return float(default_g4_pair_estimate_usd())


def project_budget(
    *,
    g3_pairs: int = 1,
    g4_pairs: int = 5,
    skip_g2: bool = False,
    skip_g3: bool = False,
    skip_g4: bool = False,
) -> dict[str, Any]:
    """Project remaining stack spend (Tick 284: exclude completed gates)."""
    spent = _budget_spent()
    ceiling = _budget_ceiling()
    g2_e = 0.0 if skip_g2 else g2_estimate_usd()
    g3_e = 0.0 if skip_g3 else g3_pair_estimate_usd() * g3_pairs
    g4_e = 0.0 if skip_g4 else g4_pair_estimate_usd() * g4_pairs
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
        "skip_g2": skip_g2,
        "skip_g3": skip_g3,
        "skip_g4": skip_g4,
    }


def bump_spent(delta: float, *, stage: str | None = None, run_ids: list[int] | None = None, detail: str = "") -> float:
    """Increment SIA_BUDGET_SPENT_USD so later gate preflights see remaining headroom."""
    new_spent = _budget_spent() + max(0.0, float(delta))
    os.environ["SIA_BUDGET_SPENT_USD"] = f"{new_spent:.4f}"
    # Tick 284: persist across cron ticks / mid-stack crashes.
    write_budget_spent_ledger(
        spent_usd=new_spent,
        stages_complete=[stage] if stage else None,
        detail=detail or f"bumped +${max(0.0, float(delta)):.4f}",
        run_ids=run_ids,
        path=budget_spent_ledger_path(REPO_ROOT),
    )
    return new_spent


def _resolve_run_dirs(run_ids: list[int]) -> list[Path]:
    """Locate run dirs under monorepo ``runs/`` or ``SIA/runs/``."""
    dirs: list[Path] = []
    for rid in run_ids:
        found = g2._run_dir_for(rid) or g3._run_dir_for(rid)
        if found is not None:
            dirs.append(found)
    return dirs


def stage_runs_complete(run_ids: list[int]) -> bool:
    """True when every listed run_id has a completed Darwinian results.json."""
    if not run_ids:
        return False
    for rid in run_ids:
        found = g2._run_dir_for(rid) or g3._run_dir_for(rid)
        if not darwinian_run_complete(found):
            return False
    return True


def bump_spent_reconciled(
    run_ids: list[int],
    *,
    fallback_estimate: float,
    stage: str | None = None,
) -> tuple[float, str]:
    """Tick 283: bump spend from actual run USD when present, else estimate.

    Stack budget targets ~$20 (Tick 293 Nebius: G2+$2 + G3+$3 + G4+$14 = $19;
    Anthropic-era was G2+$1 + G3+$4 + G4+$15). Bumping only by
    estimate can refuse G4 when G2/G3 came in under estimate, or under-count
    when they overran. Prefer ``total_cost_usd`` artifacts × meta overhead.
    Tick 284 also persists the bump to ``docs/icml_budget_spent.json``.
    """
    from icml_env_checks import reconcile_gate_spend_usd

    dirs = _resolve_run_dirs(run_ids)
    amount, detail = reconcile_gate_spend_usd(
        dirs, fallback_estimate=fallback_estimate
    )
    bump_spent(amount, stage=stage, run_ids=run_ids, detail=detail)
    return amount, detail


def sync_spent_from_completed_stages(
    *,
    g2_run_id: int,
    g3_b_ids: list[int],
    g3_d_ids: list[int],
    g4_b_ids: list[int],
    g4_d_ids: list[int],
) -> dict[str, Any]:
    """Authoritative resume sync: artifacts when present, else committed ledger.

    Avoids double-counting when a prior tick already bumped and persisted.
    Tick 285: if ``runs/`` are gone (fresh cron VM) but
    ``docs/icml_budget_spent.json`` was committed with matching run IDs,
    still mark those stages done and keep ledger spend (do not zero / re-run).
    """
    from icml_env_checks import reconcile_gate_spend_usd

    ledger_path = budget_spent_ledger_path(REPO_ROOT)
    apply_persisted_spent_to_env(path=ledger_path)
    ledger = load_budget_spent_ledger(ledger_path)

    g2_local = stage_runs_complete([g2_run_id])
    g3_ids = g3_b_ids + g3_d_ids
    g4_ids = g4_b_ids + g4_d_ids
    g3_local = stage_runs_complete(g3_ids)
    g4_local = stage_runs_complete(g4_ids)

    g2_ledger = ledger_stage_complete("G2", [g2_run_id], path=ledger_path)
    g3_ledger = ledger_stage_complete("G3", g3_ids, path=ledger_path)
    g4_ledger = ledger_stage_complete("G4", g4_ids, path=ledger_path)

    g2_done = g2_local or g2_ledger
    g3_done = g3_local or g3_ledger
    g4_done = g4_local or g4_ledger

    total = 0.0
    details: list[str] = []
    stages: list[str] = []
    all_ids: list[int] = []
    any_local = False

    if g2_done:
        dirs = _resolve_run_dirs([g2_run_id])
        if dirs:
            any_local = True
            amt, det = reconcile_gate_spend_usd(
                dirs, fallback_estimate=g2_estimate_usd()
            )
        else:
            amt, det = g2_estimate_usd(), "ledger-only resume (no local run dir)"
        total += amt
        details.append(f"G2: {det}")
        stages.append("G2")
        all_ids.append(g2_run_id)
    if g3_done:
        dirs = _resolve_run_dirs(g3_ids)
        est = g3_pair_estimate_usd() * max(1, len(g3_b_ids))
        if dirs:
            any_local = True
            amt, det = reconcile_gate_spend_usd(dirs, fallback_estimate=est)
        else:
            amt, det = est, "ledger-only resume (no local run dirs)"
        total += amt
        details.append(f"G3: {det}")
        stages.append("G3")
        all_ids.extend(g3_ids)
    if g4_done:
        dirs = _resolve_run_dirs(g4_ids)
        est = g4_pair_estimate_usd() * max(1, len(g4_b_ids))
        if dirs:
            any_local = True
            amt, det = reconcile_gate_spend_usd(dirs, fallback_estimate=est)
        else:
            amt, det = est, "ledger-only resume (no local run dirs)"
        total += amt
        details.append(f"G4: {det}")
        stages.append("G4")
        all_ids.extend(g4_ids)

    if stages and any_local:
        # Prefer artifact-reconciled spend when local runs exist.
        os.environ["SIA_BUDGET_SPENT_USD"] = f"{total:.4f}"
        write_budget_spent_ledger(
            spent_usd=total,
            stages_complete=stages,
            detail="; ".join(details),
            run_ids=all_ids,
            path=ledger_path,
        )
    elif stages and not any_local:
        # Cross-VM: keep committed ledger spent (do not overwrite with estimates).
        ledger_spent = ledger.get("spent_usd")
        if isinstance(ledger_spent, (int, float)):
            os.environ["SIA_BUDGET_SPENT_USD"] = f"{float(ledger_spent):.4f}"
            details.append(
                f"Tick 285 ledger-only spend=${float(ledger_spent):.4f} "
                f"(stages={','.join(stages)}; runs/ absent)"
            )
        else:
            os.environ["SIA_BUDGET_SPENT_USD"] = f"{total:.4f}"
            write_budget_spent_ledger(
                spent_usd=total,
                stages_complete=stages,
                detail="; ".join(details),
                run_ids=all_ids,
                path=ledger_path,
            )
    return {
        "g2_done": g2_done,
        "g3_done": g3_done,
        "g4_done": g4_done,
        "spent": _budget_spent(),
        "details": details,
        "ledger_only": bool(stages) and not any_local,
    }


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
    # Tick 268–274: tip lineage + secrets-first Next (HF required for --fetch-diamond).
    tip_blocker = any(
        b.lower().startswith("tip:") or "ICML_PROGRESS" in b for b in report.blockers
    )
    tip_ref = None
    tip_path = REPO_ROOT / "docs" / "icml_tip_status.json"
    if tip_path.is_file():
        try:
            tip_blob = json.loads(tip_path.read_text(encoding="utf-8"))
            tip_ref = tip_blob.get("remote_tip_ref")
            if tip_blob.get("tip_ok_for_live") is False:
                tip_blocker = True
        except (json.JSONDecodeError, OSError):
            pass
    secrets_status = collect_icml_secrets_status()
    secrets_ok = bool(secrets_status.get("secrets_ok_for_paid_sia"))
    fetch_diamond_ok = bool(secrets_status.get("fetch_diamond_ok"))
    next_lines = live_pipeline_next_steps(
        secrets_ok=secrets_ok,
        tip_ok=(False if tip_blocker else True),
        tip_ref=tip_ref,
        fetch_diamond_ok=fetch_diamond_ok,
    )
    lines.extend(["", "## Next", ""])
    for i, step in enumerate(next_lines, start=1):
        lines.append(f"{i}. {step}")
    lines.append("")
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
    # Tick 282: bootstrap huggingface_hub before HF materialize (CSV still
    # benefits from uv/SIA path consistency).
    deps_ok, deps_detail = ensure_deps_before_diamond_fetch(allow_install=True)
    notes.append(f"runtime deps before diamond: {deps_detail}")
    if not deps_ok and diamond_csv is None:
        raise RuntimeError(
            f"runtime deps failed before HF materialize: {deps_detail}"
        )
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
    fetch_diamond: bool = False,
    diamond_csv: Path | None = None,
    diamond_n: int | None = None,
) -> None:
    """Run G2/G3/G4 preflights (no paid API) and aggregate readiness.

    Tick 276: when ``fetch_diamond`` (cron intended live path), pass
    ``--fetch-diamond`` into each gate so individual gate2/3/4 reports
    require HF via ``require_hf_for_diamond`` — not only the aggregate
    pipeline blocker added below.

    Tick 283/293: default ``diamond_n`` matches G3/G4 ``eval_subset`` via
    ``icml_diamond_n_for_stack`` (Nebius budget-fit → 10; Anthropic → 15).

    Tick 284: resume-aware — completed run IDs do not clear ``ready_for_live``;
    budget projection excludes finished gates and reloads persisted spend.
    """
    if diamond_n is None:
        diamond_n = icml_diamond_n_for_stack()
    shape = icml_g3g4_live_shape()
    shape_args = [
        "--eval-subset",
        str(shape["eval_subset"]),
        "--population-size",
        str(shape["population_size"]),
        "--elite-count",
        str(shape["elite_count"]),
        "--max-gen",
        str(shape["max_gen"]),
    ]
    g3_b_ids = g3.parse_int_list(g3_b)
    g3_d_ids = g3.parse_int_list(g3_d)
    g4_b_ids = g4.parse_int_list(g4_b)
    g4_d_ids = g4.parse_int_list(g4_d)
    resume = sync_spent_from_completed_stages(
        g2_run_id=g2_run_id,
        g3_b_ids=g3_b_ids,
        g3_d_ids=g3_d_ids,
        g4_b_ids=g4_b_ids,
        g4_d_ids=g4_d_ids,
    )
    if resume.get("details"):
        report.notes.append(
            "Tick 284 resume sync: " + "; ".join(resume["details"])
        )
    report.notes.append(
        "Tick 293 G3/G4 shape: "
        f"eval_subset={shape['eval_subset']} pop={shape['population_size']} "
        f"elite={shape['elite_count']} max_gen={shape['max_gen']}"
    )
    report.budget = project_budget(
        g3_pairs=len(g3.parse_int_list(g3_seeds)),
        g4_pairs=5,
        skip_g2=bool(resume.get("g2_done")),
        skip_g3=bool(resume.get("g3_done")),
        skip_g4=bool(resume.get("g4_done")),
    )

    fetch_args: list[str] = []
    if diamond_csv is not None:
        fetch_args.extend(["--fetch-diamond", "--diamond-csv", str(diamond_csv)])
        fetch_args.extend(["--diamond-n", str(diamond_n)])
    elif fetch_diamond:
        fetch_args.extend(["--fetch-diamond", "--diamond-n", str(diamond_n)])

    # G2
    rc = g2.main(
        ["--preflight-only", "--run-id", str(g2_run_id), *fetch_args]
    )
    report.add_stage(
        StageResult(
            name="G2",
            attempted=True,
            exit_code=rc,
            ok=rc == 0,
            detail="preflight invoked"
            + (" (+fetch-diamond)" if fetch_args else "")
            + (" [resume:complete]" if resume.get("g2_done") else ""),
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
            *shape_args,
            *fetch_args,
        ]
    )
    report.add_stage(
        StageResult(
            name="G3",
            attempted=True,
            exit_code=rc,
            ok=rc == 0,
            detail="preflight invoked"
            + (" (+fetch-diamond)" if fetch_args else "")
            + (" [resume:complete]" if resume.get("g3_done") else ""),
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
            *shape_args,
            *fetch_args,
        ]
    )
    report.add_stage(
        StageResult(
            name="G4",
            attempted=True,
            exit_code=rc,
            ok=rc == 0,
            detail="preflight invoked"
            + (" (+fetch-diamond)" if fetch_args else "")
            + (" [resume:complete]" if resume.get("g4_done") else ""),
        )
    )

    # Live readiness: keys + non-smoke + budget stack + free IDs (from gate reports).
    # Tick 284: completed stages ignore run_id_free blockers (resume path).
    g2_json = (REPO_ROOT / "docs" / "gate2_report.json")
    g3_json = (REPO_ROOT / "docs" / "gate3_report.json")
    g4_json = (REPO_ROOT / "docs" / "gate4_report.json")
    ready_flags: list[bool] = []
    stage_done = {
        "G2": bool(resume.get("g2_done")),
        "G3": bool(resume.get("g3_done")),
        "G4": bool(resume.get("g4_done")),
    }
    for path, label in (
        (g2_json, "G2"),
        (g3_json, "G3"),
        (g4_json, "G4"),
    ):
        if stage_done.get(label):
            ready_flags.append(True)
            report.notes.append(
                f"Tick 284: {label} already complete — treating gate live-ready for resume"
            )
            continue
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

    # Tick 269: tip lineage status (cron often boots from main).
    tip_status = write_icml_tip_status(
        REPO_ROOT / "docs" / "icml_tip_status.json",
        fetch=False,
    )
    if not tip_status.get("tip_ok_for_live"):
        for b in tip_status.get("blockers") or []:
            report.blockers.append(f"tip: {b}")
        report.ready_for_live = False

    # Tick 268: presence-only secrets gate artifact (never writes secret values).
    synthetic = any("synthetic" in b.lower() for b in report.blockers)
    secrets_status = write_icml_secrets_status(
        REPO_ROOT / "docs" / "icml_secrets_status.json",
        gpqa_is_synthetic=True if synthetic else None,
    )
    # Tick 274/276: intended cron live path is --fetch-diamond → surface HF.
    # CSV path / preflight without --fetch-diamond skips the aggregate HF demand
    # (individual gates already got require_hf when fetch_args were passed).
    if fetch_diamond and diamond_csv is None:
        if not secrets_status.get("hf_token_present"):
            report.blockers.append(
                "HF_TOKEN / HUGGINGFACE_HUB_TOKEN missing "
                "(required for --fetch-diamond / cron auto-live)"
            )
            report.ready_for_live = False
        elif not secrets_status.get("fetch_diamond_ok"):
            report.blockers.append(
                "fetch_diamond_ok=false — need "
                + icml_human_required_secrets_phrase(for_fetch_diamond=True)
            )
            report.ready_for_live = False


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
    """Execute G2→G3→G4 serially. Returns process exit code.

    Tick 284: skip stages whose run IDs already have complete results
    (mid-stack crash / cron boundary resume). Never overwrite existing runs.
    Tick 285: also skip when committed ledger marks stages complete even if
    local ``runs/`` are absent (fresh cloud VM).
    """
    shape = icml_g3g4_live_shape()
    shape_args = [
        "--eval-subset",
        str(shape["eval_subset"]),
        "--population-size",
        str(shape["population_size"]),
        "--elite-count",
        str(shape["elite_count"]),
        "--max-gen",
        str(shape["max_gen"]),
    ]
    report.notes.append(
        "Tick 293 G3/G4 shape: "
        f"eval_subset={shape['eval_subset']} pop={shape['population_size']} "
        f"elite={shape['elite_count']} max_gen={shape['max_gen']}"
    )
    g3_b_ids = g3.parse_int_list(g3_b)
    g3_d_ids = g3.parse_int_list(g3_d)
    g4_b_ids = g4.parse_int_list(g4_b)
    g4_d_ids = g4.parse_int_list(g4_d)
    resume = sync_spent_from_completed_stages(
        g2_run_id=g2_run_id,
        g3_b_ids=g3_b_ids,
        g3_d_ids=g3_d_ids,
        g4_b_ids=g4_b_ids,
        g4_d_ids=g4_d_ids,
    )
    if resume.get("details"):
        label = "Tick 285 ledger-only resume" if resume.get("ledger_only") else "Tick 284 resume sync"
        report.notes.append(label + ": " + "; ".join(resume["details"]))
    report.budget = project_budget(
        g3_pairs=len(g3.parse_int_list(g3_seeds)),
        g4_pairs=5,
        skip_g2=bool(resume.get("g2_done")),
        skip_g3=bool(resume.get("g3_done")),
        skip_g4=bool(resume.get("g4_done")),
    )

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
    if resume.get("g2_done"):
        report.add_stage(
            StageResult(
                name="G2",
                attempted=False,
                exit_code=0,
                ok=True,
                skipped_reason=f"resume: run_{g2_run_id} already complete",
                detail="Condition D smoke (skipped)",
            )
        )
        report.notes.append(f"Tick 284: skipped G2 (run_{g2_run_id} complete)")
    else:
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
        # Tick 283/284: reconcile + persist.
        g2_amt, g2_spend_detail = bump_spent_reconciled(
            [g2_run_id],
            fallback_estimate=float(
                report.budget.get("g2_estimate") or g2_estimate_usd()
            ),
            stage="G2",
        )
        report.notes.append(
            f"G2 spend reconcile: {g2_spend_detail} (bumped ${g2_amt:.4f})"
        )
    if stop_after == "g2":
        report.stopped_after = "G2"
        report.notes.append("stop-after=g2")
        return 0

    # --- G3 ---
    if resume.get("g3_done"):
        report.add_stage(
            StageResult(
                name="G3",
                attempted=False,
                exit_code=0,
                ok=True,
                skipped_reason="resume: G3 B/D run IDs already complete",
                detail="sequential B then D pilot (skipped)",
            )
        )
        report.notes.append("Tick 284: skipped G3 (pilot runs complete)")
    else:
        g3_argv = [
            "--live",
            "--seeds",
            g3_seeds,
            "--b-run-ids",
            g3_b,
            "--d-run-ids",
            g3_d,
            *shape_args,
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
        g3_ids = g3_b_ids + g3_d_ids
        g3_amt, g3_spend_detail = bump_spent_reconciled(
            g3_ids,
            fallback_estimate=float(
                report.budget.get("g3_estimate") or g3_pair_estimate_usd()
            ),
            stage="G3",
        )
        report.notes.append(
            f"G3 spend reconcile: {g3_spend_detail} (bumped ${g3_amt:.4f})"
        )

    comparison, h5 = _load_gate3_sidecar(REPO_ROOT / "docs" / "gate3_report.md")
    promising = g3_pilot_promising(comparison, h5)
    report.g3_promising = promising
    report.notes.append(f"g3_promising={promising}")

    if stop_after == "g3":
        report.stopped_after = "G3"
        report.notes.append("stop-after=g3")
        return 0

    if not promising and not force_g4 and not resume.get("g4_done"):
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
    g4_need = float(
        report.budget.get("g4_estimate")
        if report.budget.get("g4_estimate") is not None
        else (g4_pair_estimate_usd() * 5)
    )
    if resume.get("g4_done"):
        report.add_stage(
            StageResult(
                name="G4",
                attempted=False,
                exit_code=0,
                ok=True,
                skipped_reason="resume: G4 B/D run IDs already complete",
                detail="5-seed B vs D + paper pack (skipped)",
            )
        )
        report.notes.append("Tick 284: skipped G4 (multiseed runs complete)")
        report.stopped_after = "G4"
        return 0

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
        *shape_args,
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
    g4_ids = g4_b_ids + g4_d_ids
    g4_amt, g4_spend_detail = bump_spent_reconciled(
        g4_ids,
        fallback_estimate=g4_need,
        stage="G4",
    )
    report.notes.append(
        f"G4 spend reconcile: {g4_spend_detail} (bumped ${g4_amt:.4f})"
    )
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
        help="Materialize real GPQA diamond once (n=eval_subset) before live stack",
    )
    p.add_argument("--diamond-csv", type=Path, default=None)
    p.add_argument("--diamond-n", type=int, default=DEFAULT_DIAMOND_N)
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
    p.add_argument(
        "--allow-stale-tip",
        action="store_true",
        help="Allow --live even when local Tick lags remote tip (dangerous)",
    )
    args = p.parse_args(argv)

    selected = "live" if args.live else "preflight"
    # Tick 278: auto-wire local diamond CSV under --fetch-diamond (match cron).
    diamond_csv, csv_auto = autowire_diamond_csv(
        args.diamond_csv, fetch_diamond=bool(args.fetch_diamond), repo_root=REPO_ROOT
    )
    args.diamond_csv = diamond_csv
    g3_pairs = len(g3.parse_int_list(args.g3_seeds))
    report = PipelineReport(
        timestamp=_utc_now(),
        mode=selected,
        budget=project_budget(g3_pairs=g3_pairs, g4_pairs=5),
    )
    if csv_auto and args.diamond_csv is not None:
        report.notes.append(
            f"Tick 278: auto-wired --diamond-csv from {args.diamond_csv}"
        )

    # Tick 269: refuse paid stack on stale / missing ICML tip (unless override).
    tip_status = write_icml_tip_status(
        REPO_ROOT / "docs" / "icml_tip_status.json",
        fetch=False,
    )
    if selected == "live" and not tip_status.get("tip_ok_for_live"):
        if args.allow_stale_tip:
            report.notes.append(
                "tip: --allow-stale-tip set; proceeding despite lineage blockers"
            )
        else:
            for b in tip_status.get("blockers") or ["stale ICML tip"]:
                report.blockers.append(f"tip: {b}")
            report.notes.append(
                "Recover tip: python scripts/icml_recover_tip.py --apply"
            )
            report.icml_ready_status = _read_icml_ready_status(args.icml_ready)
            write_pipeline_report(report, args.report)
            print(f"Pipeline refused --live (stale tip) → {args.report}")
            for b in report.blockers:
                print(f"  BLOCK: {b}")
            return 3

    # Tick 274/278: refuse --live --fetch-diamond without HF/CSV (match cron).
    # Avoids attempting HF materialize (or confusing "keys OK" next-steps) on
    # Anthropic+Nebius-only partial secrets. Local CSV auto-wire skips HF.
    if (
        selected == "live"
        and args.fetch_diamond
        and args.diamond_csv is None
    ):
        secrets_status = collect_icml_secrets_status()
        if not secrets_status.get("fetch_diamond_ok"):
            for b in secrets_status.get("blockers") or [
                "fetch_diamond_ok=false (need "
                + icml_human_required_secrets_phrase(for_fetch_diamond=True)
                + ")"
            ]:
                report.blockers.append(f"secrets: {b}")
            report.notes.append(
                "Add HF_TOKEN (+ API keys) per docs/ICML_HUMAN_UNBLOCK.md; "
                "or pass --diamond-csv / drop gpqa_diamond.csv to skip HF."
            )
            report.icml_ready_status = _read_icml_ready_status(args.icml_ready)
            write_pipeline_report(report, args.report)
            print(
                f"Pipeline refused --live --fetch-diamond "
                f"(fetch_diamond_ok=false) → {args.report}"
            )
            for b in report.blockers:
                print(f"  BLOCK: {b}")
            return 4

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
            fetch_diamond=bool(args.fetch_diamond),
            diamond_csv=args.diamond_csv,
            diamond_n=args.diamond_n,
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
