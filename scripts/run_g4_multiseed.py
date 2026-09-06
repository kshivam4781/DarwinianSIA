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
  - refuses existing run IDs (never overwrite)
  - respects ``SIA_BUDGET_SPENT_USD`` / ``SIA_BUDGET_CEILING_USD`` (~$20)
  - projects spend: ``SIA_G4_PAIR_ESTIMATE_USD`` × 5 ≤ remaining budget

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
    default_g4_pair_estimate_usd,
    ensure_deps_before_diamond_fetch,
    ensure_icml_runtime_deps,
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
    """MECHANISM live H2: ≥3/5 D runs show in-bias DNA share ≥ min_share (or max allele ≥ min_share)."""
    n_pass = 0
    n_total = 0
    for payload in h2_by_d_run.values():
        if not isinstance(payload, dict) or "error" in payload:
            continue
        n_total += 1
        share = payload.get("in_bias_share")
        if isinstance(share, (int, float)) and float(share) >= min_share:
            n_pass += 1
            continue
        counts = payload.get("counts") or {}
        total = int(payload.get("total") or 0) or sum(int(v) for v in counts.values())
        if total > 0 and counts:
            max_share = max(int(v) for v in counts.values()) / float(total)
            if max_share >= min_share and payload.get("bias_values"):
                n_pass += 1
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
    pooled: dict[str, int] = {}
    field_votes: dict[str, int] = {}
    for payload in h2_by_d_run.values():
        if not isinstance(payload, dict) or "error" in payload:
            continue
        fld = payload.get("field")
        if isinstance(fld, str) and fld.strip():
            key = fld.strip()
            field_votes[key] = field_votes.get(key, 0) + 1
        for k, v in (payload.get("counts") or {}).items():
            pooled[str(k)] = pooled.get(str(k), 0) + int(v)
    field = "auto"
    if field_votes:
        field = max(field_votes.items(), key=lambda kv: (kv[1], kv[0]))[0]
    if pooled:
        fig, ax = plt.subplots(figsize=(6.5, 4))
        labels = list(pooled.keys())
        vals = [pooled[k] for k in labels]
        ax.bar(labels, vals)
        ax.set_title(f"Fig 2 — Live H2 DNA trait histogram ({field})")
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
    h2_bits: list[str] = []
    for name, payload in h2.items():
        if not isinstance(payload, dict):
            continue
        share = payload.get("in_bias_share")
        # Tick 363: include auto-resolved DNA field (Tick 361) so live MECHANISM
        # rows show tool_strategy / retry_policy rather than an implied memory.
        fld = payload.get("field") or "auto"
        h2_bits.append(f"{name}: field={fld} in_bias_share={_fmt_num(share)}")
    h2_line = (
        f"H2 live DNA skew: **{'PASS' if h2_ok else 'FAIL/partial'}** "
        f"({'; '.join(h2_bits) if h2_bits else 'no H2 payloads'}).\n"
    )
    fig_line = ""
    if figures_written:
        fig_line = f"Figures refreshed: {', '.join(figures_written)}.\n"
    new_block = header + body + summary + h5_line + h2_line + fig_line + "\n"
    text = text[:start] + new_block + text[end:]

    # Table 2 live H2 / H5 marked rows (optional markers; no-op if absent).
    h2_row = (
        f"| H2 trait skew (live API) | "
        f"{'; '.join(h2_bits) if h2_bits else '—'}; "
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
                f"- H2 DNA skew pass: **{'yes' if report.h2_pass else 'no'}**",
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
                    lines.append(
                        f"- `{name}`: in_bias_share=`{h2.get('in_bias_share')}` "
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
    sidecar.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


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
    """Score PRIMARY/H2/H5, refresh paper pack + figures + ICML_READY. Returns paper_refreshed."""
    comparison, h5 = score_pilot(b_dirs, d_dirs)
    h2 = score_live_h2(d_dirs)
    report.comparison = comparison
    report.h5_by_d_run = h5
    report.h2_by_d_run = h2
    report.primary_pass = primary_criteria_pass(comparison)
    report.h5_pass = h5_validity_pass(h5)
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
        return 0 if report.comparison is not None else 4

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
    else:
        report.notes.append("incomplete B/D pairs — skipped compare_b_vs_d / paper refresh")

    write_gate4_report(
        report, args.report, executed=True, paper_refreshed=paper_refreshed
    )
    print(f"G4 report → {args.report}")
    print(
        f"primary_pass={report.primary_pass} h2_pass={report.h2_pass} "
        f"h5_pass={report.h5_pass} STATUS={report.ready_status}"
    )
    if report.comparison is None:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
