#!/usr/bin/env python3
"""ICML Gate G2 preflight + Condition D smoke runner.

Largest remaining ICML gap is live GPQA G2. This script makes the next tick
turnkey and hard-stops unsafe paid runs:

  - missing NEBIUS_API_KEY for --live (ANTHROPIC optional under Nebius meta; Tick 289/292)
  - synthetic smoke GPQA answers for --live (refuse paid eval on fake labels)
  - existing run directory (never overwrite)
  - optional budget ceiling via SIA_BUDGET_SPENT_USD / SIA_BUDGET_CEILING_USD
  - Tick 378: direct ``--live`` hydrates ``SIA_BUDGET_SPENT_USD`` from the
    committed ledger + unbilled local complete runs before the budget check
    (closes G2 bypass left after Tick 377 G3/G4 hydrate)
  - Tick 379: after successful live + post-run gates, persist ledger stage
    ``G2`` (hydrate alone never stamped ``stages_complete``)
  - Tick 380: ``--live`` skips paid re-run when committed ledger already marks
    ``G2`` complete for the planned run_id (pipeline Tick 285; stamp alone
    was not enough — direct runners still treated missing ``runs/`` as free)
  - Tick 383: ledger-skip still re-validates / trusts G2 post-checks (local
    ``validate_g2_artifacts`` or live-executed gate2 sidecar) so Tick 380 cannot
    clobber nonzero-fitness evidence needed for honest G2→G3 advance
  - Tick 384: ledger-skip returns exit 4 when post-checks cannot be proven;
    preflight preserves ``prior_live_post`` so cron preflight cannot wipe
    live evidence the pipeline needs for G2→G3
  - stale tip lineage for --live (Tick 306; same tip_ok_for_live as pipeline/G3/G4)
  - Tick 371: post-run best fitness must be > SIA_G2_MIN_BEST_FITNESS (default 0)
    so 0%/unscored smoke cannot auto-advance the live pipeline into paid G3/G4
  - Tick 406: post-run delay-all fidelity — gen2 feedback prompts must lack
    Contradiction-Aware agenda and gen2 DNA must not carry committee
    technique_seeds (fair gen1→gen2 under Tick 403–405). Prevents G3/G4 burn
    if the delay-all gate regresses.
  - Tick 509: dry-run ``--max-gen ≥3`` also requires Tick 407 gen≥3
    Contradiction-Aware agenda (positive control that delay-all *lifted*).
    Tick 406–508 only proved the fair gen2 *skip* — a never-steer regression
    still PASSed G2 dry-run and could burn ~$19 on G3/G4 with D≈B. Live G2
    stays max_gen=2 (budget smoke); use dry-run max_gen≥3 for the lift proof.
  - Tick 510: durable ``docs/gate2_steering_lift_proof.json`` + pipeline hard
    gate. Tick 509 made the lift proof runnable, but cron ``--preflight-only``
    rewrites ``gate2_report`` and live G2 stays max_gen=2 — so a never-steer
    regression could still reach paid G3 without a surviving gen≥3 proof.
    ``ensure_g2_steering_lift_proof`` auto-runs dry-run max_gen≥3 when missing;
    the live pipeline refuses spend without a PASS sidecar.
  - Tick 513: cold-boot re-verify dry-run ``--max-gen ≥3`` (``run_1957``) when
    prior lift run dirs are gone; durable proof tick stamps current
    ``ICML_PROGRESS`` tick (no longer frozen at 510).

Modes:
  --preflight-only   check keys/data/run_id; write docs/gate2_report.md; no sia run
  --dry-run          harness Condition D (smoke fixture OK; no API)
  --live             paid G2 smoke (keys + non-smoke GPQA required)

Examples (Linux/cloud: python3; Windows venv: python):
  python3 scripts/run_g2_smoke.py --preflight-only --run-id 1850
  python3 scripts/run_g2_smoke.py --dry-run --run-id 1850
  python3 scripts/run_g2_smoke.py --dry-run --max-gen 3 --run-id 1955
  python3 scripts/run_g2_smoke.py --live --run-id 1300 --seed 1
  python3 scripts/run_g2_smoke.py --live --run-id 1300 --fetch-diamond
  python3 scripts/run_g2_smoke.py --preflight-only --fetch-diamond --diamond-csv "$TMPDIR/gpqa_diamond.csv"
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
from prepare_gpqa_diamond import (  # noqa: E402
    materialize_from_csv,
    materialize_from_hf,
)
from icml_env_checks import (  # noqa: E402
    autowire_diamond_csv,
    collect_icml_secrets_status,
    commit_durable_ledgers_after_live,
    darwinian_run_complete,
    default_g2_estimate_usd,
    diamond_csv_autowire_note,
    ensure_deps_before_diamond_fetch,
    ensure_icml_runtime_deps,
    hydrate_direct_gate_budget_spent,
    persist_direct_gate_stage_spend,
    persist_prior_live_stash_from_working_tree,
    direct_gate_ledger_skip,
    icml_fetch_diamond_needs_hf,
    icml_human_required_secrets_phrase,
    icml_meta_profile_cli_flags,
    icml_meta_requires_anthropic,
    icml_ondisk_nonsynthetic_gpqa,
    icml_preflight_diamond_ready,
    icml_should_keep_ondisk_diamond,
    icml_python_cli,
    icml_target_profile_cli_flags,
    extract_numbered_next_steps,
    gate2_next_step_bodies,
    _gate_next_markdown_from_bodies,
    portable_argv_for_durable,
    probe_icml_meta_profile,
    probe_icml_target_profile_nebius,
    probe_per_run_venv_capable,
    repo_relative_path,
    sanitize_repo_paths_in_text,
    write_icml_tip_status,
)

DEFAULT_BUDGET_CEILING = 20.0
DEFAULT_LIVE_RUN_ID = 1300
DEFAULT_DRY_RUN_ID = 1850
# Tick 510: durable gen≥3 delay-all *lift* proof (survives gate2 preflight rewrite).
DEFAULT_STEERING_LIFT_RUN_ID = 1956
STEERING_LIFT_PROOF_NAME = "gate2_steering_lift_proof.json"
STEERING_LIFT_REQUIRED_CHECKS = (
    "delay_all_feedback_skip",
    "delay_all_technique_seeds_skip",
    "steering_applied_gen3",
    "nonzero_fitness",
)


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
    # Tick 380: ledger marks G2 done for this run_id → skip paid --live re-run.
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


def steering_lift_proof_path(repo_root: Path | None = None) -> Path:
    """Tick 510: durable sidecar path (not wiped by gate2 preflight)."""
    root = repo_root if repo_root is not None else REPO_ROOT
    return root / "docs" / STEERING_LIFT_PROOF_NAME


def _repo_relative_detail(detail: str | Path, *, repo_root: Path | None = None) -> str:
    """Tick 523: store portable paths in durable G2 / lift-proof details.

    Absolute ``/workspace/...`` details broke cross-VM portability of
    ``docs/gate2_report.*`` and ``docs/gate2_steering_lift_proof.json`` the same
    way bare ``str(path)`` leaked into Figs before Tick 519–522. Non-path
    details (e.g. ``present``, fitness strings) round-trip unchanged.

    Prefer ``repo_root`` when the path lives under it (unit tests / alt
    checkouts); otherwise fall back to ``REPO_ROOT`` so a durable proof
    written under a tmp ``docs/`` root still strips absolute in-repo paths.
    """
    text = str(detail or "")
    if not text:
        return text
    # Only rewrite absolute path-looking details (or Path objects).
    p = Path(detail) if isinstance(detail, Path) else Path(text)
    if not (isinstance(detail, Path) or p.is_absolute() or text.startswith(("/", "\\"))):
        return text
    resolved = p.resolve()
    for root in (repo_root, REPO_ROOT):
        if root is None:
            continue
        try:
            return str(resolved.relative_to(Path(root).resolve()))
        except ValueError:
            continue
    return str(p)


def _post_as_check_dicts(post, *, repo_root: Path | None = None) -> list[dict]:
    """Normalize post checks to ``[{name, ok, detail}, ...]``.

    Tick 512: duck-type foreign ``CheckResult`` dataclasses (e.g.
    ``run_g3_pilot.CheckResult`` from ``validate_g3_d_steering``). A strict
    ``isinstance(..., run_g2_smoke.CheckResult)`` dropped gen≥3 lift rows, so
    ``post_checks_satisfy_steering_lift`` returned False after a PASS dry-run
    and ``write_gate2_report`` never refreshed ``gate2_steering_lift_proof.json``.

    Tick 523: normalize absolute in-repo path details to repo-relative form so
    durable JSON does not embed ``/workspace/...``.
    """
    if post is None:
        return []
    out: list[dict] = []
    root = repo_root if repo_root is not None else REPO_ROOT

    def _one(item) -> dict | None:
        if isinstance(item, dict) and item.get("name"):
            return {
                "name": str(item["name"]),
                "ok": bool(item.get("ok")),
                "detail": _repo_relative_detail(
                    str(item.get("detail") or ""), repo_root=root
                ),
            }
        # Local + foreign CheckResult dataclasses / duck-typed rows.
        name = getattr(item, "name", None)
        if name is None:
            return None
        if isinstance(item, CheckResult):
            row = asdict(item)
            row["detail"] = _repo_relative_detail(
                str(row.get("detail") or ""), repo_root=root
            )
            return row
        return {
            "name": str(name),
            "ok": bool(getattr(item, "ok", False)),
            "detail": _repo_relative_detail(
                str(getattr(item, "detail", "") or ""), repo_root=root
            ),
        }

    if isinstance(post, dict):
        # Rare: name → {ok, detail} map
        for name, val in post.items():
            if isinstance(val, dict):
                out.append(
                    {
                        "name": str(name),
                        "ok": bool(val.get("ok")),
                        "detail": _repo_relative_detail(
                            str(val.get("detail") or ""), repo_root=root
                        ),
                    }
                )
            else:
                converted = _one(val)
                if converted is not None:
                    # Preserve map key as name when value lacks one.
                    converted.setdefault("name", str(name))
                    converted["name"] = str(name)
                    out.append(converted)
        return out
    for item in post:
        converted = _one(item)
        if converted is not None:
            out.append(converted)
    return out


def post_checks_satisfy_steering_lift(post) -> tuple[bool, str]:
    """True when post-run checks prove delay-all skip + gen≥3 lift + fitness."""
    checks = {c["name"]: c for c in _post_as_check_dicts(post)}
    missing = [n for n in STEERING_LIFT_REQUIRED_CHECKS if n not in checks]
    if missing:
        # Accept run-scoped steering_applied_run_* as alias for gen3 aggregate.
        if "steering_applied_gen3" in missing:
            run_scoped = [
                n
                for n, c in checks.items()
                if n.startswith("steering_applied_run_") and c.get("ok")
            ]
            if run_scoped:
                missing = [n for n in missing if n != "steering_applied_gen3"]
                checks["steering_applied_gen3"] = checks[run_scoped[0]]
        if missing:
            return False, f"missing post checks: {missing}"
    failed = [
        n for n in STEERING_LIFT_REQUIRED_CHECKS if not checks.get(n, {}).get("ok")
    ]
    if failed:
        details = "; ".join(
            f"{n}: {checks[n].get('detail') or 'FAIL'}" for n in failed
        )
        return False, f"steering-lift post FAIL ({details})"
    return True, "delay-all skip + gen≥3 lift + nonzero fitness"


def _resolve_steering_lift_proof_tick(
    repo_root: Path,
    tick: int | None = None,
) -> int:
    """Tick 513: stamp the current ICML progress tick (not a frozen 510).

    Hard-coding ``tick: 510`` left durable proof looking stale after Tick 512+
    refreshes (``run_1956`` / ``run_1957`` still said tick 510), which misled
    operators reading ``gate2_steering_lift_proof.json`` on cold boots.
    """
    if tick is not None:
        return int(tick)
    progress = repo_root / "docs" / "ICML_PROGRESS.md"
    if progress.is_file():
        try:
            from icml_env_checks import parse_latest_icml_tick

            parsed = parse_latest_icml_tick(progress.read_text(encoding="utf-8"))
            if parsed is not None:
                return int(parsed)
        except Exception:
            pass
    return 510  # first tick that introduced the durable sidecar


def local_steering_lift_run_present(
    run_id: int | None,
    repo_root: Path | None = None,
) -> bool:
    """True when ``runs/run_<id>`` (or ``SIA/runs/…``) still exists on this VM.

    Tick 514: cold boots routinely lose gitignored ``runs/``. Durable proof
    must remain valid without a local dir — do **not** treat a vanished path
    as a reason to re-burn a dry-run ``--max-gen ≥3``.
    """
    if run_id is None:
        return False
    root = repo_root if repo_root is not None else REPO_ROOT
    # Prefer REPO_ROOT-scoped lookup when tests monkeypatch REPO_ROOT.
    for base in (root / "runs", root / "SIA" / "runs"):
        if (base / f"run_{int(run_id)}").is_dir():
            return True
    # Fall back to process-global helpers (live repo layout).
    if root == REPO_ROOT:
        return _run_dir_for(int(run_id)) is not None
    return False


def write_steering_lift_proof(
    *,
    run_id: int,
    post,
    timestamp: str | None = None,
    source: str = "dry-run",
    repo_root: Path | None = None,
    tick: int | None = None,
) -> Path:
    """Persist Tick 509/510 steering-lift PASS so preflight cannot wipe it."""
    root = repo_root if repo_root is not None else REPO_ROOT
    ok, detail = post_checks_satisfy_steering_lift(post)
    if not ok:
        raise ValueError(f"refuse to write steering-lift proof: {detail}")
    path = steering_lift_proof_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    rid = int(run_id)
    local_present = local_steering_lift_run_present(rid, root)
    # Tick 523: persist repo-relative path details (no /workspace/... leaks).
    post_dicts = _post_as_check_dicts(post, repo_root=root)
    payload = {
        "timestamp": timestamp or _utc_now(),
        "tick": _resolve_steering_lift_proof_tick(root, tick),
        "source": source,
        "mode": "dry-run",
        "run_id": rid,
        "max_gen": 3,
        "ok": True,
        "detail": detail,
        "post": post_dicts,
        "required_checks": list(STEERING_LIFT_REQUIRED_CHECKS),
        # Tick 514: honest cold-boot flag — JSON proof is authoritative.
        "local_run_present": local_present,
        "vm_ephemeral_safe": True,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def load_steering_lift_proof(repo_root: Path | None = None) -> dict | None:
    path = steering_lift_proof_path(repo_root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def refresh_steering_lift_proof_local_run_flag(
    repo_root: Path | None = None,
    *,
    tick: int | None = None,
) -> tuple[bool, str]:
    """Tick 514: update ``local_run_present`` without re-running dry-run.

    Cold-boot cron must not invent a new ``run_19xx`` solely because the
    cited gitignored run dir vanished — durable post checks already PASS.
    """
    root = repo_root if repo_root is not None else REPO_ROOT
    data = load_steering_lift_proof(root)
    if not data:
        return False, f"missing {STEERING_LIFT_PROOF_NAME}"
    if not data.get("ok"):
        return False, f"proof sidecar ok=false ({data.get('detail') or 'no detail'})"
    post_ok, post_detail = post_checks_satisfy_steering_lift(data.get("post"))
    if not post_ok:
        return False, f"proof sidecar post invalid: {post_detail}"
    rid = data.get("run_id")
    try:
        rid_i = int(rid) if rid is not None else None
    except (TypeError, ValueError):
        rid_i = None
    local_present = local_steering_lift_run_present(rid_i, root)
    data["local_run_present"] = local_present
    data["vm_ephemeral_safe"] = True
    data["local_run_flag_refreshed_at"] = _utc_now()
    data["tick"] = _resolve_steering_lift_proof_tick(root, tick)
    # Tick 523: rewrite absolute path details on cold-boot refresh (no dry-run).
    data["post"] = _post_as_check_dicts(data.get("post"), repo_root=root)
    # Keep prior detail; annotate when run dir is gone on this VM.
    if not local_present:
        data["detail"] = (
            f"{post_detail} (local run_{rid_i} dir absent — durable JSON authoritative)"
        )
    else:
        data["detail"] = post_detail
    path = steering_lift_proof_path(root)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if local_present:
        return True, f"run_{rid_i} local present; {post_detail}"
    return True, (
        f"run_{rid_i} local absent (VM-ephemeral-safe); durable proof still PASS — "
        f"{post_detail}"
    )


def steering_lift_proof_ok(repo_root: Path | None = None) -> tuple[bool, str]:
    """Tick 510: durable proof sidecar documents a PASS gen≥3 lift dry-run.

    Tick 514: a missing local ``runs/run_<id>`` does **not** invalidate the
    sidecar — gitignored runs vanish on cold boots; post-check payload is
    the evidence.
    """
    data = load_steering_lift_proof(repo_root)
    if not data:
        return False, f"missing {STEERING_LIFT_PROOF_NAME}"
    if not data.get("ok"):
        return False, f"proof sidecar ok=false ({data.get('detail') or 'no detail'})"
    post_ok, post_detail = post_checks_satisfy_steering_lift(data.get("post"))
    if not post_ok:
        return False, f"proof sidecar post invalid: {post_detail}"
    run_id = data.get("run_id")
    try:
        rid_i = int(run_id) if run_id is not None else None
    except (TypeError, ValueError):
        rid_i = None
    local_present = local_steering_lift_run_present(rid_i, repo_root)
    if local_present:
        return True, f"run_{run_id} {post_detail}"
    return True, (
        f"run_{run_id} {post_detail} "
        f"(local dir absent — durable JSON authoritative; Tick 514)"
    )


def maybe_bootstrap_steering_lift_proof_from_gate2(
    repo_root: Path | None = None,
) -> tuple[bool, str]:
    """If gate2_report.json still holds a dry-run lift PASS, durable-ize it."""
    root = repo_root if repo_root is not None else REPO_ROOT
    ok, detail = steering_lift_proof_ok(root)
    if ok:
        return True, detail
    gate2 = root / "docs" / "gate2_report.json"
    if not gate2.is_file():
        return False, "no gate2_report.json to bootstrap"
    try:
        data = json.loads(gate2.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"gate2_report unreadable: {exc}"
    if str(data.get("mode") or "") != "dry-run":
        return False, f"gate2 mode={data.get('mode')!r} (want dry-run lift)"
    post = data.get("post") or []
    post_ok, post_detail = post_checks_satisfy_steering_lift(post)
    if not post_ok:
        return False, f"gate2 dry-run post not lift-PASS: {post_detail}"
    run_id = int(data.get("run_id") or DEFAULT_STEERING_LIFT_RUN_ID)
    write_steering_lift_proof(
        run_id=run_id,
        post=post,
        timestamp=str(data.get("timestamp") or _utc_now()),
        source="bootstrap_gate2_report",
        repo_root=root,
    )
    return True, f"bootstrapped run_{run_id} ({post_detail})"


def next_free_steering_lift_run_id(
    start: int = DEFAULT_STEERING_LIFT_RUN_ID,
    *,
    limit: int = 50,
) -> int:
    """Pick an unused integer run id for a fresh lift dry-run (never overwrite)."""
    for rid in range(int(start), int(start) + int(limit)):
        if _run_dir_for(rid) is None:
            return rid
    raise RuntimeError(
        f"no free steering-lift run_id in [{start}, {start + limit})"
    )


def ensure_g2_steering_lift_proof(
    *,
    repo_root: Path | None = None,
    auto_run: bool = True,
    run_id: int | None = None,
) -> tuple[bool, str]:
    """Tick 510: require Tick 509 dry-run max_gen≥3 PASS before paid G3/G4.

    Order:
      1. Trust durable ``gate2_steering_lift_proof.json`` when post checks PASS
      2. Bootstrap from current ``gate2_report.json`` dry-run lift post (if any)
      3. Re-validate an existing run dir with ``gen_3/`` when present
      4. Optionally auto-run ``--dry-run --max-gen 3`` on a free run_id
    """
    root = repo_root if repo_root is not None else REPO_ROOT
    ok, detail = steering_lift_proof_ok(root)
    if ok:
        # Tick 514: refresh local_run_present without inventing a new dry-run
        # when cold boots wipe gitignored runs/ (JSON remains authoritative).
        flag_ok, flag_detail = refresh_steering_lift_proof_local_run_flag(root)
        if flag_ok:
            return True, f"durable proof: {flag_detail}"
        return True, f"durable proof: {detail}"

    boot_ok, boot_detail = maybe_bootstrap_steering_lift_proof_from_gate2(root)
    if boot_ok:
        return True, f"bootstrapped: {boot_detail}"

    # Re-validate on-disk run with gen_3 (ephemeral VMs often lose runs/).
    candidates: list[int] = []
    if run_id is not None:
        candidates.append(int(run_id))
    for base in (_runs_dir(), _sia_runs_dir()):
        if not base.is_dir():
            continue
        for child in sorted(base.glob("run_*"), reverse=True):
            if not (child / "gen_3").is_dir():
                continue
            try:
                candidates.append(int(child.name.split("_", 1)[1]))
            except (IndexError, ValueError):
                continue
    seen: set[int] = set()
    for rid in candidates:
        if rid in seen:
            continue
        seen.add(rid)
        run_dir = _run_dir_for(rid)
        if run_dir is None:
            continue
        post = [
            CheckResult(
                "run_dir",
                True,
                _repo_relative_detail(run_dir, repo_root=root),
            )
        ]
        post.extend(validate_g2_artifacts(run_dir, require_steering_lift=True))
        post_ok, post_detail = post_checks_satisfy_steering_lift(post)
        if post_ok:
            write_steering_lift_proof(
                run_id=rid,
                post=post,
                source="revalidate_run_dir",
                repo_root=root,
            )
            return True, f"revalidated run_{rid}: {post_detail}"

    if not auto_run:
        return False, (
            "no durable Tick 509 steering-lift proof "
            f"(run `python3 scripts/run_g2_smoke.py --dry-run --max-gen 3 "
            f"--run-id <free>`; last: {detail})"
        )

    try:
        lift_id = (
            int(run_id)
            if run_id is not None and _run_dir_for(int(run_id)) is None
            else next_free_steering_lift_run_id()
        )
    except RuntimeError as exc:
        return False, str(exc)

    rc = main(
        [
            "--dry-run",
            "--max-gen",
            "3",
            "--run-id",
            str(lift_id),
        ]
    )
    if rc != 0:
        return False, f"auto dry-run max_gen=3 run_{lift_id} exited {rc}"
    ok2, detail2 = steering_lift_proof_ok(root)
    if ok2:
        return True, f"auto-ran run_{lift_id}: {detail2}"
    # Dry-run may have written gate2 post but failed write_steering_lift_proof
    # if an older code path — bootstrap once more.
    boot2_ok, boot2_detail = maybe_bootstrap_steering_lift_proof_from_gate2(root)
    if boot2_ok:
        return True, f"auto-ran run_{lift_id} then bootstrap: {boot2_detail}"
    return False, (
        f"auto dry-run run_{lift_id} finished but proof still missing "
        f"({detail2})"
    )


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
    # Tick 289: Nebius pydantic-ai meta (Anthropic optional).
    cmd.extend(icml_meta_profile_cli_flags())
    # Tick 288: Nebius target profile (not default-target / Tinker seed).
    cmd.extend(icml_target_profile_cli_flags())
    return cmd


def run_preflight(
    *,
    mode: str,
    run_id: int,
    ensure_smoke_layout: bool = True,
    require_hf_for_diamond: bool = False,
    allow_stale_tip: bool = False,
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
    # Always record live-readiness signals (even in preflight/dry-run) so
    # ready_for_live is not vacuously true when key checks are skipped.
    report.add(
        "gpqa_not_synthetic",
        (not missing) and (not smoke),
        "real/non-smoke diamond_questions.json present"
        if (not missing and not smoke)
        else "synthetic smoke fixture detected — replace with real GPQA diamond before paid G2",
    )
    if mode != "live":
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
    # Tick 378: direct G2 --live must see ledger + unbilled local completes
    # (pipeline Tick 376 sync already hydrates before calling this runner;
    # Tick 377 wired the same helper into G3/G4 only).
    g2_est = float(default_g2_estimate_usd())
    _, hydrate_detail = hydrate_direct_gate_budget_spent(
        [int(run_id)],
        run_estimate_usd=g2_est,
        resolve_run_dir=_run_dir_for,
        repo_root=REPO_ROOT,
    )
    report.notes.append(hydrate_detail)
    spent = _budget_spent()
    budget_ok = spent < ceiling
    report.add(
        "budget",
        budget_ok,
        f"spent=${spent:.2f} ceiling=${ceiling:.2f}"
        + ("" if budget_ok else " — at/over ceiling; refuse paid G2"),
    )

    existing = _run_dir_for(run_id)
    ledger_skip, ledger_skip_detail = direct_gate_ledger_skip(
        "G2",
        [int(run_id)],
        path=REPO_ROOT / "docs" / "icml_budget_spent.json",
    )
    report.ledger_skip = bool(ledger_skip)
    if ledger_skip:
        report.notes.append(ledger_skip_detail)
        report.add(
            "ledger_stage_complete",
            True,
            ledger_skip_detail,
        )
        # Cross-VM: no local dir but ledger owns this ID — treat as not free
        # for overwrite, yet allow --live to short-circuit as skip (not refuse).
        report.add(
            "run_id_free",
            True,
            f"run_{run_id} ledger-complete (Tick 380 skip; local dir absent OK)",
        )
    else:
        report.add(
            "run_id_free",
            existing is None,
            f"run_{run_id} unused"
            if existing is None
            else f"exists at {existing} — pick unused integer (never overwrite)",
        )

    # SIA per-run venvs: uv OR stdlib venv+ensurepip (import venv alone is vacuous)
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

    # Tick 306: tip lineage on direct G2 --live (was pipeline-only Tick 269;
    # G3/G4 gained the same guard at Tick 305 — close the remaining bypass).
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
    dry_needed = ("gpqa_layout", "run_id_free", "per_run_venv", "runtime_deps")
    report.ready_for_dry_run = all(by_name.get(n, False) for n in dry_needed) and not missing
    live_needed_list = [
        "gpqa_layout",
        "gpqa_not_synthetic",
        "anthropic_key",
        "nebius_key",
        "budget",
        "run_id_free",
        "per_run_venv",
        "runtime_deps",
        "nebius_meta_profile",
        "nebius_target_profile",
        "tip_ok_for_live",
    ]
    if require_hf_for_diamond:
        live_needed_list.append("hf_token")
    report.ready_for_live = all(by_name.get(n, False) for n in live_needed_list)

    dry = mode != "live"
    report.command = build_sia_command(run_id=run_id, seed=42, dry_run=dry)
    if mode == "live":
        report.command = build_sia_command(run_id=run_id, seed=1, dry_run=False)
    return report


def _g2_min_best_fitness() -> float:
    """Tick 371: floor for G2 PASS (default >0). Override via SIA_G2_MIN_BEST_FITNESS."""
    raw = os.environ.get("SIA_G2_MIN_BEST_FITNESS", "0")
    try:
        return float(raw)
    except ValueError:
        return 0.0


_AGENDA_MARKER = "Contradiction-Aware Research Agenda"
_FEEDBACK_PROMPT_NAME = "feedback_agent_prompt.txt"
_AGENT_DNA_NAME = "agent_dna.json"


def _iter_gen_agent_dirs(run_dir: Path, gen: int) -> list[Path]:
    gen_dir = run_dir / f"gen_{gen}"
    if not gen_dir.is_dir():
        return []
    return sorted(
        p for p in gen_dir.iterdir() if p.is_dir() and p.name.startswith("agent_")
    )


def _delay_all_gen2_checks(run_dir: Path) -> list[CheckResult]:
    """Tick 406: prove fair gen1→gen2 left CABS agenda / technique_seeds off."""
    agents = _iter_gen_agent_dirs(run_dir, 2)
    if not agents:
        return [
            CheckResult(
                "delay_all_feedback_skip",
                False,
                "no gen_2/agent_* — cannot prove delay-all scoped-feedback skip",
            ),
            CheckResult(
                "delay_all_technique_seeds_skip",
                False,
                "no gen_2/agent_* — cannot prove delay-all technique_seeds skip",
            ),
        ]

    fb_leaks: list[str] = []
    fb_missing: list[str] = []
    seed_leaks: list[str] = []
    dna_missing: list[str] = []
    for agent_dir in agents:
        fb_path = agent_dir / _FEEDBACK_PROMPT_NAME
        if not fb_path.is_file():
            fb_missing.append(agent_dir.name)
        else:
            try:
                text = fb_path.read_text(encoding="utf-8")
            except OSError:
                fb_missing.append(agent_dir.name)
            else:
                if _AGENDA_MARKER in text:
                    fb_leaks.append(agent_dir.name)

        dna_path = agent_dir / _AGENT_DNA_NAME
        if not dna_path.is_file():
            dna_missing.append(agent_dir.name)
            continue
        try:
            dna = json.loads(dna_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            dna_missing.append(agent_dir.name)
            continue
        seeds = dna.get("technique_seeds") if isinstance(dna, dict) else None
        if isinstance(seeds, list) and any(str(s).strip() for s in seeds):
            seed_leaks.append(f"{agent_dir.name}:{seeds}")

    if fb_missing:
        fb_ok = False
        fb_detail = f"missing feedback prompt(s): {fb_missing}"
    elif fb_leaks:
        fb_ok = False
        fb_detail = (
            f"Contradiction-Aware agenda leaked into fair gen2 feedback: {fb_leaks}"
        )
    else:
        fb_ok = True
        fb_detail = (
            f"gen2 n={len(agents)} feedback prompts lack {_AGENDA_MARKER!r} (delay-all)"
        )

    if dna_missing:
        seeds_ok = False
        seeds_detail = f"missing/invalid agent_dna.json: {dna_missing}"
    elif seed_leaks:
        seeds_ok = False
        seeds_detail = (
            f"committee technique_seeds on fair gen2 DNA (delay-all leak): {seed_leaks}"
        )
    else:
        seeds_ok = True
        seeds_detail = (
            f"gen2 n={len(agents)} DNA technique_seeds empty (delay-all)"
        )

    return [
        CheckResult("delay_all_feedback_skip", fb_ok, fb_detail),
        CheckResult("delay_all_technique_seeds_skip", seeds_ok, seeds_detail),
    ]


def _steering_lift_gen3_checks(run_dir: Path) -> list[CheckResult]:
    """Tick 509: prove delay-all *lifted* by gen≥3 (G3 Tick 407 positive control).

    When a dry-run (or accidental live) artifact has ``gen_3/``, G2 post-checks
    must refuse never-steer Condition D — otherwise Tick 406 fair-skip alone
    PASSes and paid G3/G4 can burn with D≈B.

    Tick 512: re-wrap ``run_g3_pilot.CheckResult`` into local ``CheckResult`` so
    downstream ``isinstance(..., CheckResult)`` callers stay consistent.
    """
    from run_g3_pilot import validate_g3_d_steering  # noqa: E402

    wrapped: list[CheckResult] = []
    for row in validate_g3_d_steering([run_dir]):
        wrapped.append(
            CheckResult(
                name=str(getattr(row, "name", "steering_applied_gen3")),
                ok=bool(getattr(row, "ok", False)),
                detail=str(getattr(row, "detail", "") or ""),
            )
        )
    return wrapped


def validate_g2_artifacts(
    run_dir: Path,
    *,
    require_steering_lift: bool = False,
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    store = run_dir / "belief_store"
    checks.append(
        CheckResult(
            "belief_store",
            store.is_dir(),
            _repo_relative_detail(store)
            if store.is_dir()
            else "missing belief_store/",
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

    # Tick 406: G2 smoke is max_gen=2 — gen2 is always the fair-bred generation
    # under delay-all. Post-checks must prove Tick 403–405 gates so a regression
    # cannot burn ~$19 on G3/G4 while DNA/feedback look steered early.
    checks.extend(_delay_all_gen2_checks(run_dir))

    # Tick 509: when gen≥3 exists (dry-run --max-gen ≥3) or caller requires
    # the positive control, also prove delay-all lifted (Tick 407).
    gen3_exists = (run_dir / "gen_3").is_dir()
    if require_steering_lift or gen3_exists:
        checks.extend(_steering_lift_gen3_checks(run_dir))

    # Tick 371: refuse G2 PASS when best fitness is missing/zero so the live
    # pipeline cannot auto-advance into paid G3/G4 after a silent 0% eval
    # (historically common with parse/format failures). Exit code 0 from sia
    # alone is not enough — G2 must show a working scoring path.
    from epistemic_results import load_gen_fitness  # noqa: E402

    fitness = load_gen_fitness(run_dir)
    min_best = _g2_min_best_fitness()
    if not fitness:
        checks.append(
            CheckResult(
                "nonzero_fitness",
                False,
                "no fitness in civilization.json / agent_*/results.json — "
                "refuse G3 burn on unscored G2",
            )
        )
    else:
        best = max(float(v.get("best", 0.0) or 0.0) for v in fitness.values())
        ok = best > min_best
        checks.append(
            CheckResult(
                "nonzero_fitness",
                ok,
                (
                    f"best={best:.4f} > min={min_best:g}"
                    if ok
                    else (
                        f"best={best:.4f} ≤ min={min_best:g} — refuse G3/G4 "
                        "auto-advance on broken/zero-acc G2 smoke"
                    )
                ),
            )
        )
    return checks


def _load_gate2_sidecar_raw(gate2_report_md: Path) -> dict:
    """Load machine-readable gate2 sidecar next to the markdown report."""
    sidecar = Path(gate2_report_md).with_suffix(".json")
    if not sidecar.is_file():
        return {}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _post_checks_from_raw(post_raw) -> list[CheckResult]:
    """Parse gate2 sidecar ``post`` / ``prior_live_post`` list into CheckResults."""
    post: list[CheckResult] = []
    if not isinstance(post_raw, list):
        return post
    for item in post_raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if not name:
            continue
        post.append(
            CheckResult(
                name=name,
                ok=bool(item.get("ok")),
                detail=str(item.get("detail") or ""),
            )
        )
    return post


def _live_post_from_gate2_sidecar(data: dict) -> tuple[list[CheckResult], str]:
    """Tick 383/384: extract trustable live post from gate2 sidecar.

    Accepts ``mode=="live"`` + nonempty ``post``, or Tick 384
    ``prior_live_post`` preserved across preflight rewrites.
    """
    mode = str(data.get("mode") or "")
    post_raw = data.get("post")
    if mode == "live" and isinstance(post_raw, list) and post_raw:
        post = _post_checks_from_raw(post_raw)
        if post:
            return post, "live"
    prior = data.get("prior_live_post")
    if isinstance(prior, list) and prior:
        post = _post_checks_from_raw(prior)
        if post:
            return post, "prior_live_post"
    if isinstance(prior, dict):
        post = _post_checks_from_raw(prior.get("post"))
        if post:
            return post, "prior_live_post"
    return [], ""


def refresh_g2_post_on_ledger_skip(
    report: PreflightReport,
    *,
    gate2_report_md: Path,
) -> tuple[list[CheckResult] | None, str]:
    """Tick 383: rebuild / trust G2 post-checks after direct ledger-skip.

    Tick 380 early-returned on ``ledger_skip`` and called ``write_gate2_report``
    without ``post=``, wiping live-executed post-validation (belief_store /
    nonzero_fitness) from the gate2 sidecar. Prefer local complete G2 →
    ``validate_g2_artifacts``. Else trust a live-mode sidecar with nonempty
    ``post`` (or Tick 384 ``prior_live_post`` preserved across preflight;
    never invent post-checks from a bare preflight sidecar).
    """
    run_dir = _run_dir_for(int(report.run_id))
    if run_dir is not None and darwinian_run_complete(run_dir):
        post = validate_g2_artifacts(run_dir)
        note = (
            "Tick 383: re-validated local G2 after ledger-skip "
            f"(run_{report.run_id}; post_ok={all(c.ok for c in post)})"
        )
        report.notes.append(note)
        return post, note

    data = _load_gate2_sidecar_raw(gate2_report_md)
    mode = str(data.get("mode") or "")
    post, source = _live_post_from_gate2_sidecar(data)
    if post:
        note = (
            "Tick 383: trusted live-executed gate2 sidecar post-checks "
            f"(source={source}; no/incomplete local run_{report.run_id}; "
            f"post_ok={all(c.ok for c in post)})"
        )
        report.notes.append(note)
        return post, note

    post_raw = data.get("post")
    note = (
        "Tick 383: ledger-skip but no local G2 artifacts and no live-executed "
        f"gate2 post (mode={mode or 'missing'!r}, "
        f"post_n={len(post_raw) if isinstance(post_raw, list) else 0}) — "
        "post-checks not updated"
    )
    report.notes.append(note)
    return None, note


def gate2_diamond_ready(report: PreflightReport) -> bool:
    """True when preflight already has non-synthetic diamond (Tick 498/500)."""
    by_name = {c.name: c.ok for c in report.checks}
    return icml_preflight_diamond_ready(
        gpqa_not_synthetic_ok=bool(by_name.get("gpqa_not_synthetic")),
        notes=list(report.notes),
    )


def gate2_next_markdown_lines(report: PreflightReport) -> list[str]:
    """Build Gate 2 ``## Next`` lines (Tick 498/537: NEBIUS-first when diamond ready).

    Pre-498 always printed ``Accept HF access for Idavidrein/gpqa`` as step 2,
    even after Tick 497 rematerialized non-synthetic diamond via the public
    OpenAI mirror — operators chased HF while the only PRIMARY blocker was
    ``NEBIUS_API_KEY``. Tick **537**: bodies live in ``gate2_next_step_bodies``
    so tip/secrets ``refresh_gate_reports_next`` cannot drift from writers.
    """
    diamond_ready = gate2_diamond_ready(report)
    return _gate_next_markdown_from_bodies(
        gate2_next_step_bodies(diamond_ready=diamond_ready)
    )


def _sanitize_gate_report_text(text: str, *, repo_root: Path | None = None) -> str:
    """Tick 528: durable gate free-text must not embed absolute repo / host-tmp paths.

    Tick 527 sanitized the unified pipeline report; gate2/3/4 writers still
    persisted raw notes/blockers/check details (diamond-fetch exceptions,
    ``ok → {run_dir}``, deps probes) that can embed ``/workspace/…`` or
    ``/tmp/gpqa_diamond.csv``. Sanitize at write time so committed
    ``gate2_report.*`` stays portable across cold-boot VMs.
    """
    return sanitize_repo_paths_in_text(text or "", repo_root=repo_root or REPO_ROOT)


def write_gate2_report(report: PreflightReport, out: Path, post: list[CheckResult] | None = None) -> None:
    # Tick 528: sanitize free-text in-place before MD/JSON so both stay portable.
    root = REPO_ROOT
    report.notes[:] = [
        _sanitize_gate_report_text(n, repo_root=root) for n in report.notes
    ]
    report.blockers[:] = [
        _sanitize_gate_report_text(b, repo_root=root) for b in report.blockers
    ]
    for c in report.checks:
        c.detail = _sanitize_gate_report_text(c.detail, repo_root=root)

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
            # Tick 526: durable planned argv — basename python, no /usr/bin/…
            " ".join(portable_argv_for_durable(report.command)),
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
        # Tick 523: durable MD/JSON must not embed absolute /workspace/... paths.
        post_dicts = _post_as_check_dicts(post)
        lines.extend(
            [
                "## Post-run artifact validation",
                "",
                "| Check | OK | Detail |",
                "|-------|----|--------|",
            ]
        )
        for c in post_dicts:
            lines.append(
                f"| `{c['name']}` | {'yes' if c['ok'] else 'NO'} | {c['detail']} |"
            )
        lines.append("")
        g2_pass = all(c["ok"] for c in post_dicts) and report.mode in {
            "dry-run",
            "live",
        }
        if report.mode == "live" and g2_pass:
            lines.append("**G2 live status:** PASS")
        elif report.mode == "dry-run" and g2_pass:
            lines.append("**G2 dry-run harness status:** PASS (not live G2)")
        else:
            lines.append("**G2 status:** FAIL / incomplete")
        lines.append("")
    else:
        post_dicts = []
        lines.append(
            "**G2 live status:** NOT RUN this tick"
            if report.mode == "preflight"
            else "**G2 status:** command not executed"
        )
        lines.append("")

    next_md = gate2_next_markdown_lines(report)
    lines.extend(next_md)
    # Tick 536: JSON next_steps mirrors MD ## Next (pipeline Tick 535 parity).
    cleaned_next = [
        _sanitize_gate_report_text(s, repo_root=root)
        for s in extract_numbered_next_steps(next_md)
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Machine-readable sidecar for automation ticks
    sidecar = out.with_suffix(".json")
    # Tick 384: preflight rewrites must not wipe live post evidence. Preserve
    # prior live post under prior_live_post so pipeline G2→G3 / ledger-skip
    # trust still works after cron --preflight-only.
    existing = _load_gate2_sidecar_raw(out)
    prior_live_post = None
    if post is not None and report.mode == "live":
        # Tick 405: only *live* post becomes prior_live_post. Dry-run must not
        # poison pipeline G2→G3 trust / committed prior_live evidence
        # (Tick 384–389).
        prior_live_post = post_dicts
    elif report.mode == "dry-run":
        # Preserve a real live prior if the previous sidecar was live or a
        # preflight that already carried prior_live_post. Scrub dry-run→dry-run
        # pollution (prior_live_post copied from dry-run post).
        prev_mode = str(existing.get("mode") or "")
        if prev_mode == "live":
            preserved, _src = _live_post_from_gate2_sidecar(existing)
            if preserved:
                prior_live_post = _post_as_check_dicts(preserved)
        elif prev_mode != "dry-run" and isinstance(
            existing.get("prior_live_post"), (list, dict)
        ):
            prior_live_post = _post_as_check_dicts(existing.get("prior_live_post"))
        # else: leave None (do not carry dry-run post as prior_live)
    else:
        preserved, _src = _live_post_from_gate2_sidecar(existing)
        if preserved:
            prior_live_post = _post_as_check_dicts(preserved)
        elif isinstance(existing.get("prior_live_post"), list):
            prior_live_post = _post_as_check_dicts(existing.get("prior_live_post"))
        elif isinstance(existing.get("prior_live_post"), dict):
            prior_live_post = _post_as_check_dicts(existing.get("prior_live_post"))
    payload = {
        "timestamp": report.timestamp,
        "mode": report.mode,
        "run_id": report.run_id,
        "ready_for_live": report.ready_for_live,
        "ready_for_dry_run": report.ready_for_dry_run,
        "blockers": report.blockers,
        "checks": [asdict(c) for c in report.checks],
        # Tick 526: durable planned argv — basename python, no /usr/bin/…
        "command": portable_argv_for_durable(report.command),
        "post": post_dicts,
        "next_steps": cleaned_next,
    }
    if prior_live_post is not None:
        payload["prior_live_post"] = prior_live_post
    sidecar.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    # Tick 389: mirror prior_live into committed evidence (cross-VM) + stash.
    # Tick 405: only when prior_live_post is present (live-stamped or preserved).
    if prior_live_post is not None:
        persist_prior_live_stash_from_working_tree(REPO_ROOT)
    # Tick 510: durable gen≥3 steering-lift proof survives the next preflight
    # rewrite of gate2_report (live G2 stays max_gen=2 and would otherwise lose
    # the Tick 509 positive control before paid G3).
    if post is not None and report.mode == "dry-run":
        post_ok, _post_detail = post_checks_satisfy_steering_lift(post)
        if post_ok:
            try:
                write_steering_lift_proof(
                    run_id=int(report.run_id),
                    post=post,
                    timestamp=report.timestamp,
                    source="gate2_dry_run_write",
                    repo_root=REPO_ROOT,
                )
            except ValueError:
                pass  # should not happen after post_ok; keep gate2 write intact


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
        "--max-gen",
        type=int,
        default=None,
        help=(
            "Darwinian max_gen (default 2). Tick 509: dry-run may use ≥3 to prove "
            "delay-all *lifted* (gen≥3 Contradiction-Aware agenda). Live G2 refuses "
            "max_gen≠2 (budget smoke shape)."
        ),
    )
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
    p.add_argument(
        "--fetch-diamond",
        action="store_true",
        help=(
            "Before preflight/live: replace synthetic smoke with real GPQA diamond "
            "(public OpenAI simple-evals mirror auto-fetch — Tick 497; or "
            "--diamond-csv; or HF_TOKEN + accepted Idavidrein/gpqa access)."
        ),
    )
    p.add_argument(
        "--diamond-csv",
        type=Path,
        default=None,
        help="Optional local gpqa_diamond.csv for --fetch-diamond (skips HF download)",
    )
    p.add_argument(
        "--diamond-n",
        type=int,
        default=5,
        help="Questions to materialize with --fetch-diamond (default 5)",
    )
    p.add_argument(
        "--allow-stale-tip",
        action="store_true",
        help="Allow --live even when local Tick lags remote tip (dangerous; Tick 306)",
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

    max_gen = 2 if args.max_gen is None else int(args.max_gen)
    if max_gen < 1:
        print("G2 refuses max_gen < 1", file=sys.stderr)
        return 2
    # Tick 509: live G2 stays max_gen=2 (Section 21 smoke). Dry-run may raise
    # max_gen to prove gen≥3 steering lift before paid G3.
    if selected == "live" and max_gen != 2:
        print(
            "G2 live refuses max_gen≠2 (budget smoke shape); "
            "use --dry-run --max-gen ≥3 for Tick 509 steering-lift proof",
            file=sys.stderr,
        )
        return 2
    require_steering_lift = selected == "dry-run" and max_gen >= 3
    if require_steering_lift and max_gen < 3:
        print("G2 dry-run steering-lift proof requires max_gen≥3", file=sys.stderr)
        return 2

    # Tick 278: auto-wire local diamond CSV under --fetch-diamond (match cron).
    diamond_csv, csv_auto = autowire_diamond_csv(
        args.diamond_csv, fetch_diamond=bool(args.fetch_diamond), repo_root=REPO_ROOT
    )
    args.diamond_csv = diamond_csv
    # Tick 502: on-disk non-synthetic diamond also skips HF (Tick 499 diamond_ready).
    require_hf = icml_fetch_diamond_needs_hf(
        fetch_diamond=bool(args.fetch_diamond),
        diamond_csv=args.diamond_csv,
        repo_root=REPO_ROOT,
    )
    allow_stale = bool(args.allow_stale_tip)

    # Tick 275/278/502/503: refuse --live --fetch-diamond without fetch_diamond_ok
    # before materialize. Tick **503**: CSV / public-mirror auto-wire makes
    # ``require_hf`` false, but missing NEBIUS still means fetch_diamond_ok=false
    # — do not enter paid live materialize/preflight only to fail on keys.
    if selected == "live" and args.fetch_diamond:
        secrets_status = collect_icml_secrets_status()
        if not secrets_status.get("fetch_diamond_ok"):
            diamond_ready = bool(secrets_status.get("diamond_ready")) or (
                args.diamond_csv is not None
            ) or icml_ondisk_nonsynthetic_gpqa(REPO_ROOT)
            phrase = icml_human_required_secrets_phrase(
                for_fetch_diamond=not diamond_ready
            )
            report = run_preflight(
                mode=selected,
                run_id=run_id,
                require_hf_for_diamond=require_hf and not diamond_ready,
                allow_stale_tip=allow_stale,
            )
            for b in secrets_status.get("blockers") or [
                f"fetch_diamond_ok=false (need {phrase})"
            ]:
                report.notes.append(f"secrets: {b}")
            if diamond_ready:
                report.notes.append(
                    "Add NEBIUS_API_KEY per docs/ICML_HUMAN_UNBLOCK.md "
                    "(diamond already ready; HF optional — Tick 497/502/503)."
                )
            else:
                report.notes.append(
                    "Add secrets per docs/ICML_HUMAN_UNBLOCK.md "
                    f"({phrase}); or pass --diamond-csv / drop gpqa_diamond.csv / "
                    "keep on-disk non-synthetic diamond to skip HF (Tick 502)."
                )
            report.command = build_sia_command(
                run_id=run_id, seed=seed, dry_run=False
            )
            write_gate2_report(report, args.report)
            print(
                "G2 refused --live --fetch-diamond "
                f"(fetch_diamond_ok=false) → {args.report}",
                file=sys.stderr,
            )
            for b in report.blockers:
                print(f"  BLOCK: {b}", file=sys.stderr)
            return 4

    fetch_notes: list[str] = []
    if csv_auto and args.diamond_csv is not None:
        fetch_notes.append(diamond_csv_autowire_note(args.diamond_csv))
    if args.fetch_diamond or args.diamond_csv is not None:
        ondisk_ready = icml_ondisk_nonsynthetic_gpqa(REPO_ROOT)
        # Tick 504: auto-wired CSV must not force rematerialize when ondisk ready.
        if icml_should_keep_ondisk_diamond(
            diamond_csv=args.diamond_csv, csv_auto=csv_auto, repo_root=REPO_ROOT
        ):
            fetch_notes.append(
                "Tick 502/504: kept existing non-synthetic diamond; "
                "skip rematerialize (auto-wired CSV is fallback only; "
                "pass explicit --diamond-csv to force refresh; HF optional)"
            )
        elif args.diamond_csv is not None:
            # Tick 282: bootstrap huggingface_hub (+ uv/SIA) BEFORE materialize.
            deps_ok, deps_detail = ensure_deps_before_diamond_fetch(allow_install=True)
            fetch_notes.append(f"runtime deps before diamond: {deps_detail}")
            try:
                wrote = materialize_from_csv(
                    args.diamond_csv,
                    ["SIA", "sia-upstream"],
                    n=args.diamond_n,
                    seed=seed,
                    force=True,
                    repo_root=REPO_ROOT,
                )
                fetch_notes.append(f"materialized diamond from CSV → {wrote}")
            except Exception as exc:
                fetch_notes.append(f"diamond fetch failed: {exc}")
                if selected == "live":
                    print(
                        f"G2 live refused — --fetch-diamond failed: {exc}",
                        file=sys.stderr,
                    )
                    report = run_preflight(
                        mode=selected,
                        run_id=run_id,
                        require_hf_for_diamond=require_hf,
                        allow_stale_tip=allow_stale,
                    )
                    report.notes.extend(fetch_notes)
                    report.command = build_sia_command(
                        run_id=run_id, seed=seed, dry_run=False
                    )
                    write_gate2_report(report, args.report)
                    return 3
        elif ondisk_ready:
            # Defensive: keep path if helper disagreed (should be unreachable).
            fetch_notes.append(
                "Tick 502: kept existing non-synthetic diamond; "
                "skip HF rematerialize (HF optional when diamond ready)"
            )
        else:
            # Tick 282: bootstrap huggingface_hub (+ uv/SIA) BEFORE materialize.
            deps_ok, deps_detail = ensure_deps_before_diamond_fetch(allow_install=True)
            fetch_notes.append(f"runtime deps before diamond: {deps_detail}")
            if not deps_ok:
                fetch_notes.append(
                    "runtime_deps failed before HF materialize — "
                    "cannot import/bootstrap huggingface_hub"
                )
                if selected == "live":
                    print(
                        f"G2 live refused — runtime deps before diamond failed: {deps_detail}",
                        file=sys.stderr,
                    )
                    report = run_preflight(
                        mode=selected,
                        run_id=run_id,
                        require_hf_for_diamond=require_hf,
                        allow_stale_tip=allow_stale,
                    )
                    report.notes.extend(fetch_notes)
                    report.command = build_sia_command(
                        run_id=run_id, seed=seed, dry_run=False
                    )
                    write_gate2_report(report, args.report)
                    return 3
            try:
                wrote = materialize_from_hf(
                    ["SIA", "sia-upstream"],
                    n=args.diamond_n,
                    seed=seed,
                    force=True,
                    repo_root=REPO_ROOT,
                )
                fetch_notes.append(f"materialized diamond from HF → {wrote}")
            except Exception as exc:
                fetch_notes.append(f"diamond fetch failed: {exc}")
                if selected == "live":
                    print(
                        f"G2 live refused — --fetch-diamond failed: {exc}",
                        file=sys.stderr,
                    )
                    report = run_preflight(
                        mode=selected,
                        run_id=run_id,
                        require_hf_for_diamond=require_hf,
                        allow_stale_tip=allow_stale,
                    )
                    report.notes.extend(fetch_notes)
                    report.command = build_sia_command(
                        run_id=run_id, seed=seed, dry_run=False
                    )
                    write_gate2_report(report, args.report)
                    return 3

    report = run_preflight(
        mode=selected,
        run_id=run_id,
        require_hf_for_diamond=require_hf,
        allow_stale_tip=allow_stale,
    )
    report.notes.extend(fetch_notes)
    if require_steering_lift:
        report.notes.append(
            f"Tick 509: dry-run max_gen={max_gen} — post-checks require gen≥3 "
            "Contradiction-Aware agenda (delay-all lift positive control)"
        )
    report.command = build_sia_command(
        run_id=run_id,
        seed=seed,
        dry_run=(selected != "live"),
        max_gen=max_gen,
    )

    if selected == "preflight":
        write_gate2_report(report, args.report)
        print(f"G2 preflight written → {args.report}")
        print(f"ready_for_dry_run={report.ready_for_dry_run} ready_for_live={report.ready_for_live}")
        if report.ledger_skip:
            print("ledger_skip=True (Tick 380 — --live would no-op)")
        for b in report.blockers:
            print(f"  BLOCK: {b}")
        # Preflight success means the checker ran; live blockers are expected without keys.
        return 0

    if selected == "dry-run" and not report.ready_for_dry_run:
        write_gate2_report(report, args.report)
        print("G2 dry-run refused — preflight failed", file=sys.stderr)
        return 2
    # Tick 380: ledger-complete G2 → exit 0 without sia (even if secrets absent).
    # Tick 383: still re-validate / trust post-checks (G3 Tick 382 / G4 Tick 381
    # parity) so ledger-skip cannot wipe nonzero-fitness evidence.
    if selected == "live" and report.ledger_skip:
        report.notes.append(
            "Tick 380: skipped paid G2 — ledger stages_complete already lists G2 "
            f"for run_{run_id}"
        )
        post, post_note = refresh_g2_post_on_ledger_skip(
            report, gate2_report_md=args.report
        )
        report.notes.append(post_note)
        write_gate2_report(report, args.report, post=post)
        print(f"G2 live skipped (ledger resume) → {args.report}")
        print(post_note)
        post_ok = bool(post) and all(c.ok for c in post)
        print(f"g2_post_ok={post_ok} post_n={len(post or [])}")
        # Tick 384: do not false-green into G3 when ledger-skip cannot prove
        # nonzero-fitness / belief_store post-checks (pipeline calls g2.main).
        if not post_ok:
            print(
                "G2 ledger-skip refused G3 advance — missing/failed post-checks",
                file=sys.stderr,
            )
            return 4
        return 0
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
        post.append(
            CheckResult(
                "run_dir",
                True,
                _repo_relative_detail(run_dir),
            )
        )
        post.extend(
            validate_g2_artifacts(
                run_dir, require_steering_lift=require_steering_lift
            )
        )

    g2_ok = all(c.ok for c in post)
    # Tick 379: direct live success must stamp ledger G2 so cross-VM cron
    # (runs/ gitignored) does not re-burn a completed smoke.
    if selected == "live" and g2_ok:
        _, persist_detail = persist_direct_gate_stage_spend(
            "G2",
            [int(run_id)],
            run_estimate_usd=float(default_g2_estimate_usd()),
            resolve_run_dir=_run_dir_for,
            repo_root=REPO_ROOT,
        )
        report.notes.append(persist_detail)

    write_gate2_report(report, args.report, post=post)
    print(f"G2 report → {args.report}")
    # Tick 422: direct --live must commit durable ledgers (pipeline/cron parity).
    if selected == "live":
        ok_ledgers, ledger_detail = commit_durable_ledgers_after_live(REPO_ROOT)
        print(f"durable_ledgers_after_live: ok={ok_ledgers} {ledger_detail}")
    return 0 if g2_ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
