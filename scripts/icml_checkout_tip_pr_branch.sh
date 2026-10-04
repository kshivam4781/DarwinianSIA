#!/usr/bin/env bash
# ICML Thesis 1 — Tip PR anti-churn checkout (Tick 337–340 / 357–358 / 531).
#
# Cron boots a greenfield branch every tick. Opening a *new* tip PR supersedes
# the MERGEABLE one and defeats tip→main. When tip/secrets JSON has
# tip_pr_anti_churn=true / tip_pr_commit_branch set, checkout that branch so
# subsequent commits update the existing tip PR (open_git_pr branch=<that>).
#
# Tick 338: `bash scripts/icml_cron_entry.sh` calls this automatically after
# writing tip/secrets status (manual use still OK for agents mid-tick).
# Tick 339: `icml_boot_recover.sh --apply` + `icml_recover_tip.py --apply`
# also call this so chicken-egg recover alone lands on tip_pr_commit_branch.
# Tick 340: even after checkout, open_git_pr MUST pass branch=<tip_pr_commit_branch>
# (MCP defaults to greenfield boot branch when omitted) — see docs/icml_open_git_pr.json.
# Tick 357: persist current greenfield ``cursor/*`` boot to
# ``docs/icml_cloud_boot_branch.txt`` *before* switching to tip (agents often
# call this mid-tick without cron capture; also rejects short poison names).
# Tick 358: after checkout, refresh ``docs/icml_open_git_pr_call.json`` so
# ``cloud_boot_branch`` matches the just-persisted boot (not a stale prior-tick
# value left when agents skip full cron status rewrite).
# Tick 531: prefer *live* tip-PR resolve over committed tip_status.json —
# stale tip_pr_commit_branch (e.g. …-f49c after tip --apply to …-9e39) must
# not rewind tip Tick N → N-1.
#
# Usage:
#   bash scripts/icml_checkout_tip_pr_branch.sh
#   bash scripts/icml_checkout_tip_pr_branch.sh --dry-run
#
# Exit 0 when checked out (or dry-run prints branch). Exit 2 when anti-churn
# does not apply (no MERGEABLE tip PR / main already has tip files).

set -euo pipefail

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      sed -n '2,18p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $arg" >&2
      exit 2
      ;;
  esac
done

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${ROOT}" ]]; then
  echo "Not inside a git repo" >&2
  exit 2
fi
cd "$ROOT"

# Tick 531: live tip-PR resolve first; tip_status.json only as fallback.
# Pre-531 preferred committed tip_status tip_pr_commit_branch, which rewound
# tip after --apply when JSON still named the prior tip PR head (f49c vs 9e39).
# Tick 351 tip_pr_head_ref fallback remains inside tip_pr_commit_branch_from_status_json.
BRANCH="$(python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path('scripts').resolve()))
from icml_env_checks import resolve_anti_churn_checkout_branch
print(resolve_anti_churn_checkout_branch() or '')
" 2>/dev/null || true)"

if [[ -z "${BRANCH}" ]]; then
  echo "tip_pr_anti_churn: no usable tip_pr_commit_branch (main may already have tip, or tip PR CONFLICTING)" >&2
  exit 2
fi

echo "tip_pr_commit_branch=${BRANCH}"
if [[ "${DRY_RUN}" -eq 1 ]]; then
  exit 0
fi

# Tick 357: persist greenfield boot BEFORE tip checkout so mid-tick agents
# (and chicken-egg recover) keep a durable MCP-default warn even when cron
# capture did not run. Rejects short poison (must be full cursor/* ≠ tip).
CUR="$(git branch --show-current 2>/dev/null || true)"
if [[ -n "${CUR}" && "${CUR}" != "${BRANCH}" && "${CUR}" == cursor/* ]]; then
  python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path('scripts').resolve()))
from icml_env_checks import persist_cloud_boot_branch
boot = '''${CUR}'''.strip()
tip = '''${BRANCH}'''.strip()
got = persist_cloud_boot_branch(boot, tip_commit_branch=tip)
if got:
    print(f'persisted_cloud_boot_branch={got}')
" 2>/dev/null || true
fi

git fetch origin "${BRANCH}:refs/remotes/origin/${BRANCH}" 2>/dev/null \
  || git fetch origin "+refs/heads/${BRANCH}:refs/remotes/origin/${BRANCH}" 2>/dev/null \
  || true

if git show-ref --verify --quiet "refs/remotes/origin/${BRANCH}"; then
  git checkout -B "${BRANCH}" "refs/remotes/origin/${BRANCH}"
elif git show-ref --verify --quiet "refs/heads/${BRANCH}"; then
  git checkout "${BRANCH}"
else
  # Greenfield recover already at tip SHA — rename current branch.
  git checkout -B "${BRANCH}"
fi

echo "Checked out ${BRANCH} (anti-churn — push here; open_git_pr branch=${BRANCH})"

# Tick 358: rewrite open_git_pr call JSON so cloud_boot_branch matches the
# boot just persisted above (stale prior-tick call JSON otherwise misleads).
python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path('scripts').resolve()))
from icml_env_checks import refresh_open_git_pr_after_tip_checkout
hint = refresh_open_git_pr_after_tip_checkout(tip_commit_branch='''${BRANCH}'''.strip())
if hint:
    boot = hint.get('cloud_boot_branch') or ''
    call = hint.get('open_git_pr_call_file') or 'docs/icml_open_git_pr_call.json'
    print(f'refreshed_open_git_pr_call={call} cloud_boot_branch={boot or \"<none>\"}')
" 2>/dev/null || true
