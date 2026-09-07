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
  - Tick 372: G2 resume re-validates post-run gates (incl. nonzero fitness);
    a 0%-fitness G2 still has results.json so Tick 284 alone would skip G2
    and auto-burn G3/G4 — refuse resume-complete until gates pass
  - Tick 373: G3→G4 gate re-scores local G3 B/D artifacts (or requires a
    live-executed gate3 sidecar). A resume-skipped G3 with only a preflight /
    null comparison must not auto-burn ~$14 G4, and a completed local G3 must
    not stall G4 because the sidecar was never written after a mid-stack crash.
  - Tick 374: resume-skipped G4 still rebuilds the paper pack from local B/D
    (or requires a live-executed gate4 sidecar). A completed G4 whose
    gate4_report.json stayed mode=preflight (crash after pairs / pack never
    ran) must not leave ICML_READY stuck IN_PROGRESS forever.

Modes:
  --preflight-only   chain G2/G3/G4 preflights + budget projection; no API
  --live             G2 → (pass) G3 → (promising + budget) G4 paper pack

Examples (Linux/cloud: python3; Windows venv: python):
  python3 scripts/run_icml_live_pipeline.py --preflight-only
  python3 scripts/run_icml_live_pipeline.py --live --fetch-diamond
  python3 scripts/run_icml_live_pipeline.py --live --fetch-diamond --stop-after g3
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
    committed_g3g4_recipes_match_live_shape,
    committed_offline_bvd_matches_live_shape,
    darwinian_run_complete,
    default_g2_estimate_usd,
    default_g3_pair_estimate_usd,
    default_g4_pair_estimate_usd,
    ensure_deps_before_diamond_fetch,
    icml_diamond_n_for_stack,
    icml_g3g4_live_shape,
    icml_human_required_secrets_phrase,
    icml_python_cli,
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
    # Tick 369: surface G3 compare + H2 from gate3 sidecar (not binary promising only).
    g3_comparison: dict[str, Any] | None = None
    g3_h2_by_d_run: dict[str, Any] = field(default_factory=dict)
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


def g2_resume_gates_ok(g2_run_id: int) -> tuple[bool, str]:
    """Tick 372: re-check G2 post-run gates before resume-skip / G3 advance.

    ``darwinian_run_complete`` is true whenever ``results.json`` has an
    ``accuracy`` key — including **0.0**. Tick 371 makes a fresh G2 return
    exit 4 on zero fitness, but the run dir remains; the next cron would
    otherwise treat G2 as resume-complete and auto-burn ~$19 on G3+G4.
    """
    found = g2._run_dir_for(g2_run_id)
    if found is None:
        return False, f"run_{g2_run_id} not found for G2 resume re-validation"
    checks = g2.validate_g2_artifacts(found)
    failed = [c for c in checks if not c.ok]
    if failed:
        detail = "; ".join(f"{c.name}={c.detail}" for c in failed)
        return False, detail
    return True, "all G2 post-run gates ok"


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
    Tick 372: local G2 artifacts must also pass ``validate_g2_artifacts`` (nonzero
    fitness, CABS store, bias) before ``g2_done`` — otherwise refuse
    resume-skip so G3/G4 cannot auto-advance on a failed smoke.
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

    g2_gates_ok = True
    g2_gates_detail: str | None = None
    if g2_local:
        g2_gates_ok, g2_gates_detail = g2_resume_gates_ok(g2_run_id)

    # Local artifacts that fail Tick 371 post-run gates are never resume-complete
    # (even if the ledger was stamped before Tick 372).
    g2_gates_failed = bool(g2_local and not g2_gates_ok)
    if g2_local:
        g2_done = g2_gates_ok
    else:
        g2_done = bool(g2_ledger)
    g3_done = g3_local or g3_ledger
    g4_done = g4_local or g4_ledger

    total = 0.0
    details: list[str] = []
    stages: list[str] = []
    all_ids: list[int] = []
    any_local = False

    if g2_gates_failed:
        dirs = _resolve_run_dirs([g2_run_id])
        if dirs:
            any_local = True
            amt, det = reconcile_gate_spend_usd(
                dirs, fallback_estimate=g2_estimate_usd()
            )
            total += amt
            details.append(f"G2 spend (gates failed): {det}")
        details.append(
            f"Tick 372: G2 run_{g2_run_id} post-run gates failed "
            f"({g2_gates_detail}) — refuse resume-complete / G3 advance; "
            f"pick a new unused --g2-run-id (never overwrite)"
        )
        all_ids.append(g2_run_id)
    elif g2_done:
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
        if g2_local and g2_gates_detail:
            details.append(f"Tick 372 G2 resume re-validation: {g2_gates_detail}")
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
        # Tick 372
        "g2_gates_failed": g2_gates_failed,
        "g2_gates_detail": g2_gates_detail,
        "g2_local": g2_local,
    }


def g3_pilot_promising(comparison: dict[str, Any] | None, h5_by_d_run: dict[str, Any]) -> bool:
    """G3→G4 gate: require PRIMARY-shaped D evidence (Tick 370).

    Tick 29–369 also treated H5 ρ>0.3 alone as promising, which could auto-spend
    ~$14 on 5-seed G4 when the pilot had **no** PRIMARY-shaped D win (gens/cost/
    final / mean_final_gap). End-goal criterion 1 is PRIMARY; H5 is VALIDITY and
    remains surfaced in the pipeline / gate3 report (Tick 369). Use ``--force-g4``
    to override. ``h5_by_d_run`` is retained for call-site / API compatibility.
    """
    _ = h5_by_d_run  # informational only after Tick 370 (not an auto-G4 signal)
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
    return False


def _read_icml_ready_status(path: Path) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    m = re.search(r"\*\*STATUS:\s*([A-Z_]+)\*\*", text)
    return m.group(1) if m else None


def _load_gate3_sidecar(
    report_md: Path,
) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any]]:
    """Load gate3 sidecar compare + H5 + H2 (Tick 369: H2 was written but ignored)."""
    sidecar = report_md.with_suffix(".json")
    if not sidecar.is_file():
        return None, {}, {}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, {}, {}
    return (
        data.get("comparison"),
        data.get("h5_by_d_run") or {},
        data.get("h2_by_d_run") or {},
    )


def _load_gate3_sidecar_raw(report_md: Path) -> dict[str, Any]:
    """Full gate3 JSON (mode/executed + compare) for Tick 373 G4 gate trust checks."""
    sidecar = report_md.with_suffix(".json")
    if not sidecar.is_file():
        return {}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def load_g3_metrics_for_g4(
    *,
    g3_b_ids: list[int],
    g3_d_ids: list[int],
    report_md: Path | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any], str]:
    """Tick 373: authoritative G3→G4 metrics (prefer local re-score).

    Resume can skip the G3 runner when B/D ``results.json`` exist, but the
    committed ``gate3_report.json`` is often still ``mode=preflight`` with
    ``comparison=null`` (crash after runs / fresh VM with only run dirs).
    Trusting that sidecar would either:
      - auto-refuse G4 forever despite a PRIMARY-shaped local pilot, or
      - (if comparison were ever filled from offline) risk a false G4 burn.
    Re-score from local dirs when present. Ledger-only / no-local fallback
    accepts the sidecar **only** when ``mode=="live"`` and ``executed`` and a
    non-null comparison exist.
    """
    report_md = report_md or (REPO_ROOT / "docs" / "gate3_report.md")
    g3_ids = list(g3_b_ids) + list(g3_d_ids)
    if g3_ids and stage_runs_complete(g3_ids):
        b_dirs = _resolve_run_dirs(list(g3_b_ids))
        d_dirs = _resolve_run_dirs(list(g3_d_ids))
        if len(b_dirs) == len(g3_b_ids) and len(d_dirs) == len(g3_d_ids):
            comparison, h5, h2 = g3.score_pilot(b_dirs, d_dirs)
            return (
                comparison,
                h5 or {},
                h2 or {},
                "Tick 373: re-scored G3 from local B/D run dirs",
            )
        return (
            None,
            {},
            {},
            "Tick 373: local G3 run IDs marked complete but dirs unresolved — "
            "refuse G4 until artifacts are present or gate3 live sidecar exists",
        )

    data = _load_gate3_sidecar_raw(report_md)
    comparison = data.get("comparison")
    mode = str(data.get("mode") or "")
    executed = bool(data.get("executed"))
    if (
        mode == "live"
        and executed
        and isinstance(comparison, dict)
        and comparison
    ):
        return (
            comparison,
            data.get("h5_by_d_run") or {},
            data.get("h2_by_d_run") or {},
            "Tick 373: trusted live-executed gate3 sidecar (no local G3 dirs)",
        )
    return (
        None,
        {},
        {},
        "Tick 373: no local G3 artifacts and no live-executed gate3 comparison "
        f"(mode={mode or 'missing'!r}, executed={executed}) — refuse G4 auto-advance",
    )


def _load_gate4_sidecar_raw(report_md: Path | None = None) -> dict[str, Any]:
    """Full gate4 JSON (mode/executed + compare) for Tick 374 resume pack trust."""
    report_md = report_md or (REPO_ROOT / "docs" / "gate4_report.md")
    sidecar = report_md.with_suffix(".json")
    if not sidecar.is_file():
        return {}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def refresh_g4_paper_pack_on_resume(
    *,
    g4_seeds: str,
    g4_b_ids: list[int],
    g4_d_ids: list[int],
    report: PipelineReport,
    paper_artifacts: Path | None = None,
    ready_path: Path | None = None,
    figures_dir: Path | None = None,
    gate4_report_md: Path | None = None,
    allow_ready: bool = True,
) -> str:
    """Tick 374: rebuild paper pack after resume-skip G4 (prefer local re-score).

    Tick 284 resume skips the G4 runner when B/D ``results.json`` exist, but
    ``gate4_report.json`` is often still ``mode=preflight`` (crash after pairs /
    paper pack never ran). That leaves ``ICML_READY`` stuck IN_PROGRESS despite
    PRIMARY-shaped live evidence. Re-score + ``apply_paper_pack`` when local
    dirs are present. Ledger-only / no-local fallback accepts the sidecar
    **only** when ``mode=="live"`` (or ``refresh-paper``) and ``executed`` and a
    non-null comparison exist — never promote READY from a preflight sidecar.
    """
    paper_artifacts = paper_artifacts or (REPO_ROOT / "docs" / "paper_artifacts.md")
    ready_path = ready_path or (REPO_ROOT / "docs" / "ICML_READY.md")
    figures_dir = figures_dir or (REPO_ROOT / "docs" / "figures")
    gate4_report_md = gate4_report_md or (REPO_ROOT / "docs" / "gate4_report.md")

    g4_ids = list(g4_b_ids) + list(g4_d_ids)
    if g4_ids and stage_runs_complete(g4_ids):
        b_dirs = _resolve_run_dirs(list(g4_b_ids))
        d_dirs = _resolve_run_dirs(list(g4_d_ids))
        if len(b_dirs) == len(g4_b_ids) and len(d_dirs) == len(g4_d_ids):
            try:
                seeds = g4.parse_int_list(g4_seeds)
                plans = g4.build_g4_plans(seeds, list(g4_b_ids), list(g4_d_ids))
            except ValueError as exc:
                return (
                    f"Tick 374: G4 resume paper pack refused — bad plans ({exc})"
                )
            g4_report = g4.G4PreflightReport(
                timestamp=_utc_now(),
                mode="refresh-paper",
                plans=plans,
                ready_for_live=False,
            )
            g4_report.notes.append(
                "Tick 374: resume-skipped G4 — re-scoring local B/D into paper pack "
                f"(allow_ready={allow_ready})"
            )
            paper_refreshed = g4.apply_paper_pack(
                g4_report,
                b_dirs=b_dirs,
                d_dirs=d_dirs,
                paper_artifacts=paper_artifacts,
                ready_path=ready_path,
                figures_dir=figures_dir,
                skip_paper_refresh=False,
                allow_ready=allow_ready,
            )
            g4.write_gate4_report(
                g4_report,
                gate4_report_md,
                executed=True,
                paper_refreshed=paper_refreshed,
            )
            report.icml_ready_status = g4_report.ready_status
            return (
                "Tick 374: re-scored G4 from local B/D + refreshed paper pack "
                f"(primary={g4_report.primary_pass}; h2={g4_report.h2_pass}; "
                f"h5={g4_report.h5_pass}; paper={paper_refreshed}; "
                f"ICML_READY={g4_report.ready_status})"
            )
        return (
            "Tick 374: local G4 run IDs marked complete but dirs unresolved — "
            "paper pack not refreshed (need artifacts or live-executed gate4 sidecar)"
        )

    data = _load_gate4_sidecar_raw(gate4_report_md)
    comparison = data.get("comparison")
    mode = str(data.get("mode") or "")
    executed = bool(data.get("executed"))
    paper_refreshed = bool(data.get("paper_refreshed"))
    ready_status = data.get("ready_status")
    if (
        mode in {"live", "refresh-paper"}
        and executed
        and isinstance(comparison, dict)
        and comparison
        and paper_refreshed
    ):
        if isinstance(ready_status, str) and ready_status:
            report.icml_ready_status = ready_status
        return (
            "Tick 374: trusted live-executed gate4 sidecar paper pack "
            f"(no local G4 dirs; mode={mode}; ICML_READY={ready_status or 'n/a'})"
        )
    return (
        "Tick 374: no local G4 artifacts and no live-executed gate4 paper pack "
        f"(mode={mode or 'missing'!r}, executed={executed}, "
        f"paper_refreshed={paper_refreshed}) — ICML_READY not updated from resume"
    )


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
    # Tick 369: after Tick 368 wrote H2 + mean_final_gap into gate3, the pipeline
    # still showed only a binary promising flag — operators reading
    # icml_live_pipeline_report.md would miss MECHANISM + PRIMARY (c) before G4.
    cmp_ = report.g3_comparison or {}
    if cmp_:
        mean_gap = cmp_.get("mean_final_gap")
        mean_gap_s = (
            f"{float(mean_gap):.4f}"
            if isinstance(mean_gap, (int, float))
            else "—"
        )
        n_pairs = cmp_.get("n_pairs", "—")
        lines.extend(
            [
                "",
                "### G3 pilot metrics (from gate3 sidecar)",
                "",
                f"- Mean final gap (D−B): **{mean_gap_s}** "
                f"(primary_final_pass={cmp_.get('primary_final_pass')})",
                f"- D gens30 / cost30 / final wins: "
                f"**{cmp_.get('d_wins_gens30', '—')}** / "
                f"**{cmp_.get('d_wins_cost30', '—')}** / "
                f"**{cmp_.get('d_wins_final', '—')}** (n={n_pairs})",
                f"- H2 preferred ≥0.5: **{cmp_.get('d_wins_h2', '—')}/{n_pairs}** "
                f"(h2_preferred_pass={cmp_.get('h2_preferred_pass')})",
            ]
        )
        if report.g3_h2_by_d_run:
            lines.extend(["", "#### H2 per Condition D run", ""])
            for name, h2 in report.g3_h2_by_d_run.items():
                if not isinstance(h2, dict):
                    continue
                fld = h2.get("field") or "auto"
                lines.append(
                    f"- `{name}`: field=`{fld}` "
                    f"preferred=`{h2.get('preferred_value')}` "
                    f"preferred_share=`{h2.get('preferred_share')}` "
                    f"in_bias_share=`{h2.get('in_bias_share')}`"
                )
            lines.append("")
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
        main_has_icml_tip=secrets_status.get("main_has_icml_tip"),
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
                "g3_comparison": report.g3_comparison,
                "g3_h2_by_d_run": report.g3_h2_by_d_run,
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

    Tick 299: after G2/G3/G4 gate writers refresh, enforce
    ``committed_g3g4_recipes_match_live_shape`` so stale Section 21.7 /
    pipeline notes cannot green-light a live stack (Tick 298 was tests-only).
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
    if resume.get("g2_gates_failed"):
        detail = resume.get("g2_gates_detail") or "G2 post-run gates failed"
        report.blockers.append(
            f"Tick 372: G2 run_{g2_run_id} exists but failed post-run gates "
            f"({detail}) — refuse G3/G4 auto-advance; pick a new unused "
            f"--g2-run-id (never overwrite)"
        )
        report.notes.append(
            f"Tick 372: G2 resume re-validation failed — {detail}"
        )
    report.notes.append(
        "Tick 296 G3/G4 shape: "
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
    # Tick 372: failed G2 post-run gates must clear live readiness even when
    # gate sidecars look green (occupied-ID blockers alone are easy to miss).
    if resume.get("g2_gates_failed"):
        report.ready_for_live = False

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

    # Tick 299: committed operator recipes must match live G3/G4 shape.
    # Gate JSON were just rewritten by G3/G4 preflight above; Section 21.7 +
    # pipeline note still come from the tip tree (must stay in sync).
    recipes_ok, recipe_problems = committed_g3g4_recipes_match_live_shape(
        repo_root=REPO_ROOT
    )
    if recipes_ok:
        report.notes.append(
            "Tick 299: committed G3/G4 recipes match live shape "
            f"{shape['eval_subset']}/{shape['population_size']}/"
            f"{shape['elite_count']}/{shape['max_gen']}"
        )
    else:
        for problem in recipe_problems:
            report.blockers.append(f"recipes: {problem}")
        report.ready_for_live = False
        report.notes.append(
            "Tick 299: refuse live until gate3/4 + Section 21.7 + pipeline "
            "shape note match icml_g3g4_live_shape() (see Tick 297–298)"
        )

    # Tick 300–301: offline Bvd summary / gate3 table / paper ID citations must
    # match live shape (prevents $20 spend after shape change or Tick-23 ID drift).
    offline_ok, offline_problems = committed_offline_bvd_matches_live_shape(
        repo_root=REPO_ROOT
    )
    if offline_ok:
        report.notes.append(
            "Tick 300–301: offline Bvd summary matches live shape "
            f"{shape['eval_subset']}/{shape['population_size']}/"
            f"{shape['elite_count']}/{shape['max_gen']} "
            "(paper/READY/Section12 ID citations locked)"
        )
    else:
        for problem in offline_problems:
            report.blockers.append(f"offline_bvd: {problem}")
        report.ready_for_live = False
        report.notes.append(
            "Tick 300–301: refuse live until offline_bvd_summary + gate3 offline "
            "table + paper/READY/Section12 cite current live-shape IDs"
        )


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
        "Tick 296 G3/G4 shape: "
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
    if resume.get("g2_gates_failed"):
        detail = resume.get("g2_gates_detail") or "G2 post-run gates failed"
        report.blockers.append(
            f"Tick 372: G2 run_{g2_run_id} exists but failed post-run gates "
            f"({detail}) — refuse G3/G4 auto-advance; pick a new unused "
            f"--g2-run-id (never overwrite)"
        )
        report.add_stage(
            StageResult(
                name="G2",
                attempted=False,
                ok=False,
                skipped_reason=(
                    f"Tick 372: post-run gates failed on existing run_{g2_run_id}"
                ),
                detail=str(detail),
            )
        )
        report.stopped_after = "G2"
        return 4
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

    comparison, h5, h2, g3_metric_src = load_g3_metrics_for_g4(
        g3_b_ids=g3_b_ids,
        g3_d_ids=g3_d_ids,
        report_md=REPO_ROOT / "docs" / "gate3_report.md",
    )
    report.notes.append(g3_metric_src)
    promising = g3_pilot_promising(comparison, h5)
    report.g3_promising = promising
    report.g3_comparison = comparison
    report.g3_h2_by_d_run = h2 or {}
    report.notes.append(f"g3_promising={promising}")
    if comparison and comparison.get("mean_final_gap") is not None:
        report.notes.append(
            f"g3_mean_final_gap={comparison.get('mean_final_gap')} "
            f"primary_final_pass={comparison.get('primary_final_pass')}"
        )
    if comparison and comparison.get("d_wins_h2") is not None:
        report.notes.append(
            f"g3_d_wins_h2={comparison.get('d_wins_h2')}/"
            f"{comparison.get('n_pairs')} "
            f"h2_preferred_pass={comparison.get('h2_preferred_pass')}"
        )

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
                skipped_reason=(
                    "G3 not promising (no PRIMARY-shaped D win; H5 alone is not "
                    "enough after Tick 370); pass --force-g4 to override"
                ),
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
                detail="5-seed B vs D + paper pack (skipped runner; Tick 374 pack refresh)",
            )
        )
        report.notes.append("Tick 284: skipped G4 runner (multiseed runs complete)")
        pack_note = refresh_g4_paper_pack_on_resume(
            g4_seeds=g4_seeds,
            g4_b_ids=g4_b_ids,
            g4_d_ids=g4_d_ids,
            report=report,
        )
        report.notes.append(pack_note)
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
                f"Recover tip: {icml_python_cli()} scripts/icml_recover_tip.py --apply"
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

    # Tick 299: refuse --live when committed recipes drift from live shape
    # (Tick 298 lock was unit-tested only; cron could still spend on a tip
    # whose Section 21.7 / pipeline note lagged a shape change).
    if selected == "live":
        recipes_ok, recipe_problems = committed_g3g4_recipes_match_live_shape(
            repo_root=REPO_ROOT
        )
        if not recipes_ok:
            for problem in recipe_problems:
                report.blockers.append(f"recipes: {problem}")
            report.notes.append(
                "Sync Section 21.7 + gate/pipeline reports to "
                "icml_g3g4_live_shape() before paid G2→G3→G4 "
                "(Tick 297–299)."
            )
            report.icml_ready_status = _read_icml_ready_status(args.icml_ready)
            write_pipeline_report(report, args.report)
            print(
                f"Pipeline refused --live (stale G3/G4 recipes) → {args.report}"
            )
            for b in report.blockers:
                print(f"  BLOCK: {b}")
            return 3

        offline_ok, offline_problems = committed_offline_bvd_matches_live_shape(
            repo_root=REPO_ROOT
        )
        if not offline_ok:
            for problem in offline_problems:
                report.blockers.append(f"offline_bvd: {problem}")
            report.notes.append(
                "Refresh offline Bvd at icml_g3g4_live_shape() before paid "
                "G2→G3→G4 (Tick 300)."
            )
            report.icml_ready_status = _read_icml_ready_status(args.icml_ready)
            write_pipeline_report(report, args.report)
            print(
                f"Pipeline refused --live (stale offline Bvd shape) → {args.report}"
            )
            for b in report.blockers:
                print(f"  BLOCK: {b}")
            return 3

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
