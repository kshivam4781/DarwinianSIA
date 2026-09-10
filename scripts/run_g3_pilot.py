#!/usr/bin/env python3
"""ICML Gate G3 — sequential Condition B vs D pilot runner.

Section 21.5 Gate G3: pilot B vs D on 1–2 seeds, ``max_gen ≤ 6``, before
full 5-seed G4 spend. Tick 296: default shape is Nebius budget-fit
(``eval_subset=5``, pop=4, elite=2, max_gen=6); Anthropic meta keeps
historical ``eval_subset=15`` / pop=4 / elite=2 / max_gen=5.

Hard stops (never violate):
  - no two GPQA jobs in parallel (B then D, sequential)
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
  - Tick 379: after successful live (all planned B/D complete + scored),
    persist ledger stage ``G3`` (hydrate alone never stamped stages)
  - Tick 380: ``--live`` skips paid re-run when committed ledger already marks
    ``G3`` complete for the planned run IDs (pipeline Tick 285 parity)
  - Tick 382: ledger-skip still re-scores / trusts G3 pilot metrics (pipeline
    Tick 373 parity — Tick 380 wrote ``executed=False`` null comparison and
    could clobber a live-executed gate3 sidecar needed for G4 advance)
  - Tick 385: preflight preserves ``prior_live_metrics`` so cron
    ``--preflight-only`` cannot wipe live comparison/H2/H5 that pipeline
    ``load_g3_metrics_for_g4`` / ledger-skip trust after G3 (Tick 384 G2
    ``prior_live_post`` parity)
  - Tick 407: Condition D post-checks require gen≥3 feedback to carry the
    Contradiction-Aware agenda (positive control that delay-all *lifted*).
    Tick 406 only proves fair gen1→gen2 skip — without this, a never-steer
    regression still PASSes G2 and can burn G3/G4 with D≈B
  - Tick 409: ``run_sequential_live(abort_on_d_never_steer=True)`` aborts
    remaining pairs after first never-steer Condition D
  - Tick 411: refuse ``score_pilot`` / G4 advance unless
    ``len(B)==len(D)==len(plans)`` (Tick 410 G4 full-pair parity — equal
    B/D counts after mid-abort must not promote a partial pilot)
  - respects ``SIA_BUDGET_SPENT_USD`` / ``SIA_BUDGET_CEILING_USD`` (~$20)
  - optional rough spend estimate before launching paid pairs (remaining only)

Modes:
  --preflight-only   check blockers; refresh live section of docs/gate3_report.md
  --live             paid sequential B then D (keys + non-smoke GPQA required)

Examples (Linux/cloud: python3; Windows venv: python):
  python3 scripts/run_g3_pilot.py --preflight-only
  python3 scripts/run_g3_pilot.py --live --seeds 1 --b-run-ids 1201 --d-run-ids 1301
  python3 scripts/run_g3_pilot.py --live --seeds 1,2 --fetch-diamond
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
    committed_g3g4_recipes_match_live_shape,
    committed_offline_bvd_matches_live_shape,
    darwinian_run_complete,
    default_g3_pair_estimate_usd,
    ensure_deps_before_diamond_fetch,
    ensure_icml_runtime_deps,
    hydrate_direct_gate_budget_spent,
    persist_direct_gate_stage_spend,
    persist_prior_live_stash_from_working_tree,
    direct_gate_ledger_skip,
    icml_diamond_n_for_stack,
    icml_g3g4_live_shape,
    icml_human_required_secrets_phrase,
    icml_meta_profile_cli_flags,
    icml_meta_requires_anthropic,
    icml_python_cli,
    icml_target_profile_cli_flags,
    probe_icml_meta_profile,
    probe_icml_target_profile_nebius,
    probe_per_run_venv_capable,
    write_icml_tip_status,
)

DEFAULT_BUDGET_CEILING = 20.0
# Tick 293: Nebius-aware default (budget-fit shape); override via SIA_G3_PAIR_ESTIMATE_USD.
DEFAULT_PAIR_ESTIMATE_USD = default_g3_pair_estimate_usd()
DEFAULT_SEEDS = (1,)
DEFAULT_B_RUN_IDS = (1201,)
DEFAULT_D_RUN_IDS = (1301,)
_DEFAULT_G3G4_SHAPE = icml_g3g4_live_shape()
DEFAULT_EVAL_SUBSET = int(_DEFAULT_G3G4_SHAPE["eval_subset"])
DEFAULT_POPULATION_SIZE = int(_DEFAULT_G3G4_SHAPE["population_size"])
DEFAULT_ELITE_COUNT = int(_DEFAULT_G3G4_SHAPE["elite_count"])
DEFAULT_MAX_GEN = int(_DEFAULT_G3G4_SHAPE["max_gen"])
DEFAULT_DIAMOND_N = icml_diamond_n_for_stack()
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
    # Tick 368: live H2 preferred-allele payloads (parity with G4 Tick 364–367).
    h2_by_d_run: dict[str, Any] = field(default_factory=dict)
    # Tick 380: ledger marks G3 done for planned IDs → skip paid --live re-run.
    ledger_skip: bool = False

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
    # Tick 293: resolve via helper so Nebius budget-fit defaults apply even if
    # this module was imported under a different meta profile env.
    return float(default_g3_pair_estimate_usd())


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


def classify_plan_run_occupancy(
    plans: list[PilotPlan],
) -> tuple[list[str], list[str], int]:
    """Tick 375: split planned run IDs into resume-complete vs blocked.

    Returns ``(resume_ok, blocked_incomplete, pairs_needing_work)``.
    - ``resume_ok``: dirs that already have Darwinian ``results.json`` (skip).
    - ``blocked_incomplete``: dirs that exist but are incomplete — never overwrite.
    - ``pairs_needing_work``: seed pairs where B and/or D still need a live launch
      (drives remaining budget projection).
    """
    resume_ok: list[str] = []
    blocked: list[str] = []
    pairs_needing = 0
    for plan in plans:
        pair_needs = False
        for rid, label in ((plan.b_run_id, "B"), (plan.d_run_id, "D")):
            existing = _run_dir_for(rid)
            if existing is None:
                pair_needs = True
                continue
            if darwinian_run_complete(existing):
                resume_ok.append(f"{label} run_{rid} @ {existing}")
            else:
                blocked.append(f"{label} run_{rid} @ {existing} (incomplete)")
                pair_needs = True
        if pair_needs:
            pairs_needing += 1
    return resume_ok, blocked, pairs_needing


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
    eval_subset: int | None = None,
    population_size: int | None = None,
    elite_count: int | None = None,
    max_gen: int | None = None,
) -> list[str]:
    if condition not in {"B", "D"}:
        raise ValueError(f"condition must be B or D, got {condition!r}")
    shape = icml_g3g4_live_shape()
    eval_subset = int(shape["eval_subset"] if eval_subset is None else eval_subset)
    population_size = int(
        shape["population_size"] if population_size is None else population_size
    )
    elite_count = int(shape["elite_count"] if elite_count is None else elite_count)
    max_gen = int(shape["max_gen"] if max_gen is None else max_gen)
    if max_gen > 6:
        raise ValueError("G3 max_gen must be ≤ 6 (Section 21.5 / Tick 296)")
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
    allow_stale_tip: bool = False,
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

    ceiling = _budget_ceiling()
    n_pairs = len(plans)
    resume_ok, blocked_incomplete, pairs_needing = classify_plan_run_occupancy(plans)
    # Tick 377: direct G3 --live must see ledger + unbilled local completes
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
        "G3",
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
    # Tick 375: project only pairs that still need a live launch.
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
        + ("" if budget_ok else " — would exceed ceiling; refuse paid G3"),
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

    # Tick 303: recipe + offline Bvd locks on direct G3 --live (not only pipeline).
    # Prevents bypassing Tick 298–302 guards via `run_g3_pilot.py --live`.
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

    # Tick 305: tip lineage on direct G3 --live (was pipeline-only Tick 269).
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


def resolve_run_dir(run_id: int, cwd: Path) -> Path | None:
    found = _run_dir_for(run_id)
    if found is not None:
        return found
    candidate = cwd / "runs" / f"run_{run_id}"
    return candidate if candidate.exists() else None


def g3_full_pairs_for_metrics(
    b_dirs: list[Path],
    d_dirs: list[Path],
    plans: list[PilotPlan],
) -> bool:
    """Tick 411: True only when every planned B/D pair is present.

    Equal ``len(B)==len(D)`` is not enough — a mid-G3 abort (sia exit,
    never-steer, crash) can leave 1 of 2 planned pairs with equal counts and
    must not write a partial ``comparison`` that pipeline
    ``g3_pilot_promising`` would treat as a full pilot → ~$14 G4 burn.
    Mirrors Tick 410 ``g4_full_pairs_for_paper``.
    """
    n = len(plans)
    return bool(n) and len(b_dirs) == n and len(d_dirs) == n


def decide_g3_live_metrics_action(
    *,
    b_dirs: list[Path],
    d_dirs: list[Path],
    plans: list[PilotPlan],
    run_notes: list[str],
) -> str:
    """Tick 409–411: decide live-path G3 metrics fate.

    Returns one of:
      - ``abort_never_steer`` — Tick 409 mid-G3 never-steer abort notes present
      - ``score`` — all planned pairs complete (safe to ``score_pilot``)
      - ``incomplete`` — partial / unequal pairs (skip compare / G4 advance)
    """
    if any("Tick 409:" in n for n in run_notes):
        return "abort_never_steer"
    if g3_full_pairs_for_metrics(b_dirs, d_dirs, plans):
        return "score"
    return "incomplete"


def score_pilot(
    b_dirs: list[Path], d_dirs: list[Path]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Score PRIMARY compare + Condition D H5/H2 for a live G3 pilot.

    Tick 368: also score live H2 (preferred-allele share) so G3→G4 operators
    see MECHANISM before spending on 5-seed G4 — previously only H5 + gens/cost
    appeared in gate3 live metrics (G4 Tick 364–367 honesty was G4-only).
    """
    # Import here to avoid a hard import cycle at module load (G4 imports G3 helpers).
    from run_g4_multiseed import score_live_h2

    comparison = compare_b_vs_d(b_dirs, d_dirs)
    h5: dict[str, Any] = {}
    for d_dir in d_dirs:
        try:
            h5[d_dir.name] = compute_h5(d_dir)
        except Exception as exc:  # pragma: no cover
            h5[d_dir.name] = {"error": str(exc)}
    h2 = score_live_h2(d_dirs)
    return comparison, h5, h2


_AGENDA_MARKER = "Contradiction-Aware Research Agenda"
_FEEDBACK_PROMPT_NAME = "feedback_agent_prompt.txt"
_STEERING_MIN_GEN = 3


def _iter_gen_agent_dirs(run_dir: Path, gen: int) -> list[Path]:
    gen_dir = run_dir / f"gen_{gen}"
    if not gen_dir.is_dir():
        return []
    return sorted(
        p for p in gen_dir.iterdir() if p.is_dir() and p.name.startswith("agent_")
    )


def validate_g3_d_steering(
    d_dirs: list[Path],
    *,
    min_gen: int = _STEERING_MIN_GEN,
) -> list[CheckResult]:
    """Tick 407: prove Condition D delay-all *lifted* by gen≥3 (positive control).

    Tick 406 G2 post-checks only prove fair gen1→gen2 skip (no agenda / no
    technique_seeds on gen2). A regression that never applies steering still
    PASSes those checks and can burn ~$19 on G3/G4 with Condition D ≈ B.
    G3 runs ``max_gen≥3``, so gen3 feedback prompts must carry the
    Contradiction-Aware agenda once ``apply_cabs_feedback`` is True.
    """
    if not d_dirs:
        return [
            CheckResult(
                "steering_applied_gen3",
                False,
                "no Condition D run dirs — cannot prove delay-all lifted",
            )
        ]

    checks: list[CheckResult] = []
    for d_dir in d_dirs:
        agents = _iter_gen_agent_dirs(d_dir, min_gen)
        name = f"steering_applied_{d_dir.name}"
        if not agents:
            checks.append(
                CheckResult(
                    name,
                    False,
                    f"no gen_{min_gen}/agent_* — cannot prove delay-all lifted "
                    "(refuse G4 burn on never-steer Condition D)",
                )
            )
            continue

        found_agenda: list[str] = []
        missing_fb: list[str] = []
        for agent_dir in agents:
            fb_path = agent_dir / _FEEDBACK_PROMPT_NAME
            if not fb_path.is_file():
                missing_fb.append(agent_dir.name)
                continue
            try:
                text = fb_path.read_text(encoding="utf-8")
            except OSError:
                missing_fb.append(agent_dir.name)
                continue
            if _AGENDA_MARKER in text:
                found_agenda.append(agent_dir.name)

        if found_agenda:
            checks.append(
                CheckResult(
                    name,
                    True,
                    f"gen{min_gen} n={len(agents)} agenda in {found_agenda} "
                    "(delay-all lifted)",
                )
            )
        else:
            detail = (
                f"gen{min_gen} feedback lacks {_AGENDA_MARKER!r} — "
                "Condition D never steered after delay-all; refuse G4 burn"
            )
            if missing_fb:
                detail += f"; missing prompts: {missing_fb}"
            checks.append(CheckResult(name, False, detail))

    all_ok = all(c.ok for c in checks)
    checks.append(
        CheckResult(
            "steering_applied_gen3",
            all_ok,
            (
                f"Condition D n={len(d_dirs)} gen≥{min_gen} steering evidenced"
                if all_ok
                else "one or more Condition D runs lack gen≥3 CABS agenda"
            ),
        )
    )
    return checks


def g3_d_steering_ok(d_dirs: list[Path]) -> tuple[bool, list[CheckResult]]:
    """Convenience wrapper: True iff every Condition D run shows gen≥3 steering."""
    checks = validate_g3_d_steering(d_dirs)
    return all(c.ok for c in checks), checks


def _load_gate3_sidecar_raw(report_md: Path) -> dict[str, Any]:
    """Full gate3 JSON (mode/executed + compare) for Tick 382 ledger-skip trust."""
    sidecar = report_md.with_suffix(".json")
    if not sidecar.is_file():
        return {}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _live_metrics_from_gate3_sidecar(
    data: dict,
) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any], str]:
    """Tick 382/385: extract trustable live G3 metrics from gate3 sidecar.

    Accepts ``mode=="live"`` + ``executed`` + nonempty ``comparison``, or Tick
    385 ``prior_live_metrics`` preserved across preflight rewrites.
    """
    mode = str(data.get("mode") or "")
    executed = bool(data.get("executed"))
    comparison = data.get("comparison")
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
            "live",
        )
    prior = data.get("prior_live_metrics")
    if isinstance(prior, dict):
        prior_cmp = prior.get("comparison")
        if isinstance(prior_cmp, dict) and prior_cmp:
            return (
                prior_cmp,
                prior.get("h5_by_d_run") or {},
                prior.get("h2_by_d_run") or {},
                "prior_live_metrics",
            )
    return None, {}, {}, ""


def refresh_g3_metrics_on_ledger_skip(
    report: G3PreflightReport,
    *,
    gate3_report_md: Path,
) -> tuple[bool, str]:
    """Tick 382: rebuild / trust G3 pilot metrics after direct ledger-skip.

    Tick 380 early-returned on ``ledger_skip`` and wrote ``executed=False`` with
    ``comparison=null``, which could clobber a live-executed gate3 sidecar that
    pipeline Tick 373 needs for G4 advance. Prefer local complete B/D dirs →
    ``score_pilot``. Else trust a live-executed sidecar with non-null comparison
    (or Tick 385 ``prior_live_metrics`` preserved across preflight; never invent
    metrics from a bare preflight sidecar).
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
        comparison, h5, h2 = score_pilot(b_dirs, d_dirs)
        report.comparison = comparison
        report.h5_by_d_run = h5 or {}
        report.h2_by_d_run = h2 or {}
        # Tick 407: local re-score must also prove delay-all lifted on D.
        steering_ok, steering_checks = g3_d_steering_ok(d_dirs)
        for c in steering_checks:
            report.checks.append(c)
        n_pairs = comparison.get("n_pairs") if isinstance(comparison, dict) else None
        if not steering_ok:
            note = (
                "Tick 407: re-scored G3 from local B/D after ledger-skip but "
                f"Condition D gen≥3 steering FAILED (n_pairs={n_pairs}) — "
                "refuse G4 burn on never-steer D"
            )
            report.notes.append(note)
            return False, note
        note = (
            "Tick 382/407: re-scored G3 from local B/D after ledger-skip "
            f"(n_pairs={n_pairs}; gen≥3 steering ok)"
        )
        report.notes.append(note)
        return True, note

    data = _load_gate3_sidecar_raw(gate3_report_md)
    comparison, h5, h2, source = _live_metrics_from_gate3_sidecar(data)
    if comparison is not None:
        report.comparison = comparison
        report.h5_by_d_run = h5
        report.h2_by_d_run = h2
        # Tick 407: when trusting sidecar without local dirs, require prior
        # live payload already recorded steering_applied_gen3=True (if present).
        prior_steering = None
        if source == "prior_live_metrics":
            prior = data.get("prior_live_metrics") or {}
            prior_steering = prior.get("steering_applied_gen3")
        else:
            prior_steering = data.get("steering_applied_gen3")
        if prior_steering is False:
            note = (
                "Tick 407: trusted gate3 sidecar but steering_applied_gen3=false "
                "— refuse G4 burn on never-steer Condition D"
            )
            report.notes.append(note)
            report.checks.append(
                CheckResult("steering_applied_gen3", False, note)
            )
            return False, note
        # Tick 411: refuse partial-pilot sidecar vs planned pairs.
        planned_n = len(b_ids)
        try:
            scored_n = int(comparison.get("n_pairs") or 0)
        except (TypeError, ValueError):
            scored_n = 0
        if planned_n and scored_n < planned_n:
            note = (
                "Tick 411: trusted gate3 sidecar but n_pairs="
                f"{scored_n} < planned={planned_n} — refuse G4 burn on "
                "partial G3 pilot"
            )
            report.notes.append(note)
            report.checks.append(
                CheckResult("g3_full_pairs", False, note)
            )
            report.comparison = None
            report.h5_by_d_run = {}
            report.h2_by_d_run = {}
            return False, note
        if source == "prior_live_metrics":
            note = (
                "Tick 385: trusted gate3 prior_live_metrics after ledger-skip "
                "(no/partial local G3 dirs)"
            )
        else:
            note = (
                "Tick 382: trusted live-executed gate3 sidecar "
                f"(no/partial local G3 dirs; mode={str(data.get('mode') or '')})"
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
    note = (
        "Tick 382: ledger-skip but no local G3 artifacts and no live-executed "
        f"gate3 comparison (mode={mode or 'missing'!r}, executed={executed}) — "
        "metrics not updated"
    )
    report.notes.append(note)
    return False, note


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
        # Tick 368: surface Tick 360 mean_final_gap + Tick 366/367 H2 preferred
        # aggregate (not gens/cost/H5 only) so G3 pilot honesty matches G4.
        mean_gap = cmp_.get("mean_final_gap")
        mean_gap_s = (
            f"{float(mean_gap):.4f}"
            if isinstance(mean_gap, (int, float))
            else "—"
        )
        lines.extend(
            [
                "## Live pilot metrics",
                "",
                f"- Pairs scored: **{cmp_.get('n_pairs', 0)}**",
                f"- D gens30 wins: **{cmp_.get('d_wins_gens30', 0)}** / B: **{cmp_.get('b_wins_gens30', 0)}**",
                f"- D cost30 wins: **{cmp_.get('d_wins_cost30', 0)}** / B: **{cmp_.get('b_wins_cost30', 0)}**",
                f"- D final wins (>1pp): **{cmp_.get('d_wins_final', 0)}** / B: **{cmp_.get('b_wins_final', 0)}**",
                f"- Mean final gap (D−B): **{mean_gap_s}** "
                f"(primary_final_pass={cmp_.get('primary_final_pass')})",
                f"- H2 preferred ≥0.5: **{cmp_.get('d_wins_h2', '—')}/"
                f"{cmp_.get('n_pairs', 0)}** "
                f"(h2_preferred_pass={cmp_.get('h2_preferred_pass')})",
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
                    fld = h2.get("field") or "auto"
                    lines.append(
                        f"- `{name}`: field=`{fld}` "
                        f"preferred=`{h2.get('preferred_value')}` "
                        f"preferred_share=`{h2.get('preferred_share')}` "
                        f"in_bias_share=`{h2.get('in_bias_share')}` "
                        f"counts=`{h2.get('counts')}`"
                    )
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
    py = icml_python_cli()
    lines.extend(
        [
            "## Next",
            "",
            "1. Ensure live G2 smoke passed (`scripts/run_g2_smoke.py --live ...`).",
            f"2. Add `{secrets_line}` (see `docs/ICML_HUMAN_UNBLOCK.md`).",
            "3. Budget-check, then:",
            f"   `{py} scripts/run_g3_pilot.py --live --seeds 1 --b-run-ids 1201 --d-run-ids 1301 --fetch-diamond`",
            "4. If pilot looks promising, G4 5-seed under remaining budget (never parallel full GPQA).",
            "5. Do **not** set `ICML_READY` STATUS: READY from offline / preflight alone.",
            "",
        ]
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    sidecar = out.with_suffix(".json")
    # Tick 385: preflight rewrites must not wipe live comparison/H2/H5.
    # Preserve under prior_live_metrics so pipeline G3→G4 / ledger-skip trust
    # still works after cron --preflight-only (Tick 384 prior_live_post parity).
    existing = _load_gate3_sidecar_raw(out)
    prior_live_metrics = None
    if (
        executed
        and report.mode == "live"
        and isinstance(report.comparison, dict)
        and report.comparison
    ):
        prior_live_metrics = {
            "comparison": report.comparison,
            "h5_by_d_run": report.h5_by_d_run or {},
            "h2_by_d_run": report.h2_by_d_run or {},
            "executed": True,
            # Tick 407: preserve steering positive-control across preflight wipe.
            "steering_applied_gen3": any(
                c.name == "steering_applied_gen3" and c.ok for c in report.checks
            ),
        }
    else:
        preserved_cmp, preserved_h5, preserved_h2, _src = (
            _live_metrics_from_gate3_sidecar(existing)
        )
        if preserved_cmp is not None:
            prior_steering = None
            if isinstance(existing.get("prior_live_metrics"), dict):
                prior_steering = existing["prior_live_metrics"].get(
                    "steering_applied_gen3"
                )
            if prior_steering is None:
                prior_steering = existing.get("steering_applied_gen3")
            if prior_steering is None:
                # Infer from checks on this report / existing sidecar.
                for c in report.checks:
                    if c.name == "steering_applied_gen3":
                        prior_steering = c.ok
                        break
            prior_live_metrics = {
                "comparison": preserved_cmp,
                "h5_by_d_run": preserved_h5,
                "h2_by_d_run": preserved_h2,
                "executed": True,
            }
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
        "plans": [asdict(p) for p in report.plans],
        "blockers": report.blockers,
        "checks": [asdict(c) for c in report.checks],
        "commands": report.commands,
        "comparison": report.comparison,
        "h5_by_d_run": report.h5_by_d_run,
        "h2_by_d_run": report.h2_by_d_run,
        "notes": report.notes,
        "executed": executed,
    }
    if steering_flag is not None:
        payload["steering_applied_gen3"] = steering_flag
    if prior_live_metrics is not None:
        payload["prior_live_metrics"] = prior_live_metrics
    sidecar.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    # Tick 389: mirror prior_live into committed evidence (cross-VM) + stash.
    if prior_live_metrics is not None:
        persist_prior_live_stash_from_working_tree(REPO_ROOT)


def run_sequential_live(
    report: G3PreflightReport,
    *,
    cwd: Path,
    eval_subset: int,
    population_size: int,
    elite_count: int,
    max_gen: int,
    abort_on_d_never_steer: bool = False,
) -> tuple[list[Path], list[Path], list[str]]:
    """Execute B then D for each seed. Never launches two GPQA jobs at once.

    Tick 375: if a planned run ID already has a complete Darwinian
    ``results.json``, resume-skip it (never overwrite). Incomplete existing
    dirs abort (preflight should have blocked them).

    Tick 409: when ``abort_on_d_never_steer`` and ``max_gen≥3``, after each
    Condition D completes (or resume-skips), prove gen≥3 CABS agenda via
    ``g3_d_steering_ok``. On never-steer, abort remaining pairs so G4 cannot
    burn ~$12 more after the first failed D (Tick 408 only refused READY
    *after* all five pairs finished).
    """
    env = os.environ.copy()
    env.setdefault("SIA_CABS_ROOT", str(REPO_ROOT))
    b_dirs: list[Path] = []
    d_dirs: list[Path] = []
    notes: list[str] = []

    def _maybe_abort_never_steer(run_id: int, d_dir: Path) -> bool:
        """Return True if caller should abort remaining pairs."""
        if not abort_on_d_never_steer or max_gen < _STEERING_MIN_GEN:
            return False
        ok, steers = g3_d_steering_ok([d_dir])
        if ok:
            return False
        detail = next((c.detail for c in steers if not c.ok), "never-steer")
        notes.append(
            f"Tick 409: Condition D run_{run_id} never steered after delay-all "
            f"({detail}) — abort remaining pairs to save budget"
        )
        return True

    for plan in report.plans:
        for condition, run_id, bucket in (
            ("B", plan.b_run_id, b_dirs),
            ("D", plan.d_run_id, d_dirs),
        ):
            existing = _run_dir_for(run_id)
            if darwinian_run_complete(existing):
                assert existing is not None
                bucket.append(existing)
                notes.append(
                    f"{condition} run_{run_id} resume-skip (already complete) → {existing}"
                )
                if condition == "D" and _maybe_abort_never_steer(run_id, existing):
                    return b_dirs, d_dirs, notes
                continue
            if existing is not None:
                notes.append(
                    f"{condition} run_{run_id} exists but incomplete at {existing}; "
                    "aborting (never overwrite)"
                )
                return b_dirs, d_dirs, notes
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
            if condition == "D" and _maybe_abort_never_steer(run_id, run_dir):
                return b_dirs, d_dirs, notes
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
    p.add_argument("--eval-subset", type=int, default=DEFAULT_EVAL_SUBSET)
    p.add_argument("--population-size", type=int, default=DEFAULT_POPULATION_SIZE)
    p.add_argument("--elite-count", type=int, default=DEFAULT_ELITE_COUNT)
    p.add_argument("--max-gen", type=int, default=DEFAULT_MAX_GEN)
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
    p.add_argument("--diamond-n", type=int, default=DEFAULT_DIAMOND_N)
    p.add_argument(
        "--allow-stale-tip",
        action="store_true",
        help="Allow --live even when local Tick lags remote tip (dangerous; Tick 305)",
    )
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

    if args.max_gen > 6:
        print("G3 refuses max_gen > 6 (Section 21.5 / Tick 296)", file=sys.stderr)
        return 2

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
                    mode=selected,
                    plans=plans,
                    require_hf_for_diamond=require_hf,
                    allow_stale_tip=allow_stale,
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
                    mode=selected,
                    plans=plans,
                    require_hf_for_diamond=require_hf,
                    allow_stale_tip=allow_stale,
                )
                report.notes.extend(fetch_notes)
                write_gate3_report(report, args.report)
                return 3

    report = run_preflight(
        mode=selected,
        plans=plans,
        require_hf_for_diamond=require_hf,
        allow_stale_tip=allow_stale,
    )
    report.notes.extend(fetch_notes)

    if selected == "preflight":
        write_gate3_report(report, args.report)
        print(f"G3 preflight written → {args.report}")
        print(f"ready_for_live={report.ready_for_live}")
        if report.ledger_skip:
            print("ledger_skip=True (Tick 380 — --live would no-op)")
        for b in report.blockers:
            print(f"  BLOCK: {b}")
        return 0

    # Tick 380: ledger-complete G3 → exit 0 without sia (even if secrets absent).
    # Tick 382: still re-score / trust pilot metrics (pipeline Tick 373 parity).
    # Tick 407: return 4 when metrics/steering cannot be proven (G2 Tick 384 parity).
    if report.ledger_skip:
        report.notes.append(
            "Tick 380: skipped paid G3 — ledger stages_complete already lists G3 "
            "for planned run IDs"
        )
        metrics_ok, metrics_note = refresh_g3_metrics_on_ledger_skip(
            report, gate3_report_md=args.report
        )
        report.notes.append(metrics_note)
        write_gate3_report(
            report, args.report, executed=bool(report.comparison)
        )
        print(f"G3 live skipped (ledger resume) → {args.report}")
        print(metrics_note)
        print(f"g3_metrics_ok={metrics_ok} comparison={report.comparison is not None}")
        if not metrics_ok:
            print(
                "G3 ledger-skip refused G4 advance — missing metrics / "
                "gen≥3 Condition D steering",
                file=sys.stderr,
            )
            return 4
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
        # Tick 409: multi-seed G3 also aborts after first never-steer D.
        abort_on_d_never_steer=True,
    )
    report.notes.extend(run_notes)

    steering_ok = False
    # Tick 409–411: never-steer abort OR partial pairs → skip score_pilot.
    metrics_action = decide_g3_live_metrics_action(
        b_dirs=b_dirs,
        d_dirs=d_dirs,
        plans=report.plans,
        run_notes=run_notes,
    )
    if metrics_action == "abort_never_steer":
        # Record steering checks for completed D dirs; do NOT promote a
        # partial pilot comparison that could auto-advance G4.
        if d_dirs:
            _ok, steering_checks = g3_d_steering_ok(d_dirs)
            for c in steering_checks:
                report.checks.append(c)
        report.notes.append(
            "Tick 409: aborted remaining G3 pairs on never-steer — skipped "
            "compare_b_vs_d (refuse partial pilot → G4)"
        )
        steering_ok = False
    elif metrics_action == "score":
        comparison, h5, h2 = score_pilot(b_dirs, d_dirs)
        report.comparison = comparison
        report.h5_by_d_run = h5
        report.h2_by_d_run = h2
        # Tick 407: positive control — delay-all must have lifted by gen≥3.
        steering_ok, steering_checks = g3_d_steering_ok(d_dirs)
        for c in steering_checks:
            report.checks.append(c)
        if not steering_ok:
            report.notes.append(
                "Tick 407: Condition D gen≥3 steering FAILED — refuse G4 burn"
            )
    else:
        report.notes.append(
            "Tick 411: incomplete / partial B/D pairs "
            f"(B={len(b_dirs)} D={len(d_dirs)} plans={len(report.plans)}) — "
            "skipped compare_b_vs_d (refuse partial pilot → G4)"
        )
        report.checks.append(
            CheckResult(
                "g3_full_pairs",
                False,
                f"B={len(b_dirs)} D={len(d_dirs)} plans={len(report.plans)}",
            )
        )

    g3_ok = bool(report.comparison) and steering_ok

    # Tick 379: stamp ledger G3 after direct live when every planned run is
    # complete (partials bill via persist but stay unstamped).
    # Tick 407: only stamp when gen≥3 steering also passes (mirror G2 post-ok).
    planned_ids = [p.b_run_id for p in report.plans] + [
        p.d_run_id for p in report.plans
    ]
    if g3_ok:
        _, persist_detail = persist_direct_gate_stage_spend(
            "G3",
            planned_ids,
            pair_estimate_usd=float(DEFAULT_PAIR_ESTIMATE_USD),
            resolve_run_dir=_run_dir_for,
            repo_root=REPO_ROOT,
        )
        report.notes.append(persist_detail)
    else:
        report.notes.append(
            "Tick 407: skipped ledger G3 stamp — comparison/steering incomplete"
        )

    write_gate3_report(report, args.report, executed=bool(report.comparison))
    print(f"G3 report → {args.report}")
    if not g3_ok:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
