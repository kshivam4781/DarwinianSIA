#!/usr/bin/env python3
"""Recover the canonical ICML tip branch after a cron boot from main (Tick 269).

Every automation tick often starts on a fresh ``cursor/icml-epistemic-results-*``
branch cut from ``main``, which lacks ``docs/ICML_PROGRESS.md`` and the live
stack. Before paid ``--live``, agents must fast-forward to the highest remote
Tick tip (prefer secrets-first / Astral-bootstrap lineage over Portal-Save-only
forks).

Examples (Linux/cloud: python3; Windows venv: python):
  python3 scripts/icml_recover_tip.py              # print tip + write status JSON
  python3 scripts/icml_recover_tip.py --fetch      # refresh remote refs first
  python3 scripts/icml_recover_tip.py --apply      # git reset --hard to tip
                                               # (+ Tick 339 tip PR anti-churn checkout)
                                               # (+ Tick 388 prior_live stash/reinject)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from icml_env_checks import (  # noqa: E402
    discard_ephemeral_icml_dirt,
    reinject_prior_live_stash,
    write_icml_tip_status,
)


def _git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def apply_tip(tip_ref: str) -> int:
    """Hard-reset current branch to ``tip_ref``. Returns process exit code.

    Tick 388: mirror ``icml_boot_recover.sh --apply`` / cron tip recover —
    discard ephemeral dirt (Tick 387 stashes ``prior_live_*`` first), then
    reinject after ``git reset --hard``. Tick 387 only wired stash into cron +
    ``icml_boot_recover.sh``; agents using ``icml_recover_tip.py --apply`` still
    refused dirty trees without stashing and never reinjected after hard-reset.
    """
    # Tick 388 / Tick 286 parity: discard preflight ephemerals (stash prior_live).
    ok_discard, discard_detail = discard_ephemeral_icml_dirt(REPO_ROOT)
    print(f"ephemeral_discard: ok={ok_discard} {discard_detail}")

    status = _git(["status", "--porcelain", "-uall"])
    if status.returncode != 0:
        print(f"git status failed: {status.stderr.strip()}", file=sys.stderr)
        return 2
    # Tick 388: gitignored prior_live stash must not block --apply (same class
    # of bug as Tick 356/359 boot/call JSON). Filter even if .gitignore lags.
    # Tick 389: committed evidence may be newly written during persist — filter
    # it too (reinject rewrites evidence after hard-reset).
    from icml_env_checks import (
        ICML_PRIOR_LIVE_EVIDENCE_RELPATH,
        ICML_PRIOR_LIVE_STASH_RELPATH,
    )

    stash_norm = ICML_PRIOR_LIVE_STASH_RELPATH.replace("\\", "/")
    evidence_norm = ICML_PRIOR_LIVE_EVIDENCE_RELPATH.replace("\\", "/")
    dirty_lines: list[str] = []
    for line in (status.stdout or "").splitlines():
        if len(line) < 4:
            continue
        rest = line[3:]
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        rest = rest.strip().strip('"').replace("\\", "/")
        if rest in {stash_norm, evidence_norm}:
            continue
        dirty_lines.append(line)
    dirty = "\n".join(dirty_lines).strip()
    if dirty:
        print(
            "Working tree dirty — refuse --apply (commit/stash first):\n"
            f"{dirty[:500]}",
            file=sys.stderr,
        )
        # Still reinject any stash captured before the refuse (parity with cron).
        ok_pl, detail_pl = reinject_prior_live_stash(REPO_ROOT)
        print(f"prior_live_reinject: ok={ok_pl} {detail_pl}")
        return 3

    reset = _git(["reset", "--hard", tip_ref])
    if reset.returncode != 0:
        print(
            f"git reset --hard {tip_ref} failed: "
            f"{(reset.stderr or reset.stdout or '').strip()}",
            file=sys.stderr,
        )
        return 4
    print(f"Recovered tip: HEAD now at {tip_ref}")
    head = _git(["log", "-1", "--oneline"])
    if head.returncode == 0:
        print(head.stdout.strip())

    # Tick 388: reinject prior_live_* after hard-reset (stash survives; Tick 387
    # path was cron/boot_recover only — recover_tip --apply was the hole).
    ok_pl, detail_pl = reinject_prior_live_stash(REPO_ROOT)
    print(f"prior_live_reinject: ok={ok_pl} {detail_pl}")

    # Tick 339: tip PR anti-churn checkout after --apply (mirrors boot_recover).
    # Tick 338 only wired this into icml_cron_entry.sh; recover --apply alone
    # still left greenfield branch names → new tip PR churn.
    checkout = REPO_ROOT / "scripts" / "icml_checkout_tip_pr_branch.sh"
    if checkout.is_file():
        cur = _git(["rev-parse", "--abbrev-ref", "HEAD"])
        cur_branch = (cur.stdout or "").strip() if cur.returncode == 0 else "?"
        print(f"tip_pr_anti_churn_checkout (recover_tip): attempting from {cur_branch}")
        anti = subprocess.run(
            ["bash", str(checkout)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if anti.stdout:
            print(anti.stdout.rstrip())
        if anti.returncode == 0:
            after = _git(["rev-parse", "--abbrev-ref", "HEAD"])
            after_b = (after.stdout or "").strip() if after.returncode == 0 else "?"
            print(f"tip_pr_anti_churn_checkout=ok branch={after_b}")
        else:
            if anti.stderr:
                print(anti.stderr.rstrip(), file=sys.stderr)
            print(
                "tip_pr_anti_churn_checkout=skip_or_fail "
                f"(continuing on {cur_branch}; do NOT open a new tip PR)",
                file=sys.stderr,
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--fetch",
        action="store_true",
        help="git fetch origin ICML tip refs before scanning",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="git reset --hard to discovered tip (clean tree required)",
    )
    p.add_argument(
        "--status-out",
        type=Path,
        default=REPO_ROOT / "docs" / "icml_tip_status.json",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print full tip status JSON to stdout",
    )
    args = p.parse_args(argv)

    status = write_icml_tip_status(args.status_out, fetch=args.fetch)
    tip_ref = status.get("remote_tip_ref")
    local_tick = status.get("local_tick")
    remote_tick = status.get("remote_tip_tick")
    tip_ok = bool(status.get("tip_ok_for_live"))

    if args.json:
        print(json.dumps(status, indent=2))
    else:
        print(f"local_tick={local_tick}")
        print(f"remote_tip_tick={remote_tick}")
        print(f"remote_tip_ref={tip_ref}")
        print(f"tip_ok_for_live={tip_ok}")
        print(f"status → {args.status_out}")
        for b in status.get("blockers") or []:
            print(f"  BLOCK: {b}")
        if tip_ref and not tip_ok:
            print("Recover: python3 scripts/icml_recover_tip.py --apply")
            print(
                "  (main boot: git show "
                f"{tip_ref}:scripts/icml_boot_recover.sh | bash -s -- --apply)"
            )
            print(f"  (or: git reset --hard {tip_ref})")

    if not args.apply:
        return 0 if tip_ok or tip_ref else 1

    if not tip_ref:
        print("No remote ICML tip found — cannot --apply", file=sys.stderr)
        return 5
    if tip_ok and local_tick == remote_tick:
        print(f"Already on tip Tick {local_tick}; --apply is a no-op reset to {tip_ref}")
    rc = apply_tip(str(tip_ref))
    if rc == 0:
        # Refresh status after reset.
        write_icml_tip_status(args.status_out, fetch=False)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
