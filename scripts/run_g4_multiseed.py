#!/usr/bin/env python3
"""ICML Gate G4 — sequential 5-seed Condition B vs D runner + paper pack refresh.

Section 21.5 Gate G4: full 5-seed B vs D under budget; compute PRIMARY + H2 + H5;
refresh ``docs/paper_artifacts.md`` live tables, Figs 1–2, and ``docs/ICML_READY.md``
checklist when pairs complete (STATUS: READY only if criteria 1–4 all pass).

Hard stops (never violate):
  - exactly 5 seeds (G3 is 1–2; do not mix)
  - no two GPQA jobs in parallel (B then D, sequential per seed)
  - ``--live`` requires NEBIUS_API_KEY (ANTHROPIC optional under Nebius meta; Tick 289/292)
  - ``--live`` refuses synthetic smoke GPQA answers
  - ``--live`` refuses when committed G3/G4 recipes or offline Bvd artifacts
    mismatch live shape (Tick 303; same guards as pipeline Tick 298–302)
  - ``--live`` refuses when local ICML tip lags remote tip (Tick 305; same
    tip lineage guard as pipeline Tick 269 — use ``--allow-stale-tip`` only
    for recovery)
  - refuses incomplete/corrupt existing run dirs (never overwrite)
  - Tick 375: completed B/D run IDs are resume-skipped (not blockers) so a
    mid-stack crash can finish remaining pairs without picking new IDs
  - Tick 377: direct ``--live`` hydrates ``SIA_BUDGET_SPENT_USD`` from the
    committed ledger + unbilled local complete runs before the budget check
    (closes pipeline-only Tick 376 bypass)
  - Tick 379: after successful live (all planned B/D complete + paper pack),
    persist ledger stage ``G4`` (hydrate alone never stamped stages)
  - Tick 380: ``--live`` skips paid re-run when committed ledger already marks
    ``G4`` complete for the planned run IDs (pipeline Tick 285 parity)
  - Tick 381: ledger-skip still refreshes paper pack / ICML_READY (pipeline
    Tick 374 parity — Tick 380 early-return left READY stuck after paid G4)
  - Tick 386: preflight preserves ``prior_live_metrics`` so cron
    ``--preflight-only`` cannot wipe paid G4 comparison / paper_refreshed
    evidence (Tick 385 gate3 ``prior_live_metrics`` parity)
  - Tick 408: Condition D gen≥3 steering positive-control before paper pack /
    READY / ledger stamp (Tick 407 G3 gate was G3→G4 only — G4 could still
    promote never-steer D into ``ICML_READY``); refuse READY + ledger on
    never-steer; sidecar trust refuses ``steering_applied_gen3=false``
  - Tick 409: mid-G4 abort after first never-steer Condition D (via
    ``run_sequential_live(abort_on_d_never_steer=True)``) so remaining pairs
    do not burn ~$12; skip partial paper pack / Live Table promote
  - Tick 410: live paper pack only when **all planned pairs** complete
    (``len(B)==len(D)==len(plans)``), not merely equal B/D counts — closes
    partial Live Table promote after non-never-steer mid-abort (e.g. sia
    exit on seed 2 leaving one steered pair)
  - respects ``SIA_BUDGET_SPENT_USD`` / ``SIA_BUDGET_CEILING_USD`` (~$20)
  - projects spend: ``SIA_G4_PAIR_ESTIMATE_USD`` × remaining pairs ≤ budget

Modes:
  --preflight-only          check blockers; write docs/gate4_report.md
  --live                    paid sequential B then D × 5 seeds (keys + non-smoke GPQA)
  --refresh-paper-from-runs rebuild paper pack / READY checklist from existing run dirs
                            (no API; for recovery after live pairs or unit tests)

Examples (Linux/cloud: python3; Windows venv: python):
  python3 scripts/run_g4_multiseed.py --preflight-only
  python3 scripts/run_g4_multiseed.py --live \\
    --seeds 1,2,3,4,5 --b-run-ids 1211,1212,1213,1214,1215 \\
    --d-run-ids 1311,1312,1313,1314,1315 --fetch-diamond
  python3 scripts/run_g4_multiseed.py --refresh-paper-from-runs \\
    --b-run-dirs runs/run_1211 ... --d-run-dirs runs/run_1311 ...
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
from icml_env_checks import (  # noqa: E402
    autowire_diamond_csv,
    collect_icml_secrets_status,
    committed_g3g4_recipes_match_live_shape,
    committed_offline_bvd_matches_live_shape,
    darwinian_run_complete,
    default_g4_pair_estimate_usd,
    ensure_deps_before_diamond_fetch,
    ensure_icml_runtime_deps,
    hydrate_direct_gate_budget_spent,
    persist_direct_gate_stage_spend,
    persist_prior_live_stash_from_working_tree,
    direct_gate_ledger_skip,
    icml_diamond_n_for_stack,
    icml_g3g4_live_shape,
    icml_human_required_secrets_phrase,
    icml_meta_requires_anthropic,
    icml_python_cli,
    probe_icml_meta_profile,
    probe_icml_target_profile_nebius,
    probe_per_run_venv_capable,
    write_icml_tip_status,
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
    classify_plan_run_occupancy,
    g3_d_steering_ok,
    parse_int_list,
    run_sequential_live,
    score_pilot,
)

DEFAULT_BUDGET_CEILING = 20.0
# Tick 293: Nebius budget-fit pair estimate so 5 pairs + G2/G3 fit under ~$20.
DEFAULT_PAIR_ESTIMATE_USD = default_g4_pair_estimate_usd()
DEFAULT_SEEDS = (1, 2, 3, 4, 5)
DEFAULT_B_RUN_IDS = (1211, 1212, 1213, 1214, 1215)
DEFAULT_D_RUN_IDS = (1311, 1312, 1313, 1314, 1315)
_DEFAULT_G3G4_SHAPE = icml_g3g4_live_shape()
DEFAULT_EVAL_SUBSET = int(_DEFAULT_G3G4_SHAPE["eval_subset"])
DEFAULT_POPULATION_SIZE = int(_DEFAULT_G3G4_SHAPE["population_size"])
DEFAULT_ELITE_COUNT = int(_DEFAULT_G3G4_SHAPE["elite_count"])
DEFAULT_MAX_GEN = int(_DEFAULT_G3G4_SHAPE["max_gen"])
DEFAULT_DIAMOND_N = icml_diamond_n_for_stack()
LIVE_TABLE_MARKER = "### Live GPQA"
LIVE_TABLE_END_MARKER = "## Table 2"
TABLE2_LIVE_H2_MARKER = "<!-- LIVE_TABLE2_H2_START -->"
TABLE2_LIVE_H2_END = "<!-- LIVE_TABLE2_H2_END -->"
TABLE2_LIVE_H5_MARKER = "<!-- LIVE_TABLE2_H5_START -->"
TABLE2_LIVE_H5_END = "<!-- LIVE_TABLE2_H5_END -->"


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
    h2_by_d_run: dict[str, Any] = field(default_factory=dict)
    primary_pass: bool = False
    h2_pass: bool = False
    h5_pass: bool = False
    figures_written: list[str] = field(default_factory=list)
    ready_status: str = "IN_PROGRESS"
    # Tick 380: ledger marks G4 done for planned IDs → skip paid --live re-run.
    ledger_skip: bool = False

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.checks.append(CheckResult(name=name, ok=ok, detail=detail))
        if not ok:
            self.blockers.append(f"{name}: {detail}")


def _pair_estimate_usd() -> float:
    return float(default_g4_pair_estimate_usd())


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
    require_hf_for_diamond: bool = False,
    allow_stale_tip: bool = False,
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

    ceiling = _budget_ceiling()
    n_pairs = len(plans)
    resume_ok, blocked_incomplete, pairs_needing = classify_plan_run_occupancy(plans)
    # Tick 377: direct G4 --live must see ledger + unbilled local completes
    # (pipeline Tick 376 sync already hydrates before calling this runner).
    planned_ids = [rid for plan in plans for rid in (plan.b_run_id, plan.d_run_id)]
    _, hydrate_detail = hydrate_direct_gate_budget_spent(
        planned_ids,
        pair_estimate_usd=estimate,
        resolve_run_dir=_run_dir_for,
        repo_root=REPO_ROOT,
    )
    report.notes.append(hydrate_detail)
    # Tick 380: full-stage ledger complete → no billable pairs (cross-VM skip).
    ledger_skip, ledger_skip_detail = direct_gate_ledger_skip(
        "G4",
        planned_ids,
        path=REPO_ROOT / "docs" / "icml_budget_spent.json",
    )
    report.ledger_skip = bool(ledger_skip)
    if ledger_skip:
        report.notes.append(ledger_skip_detail)
        pairs_needing = 0
        if not resume_ok:
            resume_ok = [f"run_{rid}" for rid in planned_ids]
        report.add("ledger_stage_complete", True, ledger_skip_detail)
    spent = _budget_spent()
    # Tick 375: project only pairs that still need a live launch (mid-stack resume).
    billable_pairs = pairs_needing
    projected = spent + estimate * billable_pairs
    budget_ok = spent < ceiling and projected <= ceiling
    resume_note = (
        f"; resume-skip {len(resume_ok)} complete run(s)" if resume_ok else ""
    )
    if ledger_skip:
        resume_note += "; Tick 380 ledger-stage skip"
    report.add(
        "budget",
        budget_ok,
        (
            f"spent=${spent:.2f} ceiling=${ceiling:.2f} "
            f"estimate=${estimate:.2f}/pair × {billable_pairs} remaining "
            f"(of {n_pairs} planned) → projected=${projected:.2f}"
            f"{resume_note}"
        )
        + ("" if budget_ok else " — would exceed ceiling; refuse paid G4"),
    )

    report.add(
        "run_ids_free",
        not blocked_incomplete,
        (
            "all planned run IDs unused"
            if not resume_ok and not blocked_incomplete and not ledger_skip
            else (
                f"resume-ok complete: {', '.join(resume_ok)}"
                + (
                    f"; BLOCK incomplete: {', '.join(blocked_incomplete)}"
                    if blocked_incomplete
                    else (
                        " — Tick 380 ledger skip"
                        if ledger_skip
                        else " — Tick 375 will skip complete runs"
                    )
                )
            )
        ),
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

    # Tick 303: recipe + offline Bvd locks on direct G4 --live (not only pipeline).
    recipes_ok, recipe_problems = committed_g3g4_recipes_match_live_shape(
        repo_root=REPO_ROOT
    )
    report.add(
        "g3g4_recipes_match_live_shape",
        recipes_ok,
        "committed gate3/4 + Section 21.7 match icml_g3g4_live_shape()"
        if recipes_ok
        else "; ".join(recipe_problems) or "stale G3/G4 recipes",
    )
    offline_ok, offline_problems = committed_offline_bvd_matches_live_shape(
        repo_root=REPO_ROOT
    )
    report.add(
        "offline_bvd_matches_live_shape",
        offline_ok,
        "offline Bvd summary + paper IDs + figures match live shape"
        if offline_ok
        else "; ".join(offline_problems) or "stale offline Bvd artifacts",
    )

    # Tick 305: tip lineage on direct G4 --live (was pipeline-only Tick 269).
    tip_status = write_icml_tip_status(
        REPO_ROOT / "docs" / "icml_tip_status.json",
        fetch=False,
    )
    tip_ok = bool(tip_status.get("tip_ok_for_live"))
    if allow_stale_tip and not tip_ok:
        report.notes.append(
            "tip: --allow-stale-tip set; proceeding despite lineage blockers"
        )
        tip_ok = True
        tip_detail = "override (--allow-stale-tip); recover via icml_recover_tip.py"
    elif tip_ok:
        tip_detail = (
            f"local Tick {tip_status.get('local_tick')} matches remote tip "
            f"{tip_status.get('remote_tip_ref') or tip_status.get('remote_tip_sha')}"
        )
    else:
        tip_detail = "; ".join(tip_status.get("blockers") or []) or (
            "stale / missing ICML tip — recover via "
            f"{icml_python_cli()} scripts/icml_recover_tip.py --apply"
        )
    report.add("tip_ok_for_live", tip_ok, tip_detail)

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
        "g3g4_recipes_match_live_shape",
        "offline_bvd_matches_live_shape",
        "tip_ok_for_live",
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


def primary_criteria_pass(comparison: dict[str, Any] | None) -> bool:
    """PRIMARY: D beats B on ≥3/5 for gens30, cost30, or non-trivial final gap."""
    if not comparison or int(comparison.get("n_pairs") or 0) < 5:
        return False
    if comparison.get("primary_gens30_pass") or comparison.get("primary_cost30_pass"):
        return True
    if comparison.get("primary_gens25_pass") or comparison.get("primary_cost25_pass"):
        return True
    # Criterion (c): prefer explicit primary_final_pass (Tick 360 mean gap);
    # fall back to ≥3/5 final wins (>1pp) for older compare payloads.
    if comparison.get("primary_final_pass") is True:
        return True
    if int(comparison.get("d_wins_final") or 0) >= 3:
        gap = comparison.get("mean_final_gap")
        if gap is None:
            return True
        try:
            return float(gap) > 0.01
        except (TypeError, ValueError):
            return True
    return False


def g4_full_pairs_for_paper(
    b_dirs: list[Path],
    d_dirs: list[Path],
    plans: list[PilotPlan],
) -> bool:
    """Tick 410: True only when every planned B/D pair is present.

    Equal ``len(B)==len(D)`` is not enough — a mid-G4 abort (sia exit, never-steer,
    crash) can leave 1–4 complete pairs with equal counts and must not refresh
    Live Tables / READY. ``--refresh-paper-from-runs`` already requires 5 dirs;
    live + ``apply_paper_pack`` now share this gate.
    """
    n = len(plans)
    return bool(n) and len(b_dirs) == n and len(d_dirs) == n


def decide_g4_live_paper_action(
    *,
    b_dirs: list[Path],
    d_dirs: list[Path],
    plans: list[PilotPlan],
    run_notes: list[str],
) -> str:
    """Tick 409–410: decide live-path paper pack fate.

    Returns one of:
      - ``abort_never_steer`` — Tick 409 mid-G4 never-steer abort notes present
      - ``apply`` — all planned pairs complete (safe to ``apply_paper_pack``)
      - ``incomplete`` — partial / unequal pairs (skip paper pack)
    """
    if any("Tick 409:" in n for n in run_notes):
        return "abort_never_steer"
    if g4_full_pairs_for_paper(b_dirs, d_dirs, plans):
        return "apply"
    return "incomplete"


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


def h5_validity_pass(h5_by_d_run: dict[str, Any]) -> bool:
    """VALIDITY: majority of scored D seeds have Spearman ρ > 0.3 (≥3 when n≥5)."""
    n_pass, n_total = h5_pass_count(h5_by_d_run)
    if n_total <= 0:
        return False
    if n_total >= 5:
        return n_pass >= 3
    return n_pass == n_total and n_pass >= 1


def score_live_h2(d_dirs: list[Path], field: str | None = None) -> dict[str, Any]:
    """Compute H2 DNA trait skew for each Condition D run directory.

    Tick 361: default ``field=None`` auto-resolves the biased DNA field from the
    run's mutation-bias map (prefer ``tool_strategy``). Hard-coded ``memory``
    previously yielded empty bias_values when CABS steered tool_strategy — a
    latent live MECHANISM false-fail.

    Tick 396–397: ``compute_h2`` defaults to delay-all floor gen≥3 **plus**
    post-adoption tail (last 2 gens) so discover→adopt lag does not dilute
    preferred_share; do not override unless diagnosing legacy windows.
    """
    from epistemic_results import compute_h2

    out: dict[str, Any] = {}
    for d in d_dirs:
        try:
            out[d.name] = compute_h2(d, field=field)
        except Exception as exc:  # noqa: BLE001 — keep pack robust
            out[d.name] = {"error": str(exc), "field": field}
    return out


def h2_skew_pass(h2_by_d_run: dict[str, Any], *, min_share: float = 0.5) -> bool:
    """MECHANISM live H2: ≥3/5 D runs show *preferred*-allele DNA share ≥ min_share.

    Tick 364: require the fitness-weighted preferred allele (first ``bias_values``
    entry / ``preferred_share``), not mere contradiction-pool membership
    (``in_bias_share``). A population dominated by the loser allele still has
    ``in_bias_share=1.0`` and previously false-passed MECHANISM.
    """
    n_pass = 0
    n_total = 0
    for payload in h2_by_d_run.values():
        if not isinstance(payload, dict) or "error" in payload:
            continue
        n_total += 1
        pref_share = payload.get("preferred_share")
        if pref_share is None:
            # Derive from counts + preferred_value / bias_values[0] when missing.
            preferred = payload.get("preferred_value")
            bias = list(payload.get("bias_values") or [])
            if preferred is None and bias:
                preferred = bias[0]
            counts = payload.get("counts") or {}
            total = int(payload.get("total") or 0) or sum(
                int(v) for v in counts.values()
            )
            if preferred is not None and total > 0:
                pref_share = int(counts.get(str(preferred), 0)) / float(total)
        if isinstance(pref_share, (int, float)) and float(pref_share) >= min_share:
            n_pass += 1
            continue
    if n_total >= 5:
        return n_pass >= 3
    return n_pass >= 1 and n_pass == n_total


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
        # Tick 363: attribute BOTH PRIMARY gens thresholds (25% or 30%).
        b_g25 = b.get("gens_to_25")
        d_g25 = d.get("gens_to_25")
        if d_g25 is not None and (b_g25 is None or (isinstance(b_g25, int) and d_g25 < b_g25)):
            winners.append("D_gens25")
        elif b_g25 is not None and (d_g25 is None or (isinstance(d_g25, int) and b_g25 < d_g25)):
            winners.append("B_gens25")
        if d_g30 is not None and (b_g30 is None or (isinstance(b_g30, int) and d_g30 < b_g30)):
            winners.append("D_gens30")
        elif b_g30 is not None and (d_g30 is None or (isinstance(d_g30, int) and b_g30 < d_g30)):
            winners.append("B_gens30")
        b_c30 = b.get("cost_to_30") if isinstance(b.get("cost_to_30"), dict) else None
        d_c30 = d.get("cost_to_30") if isinstance(d.get("cost_to_30"), dict) else None
        b_c25 = b.get("cost_to_25") if isinstance(b.get("cost_to_25"), dict) else None
        d_c25 = d.get("cost_to_25") if isinstance(d.get("cost_to_25"), dict) else None

        def _cost_win(b_payload: Any, d_payload: Any, label: str) -> None:
            b_c = b_payload.get("cost") if isinstance(b_payload, dict) else None
            d_c = d_payload.get("cost") if isinstance(d_payload, dict) else None
            if d_c is None and b_c is None:
                return
            if d_c is not None and b_c is None:
                winners.append(f"D_{label}")
            elif b_c is not None and d_c is None:
                winners.append(f"B_{label}")
            elif (
                isinstance(d_c, (int, float))
                and isinstance(b_c, (int, float))
                and float(b_c) > 0
                and float(d_c) <= 0.85 * float(b_c)
            ):
                winners.append(f"D_{label}")
            elif (
                isinstance(d_c, (int, float))
                and isinstance(b_c, (int, float))
                and float(d_c) > 0
                and float(b_c) <= 0.85 * float(d_c)
            ):
                winners.append(f"B_{label}")

        _cost_win(b_c25, d_c25, "cost25")
        _cost_win(b_c30, d_c30, "cost30")
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


def _replace_marked_block(text: str, start_m: str, end_m: str, body: str) -> str:
    start = text.find(start_m)
    end = text.find(end_m)
    if start == -1 or end == -1 or end <= start:
        return text
    return text[:start] + start_m + "\n" + body.rstrip() + "\n" + text[end:]


def write_live_bvd_figures(
    *,
    comparison: dict[str, Any],
    h2_by_d_run: dict[str, Any],
    figures_dir: Path,
) -> list[str]:
    """Refresh Fig 1 (B vs D mean learning curves) and Fig 2 (pooled H2 histogram)."""
    written: list[str] = []
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return written

    figures_dir.mkdir(parents=True, exist_ok=True)
    rows = comparison.get("rows") or []

    # Fig 1: mean best-fitness curves across seeds for B and D
    def _mean_curve(side: str) -> tuple[list[int], list[float]]:
        series: dict[int, list[float]] = {}
        for pair in rows:
            curve = ((pair.get(side) or {}).get("learning_curve")) or {}
            for g_str, vals in curve.items():
                try:
                    g = int(g_str)
                except (TypeError, ValueError):
                    continue
                best = (vals or {}).get("best")
                if isinstance(best, (int, float)):
                    series.setdefault(g, []).append(float(best))
        gens = sorted(series)
        means = [sum(series[g]) / len(series[g]) for g in gens]
        return gens, means

    b_gens, b_means = _mean_curve("B")
    d_gens, d_means = _mean_curve("D")
    if b_gens or d_gens:
        fig, ax = plt.subplots(figsize=(6.5, 4))
        if b_gens:
            ax.plot(b_gens, b_means, marker="o", label="B darwinian-only")
        if d_gens:
            ax.plot(d_gens, d_means, marker="s", label="D epistemic_full")
        ax.axhline(0.30, color="gray", linestyle="--", linewidth=1, alpha=0.6, label="30% threshold")
        ax.set_xlabel("generation")
        ax.set_ylabel("mean best fitness")
        ax.set_title("Fig 1 — Live B vs D learning curves")
        ax.legend()
        ax.grid(True, alpha=0.3)
        path = figures_dir / "fig1_learning_curves.png"
        fig.tight_layout()
        fig.savefig(path, dpi=120)
        plt.close(fig)
        written.append(str(path))

    # Fig 2: pooled DNA trait counts across Condition D runs.
    # Tick 363: title field = majority of auto-resolved H2 fields (Tick 361),
    # not a hard-coded ``memory`` default (offline Tick 362 alignment).
    # Tick 365: title also surfaces majority preferred allele (MECHANISM key).
    pooled: dict[str, int] = {}
    field_votes: dict[str, int] = {}
    pref_votes: dict[str, int] = {}
    for payload in h2_by_d_run.values():
        if not isinstance(payload, dict) or "error" in payload:
            continue
        fld = payload.get("field")
        if isinstance(fld, str) and fld.strip():
            key = fld.strip()
            field_votes[key] = field_votes.get(key, 0) + 1
        pref = payload.get("preferred_value")
        if isinstance(pref, str) and pref.strip():
            pkey = pref.strip()
            pref_votes[pkey] = pref_votes.get(pkey, 0) + 1
        for k, v in (payload.get("counts") or {}).items():
            pooled[str(k)] = pooled.get(str(k), 0) + int(v)
    field = "auto"
    if field_votes:
        field = max(field_votes.items(), key=lambda kv: (kv[1], kv[0]))[0]
    preferred = None
    if pref_votes:
        preferred = max(pref_votes.items(), key=lambda kv: (kv[1], kv[0]))[0]
    if pooled:
        fig, ax = plt.subplots(figsize=(6.5, 4))
        labels = list(pooled.keys())
        vals = [pooled[k] for k in labels]
        colors = [
            "#1b4332" if preferred and str(lab) == str(preferred) else "#4c78a8"
            for lab in labels
        ]
        ax.bar(labels, vals, color=colors)
        title = f"Fig 2 — Live H2 DNA trait histogram ({field})"
        if preferred:
            title = f"{title}; prefer={preferred}"
        ax.set_title(title)
        ax.set_ylabel("count (pooled D runs)")
        ax.tick_params(axis="x", rotation=30)
        path = figures_dir / "fig2_mechanism.png"
        fig.tight_layout()
        fig.savefig(path, dpi=120)
        plt.close(fig)
        written.append(str(path))
    return written


def refresh_paper_artifacts_live(
    *,
    docs_path: Path,
    plans: list[PilotPlan],
    comparison: dict[str, Any],
    h5_by_d_run: dict[str, Any],
    timestamp: str,
    h2_by_d_run: dict[str, Any] | None = None,
    figures_written: list[str] | None = None,
) -> bool:
    """Replace Live GPQA Table 1 + Table 2 live H2/H5 rows in paper_artifacts.md."""
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
    # Tick 363: surface Tick 360 mean_final_gap / primary_final_pass in Live Table 1.
    gap = comparison.get("mean_final_gap")
    gap_s = _fmt_num(gap) if gap is not None else "—"
    summary = (
        f"\nPRIMARY flags: gens30={comparison.get('primary_gens30_pass')} "
        f"cost30={comparison.get('primary_cost30_pass')} "
        f"gens25={comparison.get('primary_gens25_pass')} "
        f"cost25={comparison.get('primary_cost25_pass')}; "
        f"primary_final_pass={comparison.get('primary_final_pass')} "
        f"mean_final_gap={gap_s}; "
        f"D final wins={comparison.get('d_wins_final')}/"
        f"{comparison.get('n_pairs')}. "
        f"Run IDs B={[p.b_run_id for p in plans]} D={[p.d_run_id for p in plans]}.\n"
    )
    h5_n_pass, h5_n = h5_pass_count(h5_by_d_run)
    h5_line = f"H5 ρ>0.3 on live D runs: **{h5_n_pass}/{h5_n}**.\n"
    h2 = h2_by_d_run or {}
    h2_ok = h2_skew_pass(h2)
    # Tick 367: when compare has a 5-seed aggregate, prefer h2_preferred_pass
    # (same key as offline Tick 366) so Live Table cannot hide loser-dominated
    # seed counts behind a binary skew_pass.
    n_pairs = int(comparison.get("n_pairs") or 0)
    d_wins_h2 = comparison.get("d_wins_h2")
    h2_pref_pass = comparison.get("h2_preferred_pass")
    if n_pairs >= 5 and h2_pref_pass is not None:
        h2_ok = bool(h2_pref_pass)
    h2_bits: list[str] = []
    for name, payload in h2.items():
        if not isinstance(payload, dict):
            continue
        share = payload.get("in_bias_share")
        pref = payload.get("preferred_share")
        pref_v = payload.get("preferred_value")
        # Tick 363: include auto-resolved DNA field (Tick 361) so live MECHANISM
        # rows show tool_strategy / retry_policy rather than an implied memory.
        # Tick 364: also surface preferred_share (MECHANISM pass key).
        fld = payload.get("field") or "auto"
        h2_bits.append(
            f"{name}: field={fld} preferred={pref_v or '—'} "
            f"preferred_share={_fmt_num(pref)} in_bias_share={_fmt_num(share)}"
        )
    h2_agg = ""
    if d_wins_h2 is not None and n_pairs:
        h2_agg = (
            f"d_wins_h2={d_wins_h2}/{n_pairs} "
            f"h2_preferred_pass={h2_pref_pass}; "
        )
    h2_line = (
        f"H2 live DNA skew: **{'PASS' if h2_ok else 'FAIL/partial'}** "
        f"({h2_agg}{'; '.join(h2_bits) if h2_bits else 'no H2 payloads'}).\n"
    )
    fig_line = ""
    if figures_written:
        fig_line = f"Figures refreshed: {', '.join(figures_written)}.\n"
    new_block = header + body + summary + h5_line + h2_line + fig_line + "\n"
    text = text[:start] + new_block + text[end:]

    # Table 2 live H2 / H5 marked rows (optional markers; no-op if absent).
    # Tick 367: include d_wins_h2 / h2_preferred_pass (offline Tick 366 aggregate).
    h2_agg_cell = ""
    if d_wins_h2 is not None and n_pairs:
        h2_agg_cell = (
            f"d_wins_h2={d_wins_h2}/{n_pairs} "
            f"h2_preferred_pass={h2_pref_pass}; "
        )
    h2_row = (
        f"| H2 trait skew (live API) | "
        f"{h2_agg_cell}{'; '.join(h2_bits) if h2_bits else '—'}; "
        f"skew_pass={h2_ok} | {'yes' if h2_ok else 'no'} |"
    )
    rhos = []
    for name, payload in h5_by_d_run.items():
        if isinstance(payload, dict) and "error" not in payload:
            rhos.append(f"{name}={_fmt_num(payload.get('spearman_rho'))}")
    h5_ok = h5_validity_pass(h5_by_d_run)
    h5_row = (
        f"| H5 Spearman ρ (live) | "
        f"{'; '.join(rhos) if rhos else '—'}; "
        f"ρ>0.3 = **{h5_n_pass}/{h5_n}** | {'yes' if h5_ok else 'no'} |"
    )
    text = _replace_marked_block(text, TABLE2_LIVE_H2_MARKER, TABLE2_LIVE_H2_END, h2_row)
    text = _replace_marked_block(text, TABLE2_LIVE_H5_MARKER, TABLE2_LIVE_H5_END, h5_row)

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


def update_icml_ready_from_g4(
    *,
    ready_path: Path,
    comparison: dict[str, Any] | None,
    primary_pass: bool,
    h2_pass: bool,
    h5_pass: bool,
    paper_refreshed: bool,
    figures_written: list[str],
    timestamp: str,
    allow_ready: bool = True,
) -> str:
    """Update ICML_READY checklist from live G4 evidence.

    Sets STATUS: READY only when PRIMARY + MECHANISM (live H2 **or** existing
    documented case-study checkbox) + live H5 + paper pack are all satisfied.
    Never sets READY from preflight / offline-only evidence (`allow_ready=False`).
    """
    if not ready_path.is_file():
        return "IN_PROGRESS"
    text = ready_path.read_text(encoding="utf-8")
    cmp_ = comparison or {}

    def _check_line(blob: str, prefix: str) -> str:
        """Mark the checklist line starting with ``- [ ] prefix`` as checked."""
        return re.sub(
            rf"^(\s*- )\[ \]({re.escape(prefix)})",
            r"\1[x]\2",
            blob,
            count=1,
            flags=re.MULTILINE,
        )

    if cmp_.get("primary_gens30_pass") or cmp_.get("primary_gens25_pass"):
        text = _check_line(text, " D beats B on ≥3/5 seeds for gens-to-threshold")
    if cmp_.get("primary_cost30_pass") or cmp_.get("primary_cost25_pass"):
        text = _check_line(text, " D beats B on ≥3/5 seeds for cost-to-threshold")
    # Tick 360: prefer primary_final_pass (mean gap >1pp + ≥3/5 seed wins).
    if cmp_.get("primary_final_pass") is True or int(cmp_.get("d_wins_final") or 0) >= 3:
        gap = cmp_.get("mean_final_gap")
        gap_ok = True
        if gap is not None:
            try:
                gap_ok = float(gap) > 0.01
            except (TypeError, ValueError):
                gap_ok = True
        if gap_ok:
            text = _check_line(text, " Non-trivial mean final accuracy gap")

    if h2_pass:
        text = _check_line(text, " Live API-run H2 DNA trait skew under contradiction bias")
    if h5_pass:
        text = _check_line(
            text,
            " Spearman ρ (`epistemic_value_t` vs `Δfitness_t+1`) > 0.3 on live",
        )
    if paper_refreshed:
        text = _check_line(text, " Table 1 (primary metrics by seed)")
        text = _check_line(text, " Table 2 (H2/H5 / cost)")
        text = _check_line(
            text,
            " Reproducible **live** run IDs listed in `docs/paper_artifacts.md`",
        )
    if figures_written:
        # Keep figure lines checked (already usually [x] from offline drafts).
        text = _check_line(text, " Figure 1 draft")
        text = _check_line(text, " Figure 2 draft")

    mechanism_ok = h2_pass or ("- [x] Documented case study" in text)
    paper_ok = bool(paper_refreshed)
    all_pass = bool(
        allow_ready and primary_pass and mechanism_ok and h5_pass and paper_ok
    )
    status = "READY" if all_pass else "IN_PROGRESS"
    audit = (
        f"_Last G4 pack refresh: {timestamp}; "
        f"PRIMARY={primary_pass}; live_H2={h2_pass}; live_H5={h5_pass}; "
        f"paper={paper_refreshed}; figs={len(figures_written)}; "
        f"allow_ready={allow_ready}_"
    )

    out_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("**STATUS:"):
            out_lines.append(f"**STATUS: {status}**")
            continue
        if line.startswith("_Last G4 pack refresh:"):
            continue
        out_lines.append(line)
        if line.startswith("**STATUS:"):
            # unreachable — handled above; keep structure simple
            pass
    # Insert audit immediately after STATUS line.
    final: list[str] = []
    for line in out_lines:
        final.append(line)
        if line.startswith("**STATUS:"):
            final.append("")
            final.append(audit)
    ready_path.write_text("\n".join(final) + "\n", encoding="utf-8")
    return status


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
        h5_n_pass, h5_n = h5_pass_count(report.h5_by_d_run)
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
                f"- H5 ρ>0.3: **{h5_n_pass}/{h5_n}** (validity_pass={report.h5_pass})",
                # Tick 367: surface Tick 366 d_wins_h2 / h2_preferred_pass (not binary only).
                f"- H2 preferred ≥0.5: **{cmp_.get('d_wins_h2', '—')}/"
                f"{cmp_.get('n_pairs', 0)}** "
                f"(h2_preferred_pass={cmp_.get('h2_preferred_pass')}; "
                f"skew_pass={'yes' if report.h2_pass else 'no'})",
                f"- PRIMARY aggregate: **{'PASS' if report.primary_pass else 'FAIL'}**",
                f"- paper_artifacts refreshed: **{'yes' if paper_refreshed else 'no'}**",
                f"- figures written: **{len(report.figures_written)}**",
                f"- ICML_READY STATUS: **{report.ready_status}**",
                "",
                "### H5 (Condition D)",
                "",
            ]
        )
        for name, h5 in report.h5_by_d_run.items():
            rho = h5.get("spearman_rho") if isinstance(h5, dict) else None
            lines.append(f"- `{name}`: Spearman ρ = `{rho}`")
        lines.append("")
        if report.h2_by_d_run:
            lines.extend(["### H2 (Condition D)", ""])
            for name, h2 in report.h2_by_d_run.items():
                if isinstance(h2, dict):
                    # Tick 365: gate4 report mirrors paper-pack MECHANISM key
                    # (preferred_share), not pool-only in_bias_share.
                    fld = h2.get("field") or "auto"
                    lines.append(
                        f"- `{name}`: field=`{fld}` "
                        f"preferred=`{h2.get('preferred_value')}` "
                        f"preferred_share=`{h2.get('preferred_share')}` "
                        f"in_bias_share=`{h2.get('in_bias_share')}` "
                        f"counts=`{h2.get('counts')}`"
                    )
            lines.append("")
        if executed and report.mode in {"live", "refresh-paper"}:
            lines.append(
                f"**Live G4 status:** PACK COMPLETE — `ICML_READY` → **{report.ready_status}** "
                "(READY only when PRIMARY + MECHANISM + live H5 + paper all pass)"
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

    secrets_line = icml_human_required_secrets_phrase(for_fetch_diamond=True)
    py = icml_python_cli()
    lines.extend(
        [
            "## Next",
            "",
            "1. Ensure live G2 smoke + G3 pilot passed before spending on G4.",
            f"2. Add `{secrets_line}` (see `docs/ICML_HUMAN_UNBLOCK.md`).",
            "3. Budget-check (`SIA_BUDGET_*` + `SIA_G4_PAIR_ESTIMATE_USD`), then:",
            f"   `{py} scripts/run_g4_multiseed.py --live --seeds 1,2,3,4,5 "
            "--b-run-ids 1211,1212,1213,1214,1215 --d-run-ids 1311,1312,1313,1314,1315 --fetch-diamond`",
            "4. After paid pairs, paper pack auto-refreshes Table 1/2 + Figs 1–2 + ICML_READY "
            "(or recover via `--refresh-paper-from-runs`).",
            "5. Do **not** set STATUS: READY from offline / G4 preflight alone.",
            "",
        ]
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    sidecar = out.with_suffix(".json")
    # Tick 386: preflight rewrites must not wipe live comparison / paper pack.
    # Preserve under prior_live_metrics so pipeline resume / ledger-skip trust
    # still works after cron --preflight-only (Tick 385 gate3 parity).
    existing = _load_gate4_sidecar_raw(out)
    prior_live_metrics = None
    if (
        executed
        and report.mode in {"live", "refresh-paper"}
        and isinstance(report.comparison, dict)
        and report.comparison
        and paper_refreshed
    ):
        prior_live_metrics = {
            "comparison": report.comparison,
            "h5_by_d_run": report.h5_by_d_run or {},
            "h2_by_d_run": report.h2_by_d_run or {},
            "executed": True,
            "paper_refreshed": True,
            "primary_pass": bool(report.primary_pass),
            "h2_pass": bool(report.h2_pass),
            "h5_pass": bool(report.h5_pass),
            "ready_status": report.ready_status,
            "figures_written": list(report.figures_written or []),
            # Tick 408: preserve steering positive-control across preflight wipe.
            "steering_applied_gen3": any(
                c.name == "steering_applied_gen3" and c.ok for c in report.checks
            ),
        }
    else:
        preserved_cmp, preserved_h5, preserved_h2, preserved_meta, _src = (
            _live_paper_from_gate4_sidecar(existing)
        )
        if preserved_cmp is not None:
            prior_live_metrics = {
                "comparison": preserved_cmp,
                "h5_by_d_run": preserved_h5,
                "h2_by_d_run": preserved_h2,
                "executed": True,
                "paper_refreshed": True,
                "primary_pass": bool(preserved_meta.get("primary_pass")),
                "h2_pass": bool(preserved_meta.get("h2_pass")),
                "h5_pass": bool(preserved_meta.get("h5_pass")),
                "ready_status": preserved_meta.get("ready_status"),
                "figures_written": list(preserved_meta.get("figures_written") or []),
            }
            # Carry steering flag from prior_live / top-level when present.
            prior_steering = None
            if isinstance(existing.get("prior_live_metrics"), dict):
                prior_steering = existing["prior_live_metrics"].get(
                    "steering_applied_gen3"
                )
            if prior_steering is None:
                prior_steering = existing.get("steering_applied_gen3")
            if prior_steering is None:
                for c in report.checks:
                    if c.name == "steering_applied_gen3":
                        prior_steering = c.ok
                        break
            if prior_steering is not None:
                prior_live_metrics["steering_applied_gen3"] = bool(prior_steering)
        elif isinstance(existing.get("prior_live_metrics"), dict):
            prior_live_metrics = existing.get("prior_live_metrics")
    steering_flag = None
    for c in report.checks:
        if c.name == "steering_applied_gen3":
            steering_flag = c.ok
            break
    payload = {
        "timestamp": report.timestamp,
        "mode": report.mode,
        "ready_for_live": report.ready_for_live,
        "primary_pass": report.primary_pass,
        "h2_pass": report.h2_pass,
        "h5_pass": report.h5_pass,
        "ready_status": report.ready_status,
        "plans": [asdict(p) for p in report.plans],
        "blockers": report.blockers,
        "checks": [asdict(c) for c in report.checks],
        "commands": report.commands,
        "comparison": report.comparison,
        "h5_by_d_run": report.h5_by_d_run,
        "h2_by_d_run": report.h2_by_d_run,
        "figures_written": report.figures_written,
        "notes": report.notes,
        "executed": executed,
        "paper_refreshed": paper_refreshed,
    }
    if steering_flag is not None:
        payload["steering_applied_gen3"] = steering_flag
    if prior_live_metrics is not None:
        payload["prior_live_metrics"] = prior_live_metrics
    sidecar.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    # Tick 389: mirror prior_live into committed evidence (cross-VM) + stash.
    if prior_live_metrics is not None:
        persist_prior_live_stash_from_working_tree(REPO_ROOT)


def _load_gate4_sidecar_raw(report_md: Path) -> dict[str, Any]:
    """Load gate4 JSON sidecar next to the markdown report (Tick 381)."""
    sidecar = report_md.with_suffix(".json")
    if not sidecar.is_file():
        return {}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _live_paper_from_gate4_sidecar(
    data: dict,
) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any], dict[str, Any], str]:
    """Tick 381/386: extract trustable live G4 paper-pack metrics from sidecar.

    Accepts ``mode in {live, refresh-paper}`` + ``executed`` + nonempty
    ``comparison`` + ``paper_refreshed``, or Tick 386 ``prior_live_metrics``
    preserved across preflight rewrites.
    """
    mode = str(data.get("mode") or "")
    executed = bool(data.get("executed"))
    comparison = data.get("comparison")
    paper_refreshed = bool(data.get("paper_refreshed"))
    if (
        mode in {"live", "refresh-paper"}
        and executed
        and isinstance(comparison, dict)
        and comparison
        and paper_refreshed
    ):
        meta = {
            "paper_refreshed": True,
            "primary_pass": bool(data.get("primary_pass")),
            "h2_pass": bool(data.get("h2_pass")),
            "h5_pass": bool(data.get("h5_pass")),
            "ready_status": data.get("ready_status"),
            "figures_written": data.get("figures_written") or [],
            "executed": True,
        }
        return (
            comparison,
            data.get("h5_by_d_run") or {},
            data.get("h2_by_d_run") or {},
            meta,
            "live",
        )
    prior = data.get("prior_live_metrics")
    if isinstance(prior, dict):
        prior_cmp = prior.get("comparison")
        if (
            isinstance(prior_cmp, dict)
            and prior_cmp
            and bool(prior.get("paper_refreshed"))
        ):
            meta = {
                "paper_refreshed": True,
                "primary_pass": bool(prior.get("primary_pass")),
                "h2_pass": bool(prior.get("h2_pass")),
                "h5_pass": bool(prior.get("h5_pass")),
                "ready_status": prior.get("ready_status"),
                "figures_written": prior.get("figures_written") or [],
                "executed": True,
            }
            return (
                prior_cmp,
                prior.get("h5_by_d_run") or {},
                prior.get("h2_by_d_run") or {},
                meta,
                "prior_live_metrics",
            )
    return None, {}, {}, {}, ""


def refresh_paper_pack_on_ledger_skip(
    report: G4PreflightReport,
    *,
    paper_artifacts: Path,
    ready_path: Path,
    figures_dir: Path,
    gate4_report_md: Path,
    skip_paper_refresh: bool = False,
    allow_ready: bool = True,
) -> tuple[bool, str]:
    """Tick 381: rebuild / trust paper pack after direct G4 ledger-skip.

    Tick 380 early-returned on ``ledger_skip`` without calling ``apply_paper_pack``.
    Pipeline resume already refreshes via Tick 374; direct ``run_g4_multiseed.py
    --live`` did not — so a cross-VM (or same-VM) ledger skip could leave
    ``ICML_READY`` stuck IN_PROGRESS after paid G4 evidence existed.

    Prefer local complete B/D dirs → ``apply_paper_pack``. Else trust a
    live-executed / refresh-paper sidecar with non-null comparison +
    ``paper_refreshed`` (or Tick 386 ``prior_live_metrics`` preserved across
    preflight; never promote READY from a bare preflight sidecar).
    Tick 408: refuse trust when ``steering_applied_gen3`` is explicitly false.
    """
    b_ids = [p.b_run_id for p in report.plans]
    d_ids = [p.d_run_id for p in report.plans]
    b_dirs: list[Path] = []
    d_dirs: list[Path] = []
    for rid in b_ids:
        found = _run_dir_for(rid)
        if found is not None and darwinian_run_complete(found):
            b_dirs.append(found)
    for rid in d_ids:
        found = _run_dir_for(rid)
        if found is not None and darwinian_run_complete(found):
            d_dirs.append(found)

    if len(b_dirs) == len(b_ids) and len(d_dirs) == len(d_ids) and b_ids:
        report.notes.append(
            "Tick 381: ledger-skip — re-scoring local B/D into paper pack "
            f"(allow_ready={allow_ready})"
        )
        paper_refreshed = apply_paper_pack(
            report,
            b_dirs=b_dirs,
            d_dirs=d_dirs,
            paper_artifacts=paper_artifacts,
            ready_path=ready_path,
            figures_dir=figures_dir,
            skip_paper_refresh=skip_paper_refresh,
            allow_ready=allow_ready,
        )
        steering_ok = any(
            c.name == "steering_applied_gen3" and c.ok for c in report.checks
        )
        if not steering_ok:
            note = (
                "Tick 408: ledger-skip local re-score — Condition D gen≥3 "
                "steering FAILED — refuse paper-pack READY trust"
            )
            report.notes.append(note)
            return False, note
        return (
            paper_refreshed,
            "Tick 381: re-scored G4 from local B/D + refreshed paper pack "
            f"(primary={report.primary_pass}; h2={report.h2_pass}; "
            f"h5={report.h5_pass}; paper={paper_refreshed}; "
            f"ICML_READY={report.ready_status})",
        )

    data = _load_gate4_sidecar_raw(gate4_report_md)
    comparison, h5, h2, meta, source = _live_paper_from_gate4_sidecar(data)
    if comparison is not None:
        # Tick 408: refuse never-steer sidecar (G3 Tick 407 parity).
        prior_steering = None
        prior = data.get("prior_live_metrics")
        if isinstance(prior, dict) and "steering_applied_gen3" in prior:
            prior_steering = prior.get("steering_applied_gen3")
        elif "steering_applied_gen3" in data:
            prior_steering = data.get("steering_applied_gen3")
        if prior_steering is False:
            note = (
                "Tick 408: trusted gate4 sidecar but steering_applied_gen3=false "
                "— refuse READY / paper-pack trust on never-steer Condition D"
            )
            report.checks.append(
                CheckResult("steering_applied_gen3", False, note)
            )
            report.notes.append(note)
            return False, note
        report.comparison = comparison
        report.primary_pass = bool(meta.get("primary_pass"))
        report.h2_pass = bool(meta.get("h2_pass"))
        report.h5_pass = bool(meta.get("h5_pass"))
        report.h5_by_d_run = h5
        report.h2_by_d_run = h2
        figs = meta.get("figures_written")
        if isinstance(figs, list):
            report.figures_written = figs
        ready_status = meta.get("ready_status")
        if isinstance(ready_status, str) and ready_status:
            report.ready_status = ready_status
        if source == "prior_live_metrics":
            note = (
                "Tick 386: trusted gate4 prior_live_metrics after ledger-skip "
                f"(no/partial local G4 dirs; ICML_READY={ready_status or 'n/a'})"
            )
        else:
            mode = str(data.get("mode") or "")
            note = (
                "Tick 381: trusted live-executed gate4 sidecar paper pack "
                f"(no/partial local G4 dirs; mode={mode}; "
                f"ICML_READY={ready_status or 'n/a'})"
            )
        if prior_steering is True:
            note += "; steering_applied_gen3=true"
            report.checks.append(
                CheckResult(
                    "steering_applied_gen3",
                    True,
                    "sidecar recorded gen≥3 Condition D steering",
                )
            )
        report.notes.append(note)
        return True, note

    mode = str(data.get("mode") or "")
    executed = bool(data.get("executed"))
    paper_refreshed = bool(data.get("paper_refreshed"))
    note = (
        "Tick 381: ledger-skip but no local G4 artifacts and no live-executed "
        f"gate4 paper pack (mode={mode or 'missing'!r}, executed={executed}, "
        f"paper_refreshed={paper_refreshed}) — ICML_READY not updated"
    )
    report.notes.append(note)
    return False, note


def apply_paper_pack(
    report: G4PreflightReport,
    *,
    b_dirs: list[Path],
    d_dirs: list[Path],
    paper_artifacts: Path,
    ready_path: Path,
    figures_dir: Path,
    skip_paper_refresh: bool = False,
    allow_ready: bool = True,
) -> bool:
    """Score PRIMARY/H2/H5, refresh paper pack + figures + ICML_READY. Returns paper_refreshed.

    Tick 408: Condition D gen≥3 steering positive-control — never-steer D
    forces ``allow_ready=False`` so ``ICML_READY`` cannot flip to READY.

    Tick 410: refuse when ``len(B)/len(D)`` ≠ ``len(plans)`` (partial Live Table).
    """
    # Tick 410: never refresh Live Tables from a partial G4 pair set.
    if not g4_full_pairs_for_paper(b_dirs, d_dirs, report.plans):
        report.notes.append(
            "Tick 410: refuse paper pack — need all planned pairs "
            f"(got B={len(b_dirs)} D={len(d_dirs)} plans={len(report.plans)}; "
            "refuse partial Live Table / READY)"
        )
        report.checks.append(
            CheckResult(
                "g4_full_pairs",
                False,
                f"B={len(b_dirs)} D={len(d_dirs)} plans={len(report.plans)}",
            )
        )
        return False

    # Tick 408: prove delay-all lifted on every Condition D run before READY.
    steering_ok, steering_checks = g3_d_steering_ok(d_dirs)
    for c in steering_checks:
        report.checks.append(c)
    if not steering_ok:
        allow_ready = False
        report.notes.append(
            "Tick 408: Condition D gen≥3 steering FAILED — refuse ICML_READY "
            "READY (never-steer D must not promote paper pack)"
        )

    # Tick 368: score_pilot also returns H2 (preferred-allele); avoid double compute_h2.
    comparison, h5, h2 = score_pilot(b_dirs, d_dirs)
    report.comparison = comparison
    report.h5_by_d_run = h5
    report.h2_by_d_run = h2
    report.primary_pass = primary_criteria_pass(comparison)
    report.h5_pass = h5_validity_pass(h5)
    # Tick 367: align MECHANISM with compare aggregate when n≥5 (Tick 366 key).
    if (
        int(comparison.get("n_pairs") or 0) >= 5
        and comparison.get("h2_preferred_pass") is not None
    ):
        report.h2_pass = bool(comparison["h2_preferred_pass"])
    else:
        report.h2_pass = h2_skew_pass(h2)

    paper_refreshed = False
    figures: list[str] = []
    if not skip_paper_refresh:
        figures = write_live_bvd_figures(
            comparison=comparison,
            h2_by_d_run=h2,
            figures_dir=figures_dir,
        )
        report.figures_written = figures
        paper_refreshed = refresh_paper_artifacts_live(
            docs_path=paper_artifacts,
            plans=report.plans,
            comparison=comparison,
            h5_by_d_run=h5,
            h2_by_d_run=h2,
            figures_written=figures,
            timestamp=report.timestamp,
        )
        report.notes.append(
            f"paper_artifacts refreshed={paper_refreshed} → {paper_artifacts}; "
            f"figs={len(figures)}"
        )
        report.ready_status = update_icml_ready_from_g4(
            ready_path=ready_path,
            comparison=comparison,
            primary_pass=report.primary_pass,
            h2_pass=report.h2_pass,
            h5_pass=report.h5_pass,
            paper_refreshed=paper_refreshed,
            figures_written=figures,
            timestamp=report.timestamp,
            allow_ready=allow_ready,
        )
        report.notes.append(f"ICML_READY STATUS={report.ready_status} → {ready_path}")
    return paper_refreshed


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
    mode.add_argument(
        "--refresh-paper-from-runs",
        action="store_true",
        help="Rebuild paper pack / READY from existing B/D run dirs (no API)",
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
    p.add_argument(
        "--b-run-dirs",
        nargs="*",
        type=Path,
        default=[],
        help="Existing Condition B run dirs (with --refresh-paper-from-runs)",
    )
    p.add_argument(
        "--d-run-dirs",
        nargs="*",
        type=Path,
        default=[],
        help="Existing Condition D run dirs (with --refresh-paper-from-runs)",
    )
    p.add_argument("--eval-subset", type=int, default=DEFAULT_EVAL_SUBSET)
    p.add_argument("--population-size", type=int, default=DEFAULT_POPULATION_SIZE)
    p.add_argument("--elite-count", type=int, default=DEFAULT_ELITE_COUNT)
    p.add_argument("--max-gen", type=int, default=DEFAULT_MAX_GEN)
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
        "--icml-ready",
        type=Path,
        default=REPO_ROOT / "docs" / "ICML_READY.md",
        help="ICML ready checklist path",
    )
    p.add_argument(
        "--figures-dir",
        type=Path,
        default=REPO_ROOT / "docs" / "figures",
        help="Directory for fig1/fig2 refresh",
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
    p.add_argument("--diamond-n", type=int, default=DEFAULT_DIAMOND_N)
    p.add_argument(
        "--allow-stale-tip",
        action="store_true",
        help="Allow --live even when local Tick lags remote tip (dangerous; Tick 305)",
    )
    p.add_argument(
        "--skip-paper-refresh",
        action="store_true",
        help="Do not rewrite docs/paper_artifacts.md / figures / ICML_READY after scoring",
    )
    p.add_argument(
        "--allow-ready",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Permit STATUS: READY when criteria pass. Default: true for --live, "
        "false for --refresh-paper-from-runs (pass --allow-ready after real live pairs).",
    )
    args = p.parse_args(argv)

    if args.refresh_paper_from_runs:
        selected = "refresh-paper"
    elif args.live:
        selected = "live"
    else:
        selected = "preflight"

    if args.allow_ready is None:
        allow_ready_flag = selected == "live"
    else:
        allow_ready_flag = bool(args.allow_ready)

    try:
        seeds = parse_int_list(args.seeds)
        b_ids = parse_int_list(args.b_run_ids)
        d_ids = parse_int_list(args.d_run_ids)
        plans = build_g4_plans(seeds, b_ids, d_ids)
    except ValueError as exc:
        print(f"G4 plan error: {exc}", file=sys.stderr)
        return 2

    if args.max_gen > 6:
        print("G4 refuses max_gen > 6 (Section 21.5 / Tick 296 budget shape)", file=sys.stderr)
        return 2

    # Recovery path: score existing runs into the paper pack (no paid API).
    if selected == "refresh-paper":
        b_dirs = [p.resolve() for p in args.b_run_dirs]
        d_dirs = [p.resolve() for p in args.d_run_dirs]
        if len(b_dirs) != 5 or len(d_dirs) != 5:
            print(
                "G4 --refresh-paper-from-runs requires exactly 5 --b-run-dirs and 5 --d-run-dirs",
                file=sys.stderr,
            )
            return 2
        if any(not p.is_dir() for p in b_dirs + d_dirs):
            print("G4 refresh refused — one or more run dirs missing", file=sys.stderr)
            return 2
        report = G4PreflightReport(
            timestamp=_utc_now(),
            mode="refresh-paper",
            plans=plans,
            ready_for_live=False,
        )
        report.notes.append(
            f"refresh-paper-from-runs (no API; pack rebuild; allow_ready={allow_ready_flag})"
        )
        paper_refreshed = apply_paper_pack(
            report,
            b_dirs=b_dirs,
            d_dirs=d_dirs,
            paper_artifacts=args.paper_artifacts,
            ready_path=args.icml_ready,
            figures_dir=args.figures_dir,
            skip_paper_refresh=args.skip_paper_refresh,
            allow_ready=allow_ready_flag,
        )
        write_gate4_report(
            report, args.report, executed=True, paper_refreshed=paper_refreshed
        )
        print(f"G4 paper refresh → {args.report}")
        print(
            f"primary_pass={report.primary_pass} h2_pass={report.h2_pass} "
            f"h5_pass={report.h5_pass} STATUS={report.ready_status}"
        )
        steering_ok = any(
            c.name == "steering_applied_gen3" and c.ok for c in report.checks
        )
        # Tick 408: never-steer → exit 4 even if comparison scored.
        if report.comparison is None or not steering_ok:
            return 4
        return 0

    fetch_notes: list[str] = []
    # Tick 278: auto-wire local diamond CSV under --fetch-diamond (match cron).
    diamond_csv, csv_auto = autowire_diamond_csv(
        args.diamond_csv, fetch_diamond=bool(args.fetch_diamond), repo_root=REPO_ROOT
    )
    args.diamond_csv = diamond_csv
    require_hf = bool(args.fetch_diamond) and args.diamond_csv is None
    allow_stale = bool(args.allow_stale_tip)

    # Tick 275/278: refuse --live --fetch-diamond without HF/CSV before materialize.
    if selected == "live" and require_hf:
        secrets_status = collect_icml_secrets_status()
        if not secrets_status.get("fetch_diamond_ok"):
            report = run_preflight(
                mode=selected,
                plans=plans,
                require_hf_for_diamond=True,
                allow_stale_tip=allow_stale,
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
            write_gate4_report(report, args.report)
            print(
                "G4 refused --live --fetch-diamond "
                f"(fetch_diamond_ok=false) → {args.report}",
                file=sys.stderr,
            )
            for b in report.blockers:
                print(f"  BLOCK: {b}", file=sys.stderr)
            return 4

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
                    f"G4 live refused — runtime deps before diamond failed: {deps_detail}",
                    file=sys.stderr,
                )
                report = run_preflight(
                    mode=selected,
                    plans=plans,
                    require_hf_for_diamond=require_hf,
                    allow_stale_tip=allow_stale,
                )
                report.notes.extend(fetch_notes)
                write_gate4_report(report, args.report)
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
                print(f"G4 live refused — --fetch-diamond failed: {exc}", file=sys.stderr)
                report = run_preflight(
                    mode=selected,
                    plans=plans,
                    require_hf_for_diamond=require_hf,
                    allow_stale_tip=allow_stale,
                )
                report.notes.extend(fetch_notes)
                write_gate4_report(report, args.report)
                return 3

    report = run_preflight(
        mode=selected,
        plans=plans,
        require_hf_for_diamond=require_hf,
        allow_stale_tip=allow_stale,
    )
    report.notes.extend(fetch_notes)

    if selected == "preflight":
        write_gate4_report(report, args.report)
        print(f"G4 preflight written → {args.report}")
        print(f"ready_for_live={report.ready_for_live}")
        if report.ledger_skip:
            print("ledger_skip=True (Tick 380 — --live would no-op)")
        for b in report.blockers:
            print(f"  BLOCK: {b}")
        return 0

    # Tick 380: ledger-complete G4 → exit 0 without sia (even if secrets absent).
    # Tick 381: still refresh paper pack / ICML_READY (pipeline Tick 374 parity).
    if report.ledger_skip:
        report.notes.append(
            "Tick 380: skipped paid G4 — ledger stages_complete already lists G4 "
            "for planned run IDs"
        )
        paper_refreshed, pack_note = refresh_paper_pack_on_ledger_skip(
            report,
            paper_artifacts=args.paper_artifacts,
            ready_path=args.icml_ready,
            figures_dir=args.figures_dir,
            gate4_report_md=args.report,
            skip_paper_refresh=args.skip_paper_refresh,
            allow_ready=allow_ready_flag,
        )
        report.notes.append(pack_note)
        write_gate4_report(
            report,
            args.report,
            executed=bool(report.comparison),
            paper_refreshed=paper_refreshed,
        )
        print(f"G4 live skipped (ledger resume) → {args.report}")
        print(pack_note)
        print(
            f"primary_pass={report.primary_pass} h2_pass={report.h2_pass} "
            f"h5_pass={report.h5_pass} STATUS={report.ready_status}"
        )
        return 0

    if not report.ready_for_live:
        write_gate4_report(report, args.report)
        print("G4 live refused — preflight failed", file=sys.stderr)
        for b in report.blockers:
            print(f"  BLOCK: {b}", file=sys.stderr)
        return 3

    # Reuse G3 sequential executor (same hard-stop: never parallel).
    # Tick 409: abort remaining pairs after first never-steer D (save budget).
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
        abort_on_d_never_steer=True,
    )
    report.notes.extend(run_notes)

    paper_refreshed = False
    steering_ok = False
    # Tick 409–410: never-steer abort OR partial pairs → skip paper pack.
    paper_action = decide_g4_live_paper_action(
        b_dirs=b_dirs,
        d_dirs=d_dirs,
        plans=report.plans,
        run_notes=run_notes,
    )
    if paper_action == "abort_never_steer":
        # Record steering checks for completed D dirs; do NOT promote a
        # partial Live Table / READY from <5 pairs after mid-G4 abort.
        if d_dirs:
            _ok, steering_checks = g3_d_steering_ok(d_dirs)
            for c in steering_checks:
                report.checks.append(c)
        report.notes.append(
            "Tick 409: aborted remaining G4 pairs on never-steer — skipped "
            "paper pack (refuse partial Live Table / READY)"
        )
        steering_ok = False
    elif paper_action == "apply":
        paper_refreshed = apply_paper_pack(
            report,
            b_dirs=b_dirs,
            d_dirs=d_dirs,
            paper_artifacts=args.paper_artifacts,
            ready_path=args.icml_ready,
            figures_dir=args.figures_dir,
            skip_paper_refresh=args.skip_paper_refresh,
            allow_ready=allow_ready_flag,
        )
        steering_ok = any(
            c.name == "steering_applied_gen3" and c.ok for c in report.checks
        )
        if not steering_ok:
            report.notes.append(
                "Tick 408: Condition D gen≥3 steering FAILED — refuse G4 ledger "
                "stamp / READY (never-steer)"
            )
    else:
        report.notes.append(
            "Tick 410: incomplete / partial B/D pairs "
            f"(B={len(b_dirs)} D={len(d_dirs)} plans={len(report.plans)}) — "
            "skipped compare_b_vs_d / paper refresh"
        )

    # Tick 379: stamp ledger G4 after direct live when every planned run is complete.
    # Tick 408: only stamp when gen≥3 steering also passes (mirror G3 Tick 407).
    planned_ids = [p.b_run_id for p in report.plans] + [
        p.d_run_id for p in report.plans
    ]
    g4_ok = bool(report.comparison) and steering_ok
    if g4_ok:
        _, persist_detail = persist_direct_gate_stage_spend(
            "G4",
            planned_ids,
            pair_estimate_usd=float(DEFAULT_PAIR_ESTIMATE_USD),
            resolve_run_dir=_run_dir_for,
            repo_root=REPO_ROOT,
        )
        report.notes.append(persist_detail)
    else:
        report.notes.append(
            "Tick 408: skipped G4 ledger stamp — need comparison + gen≥3 steering"
        )

    write_gate4_report(
        report, args.report, executed=True, paper_refreshed=paper_refreshed
    )
    print(f"G4 report → {args.report}")
    print(
        f"primary_pass={report.primary_pass} h2_pass={report.h2_pass} "
        f"h5_pass={report.h5_pass} STATUS={report.ready_status}"
    )
    if report.comparison is None or not steering_ok:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
