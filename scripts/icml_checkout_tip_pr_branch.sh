#!/usr/bin/env bash
# ICML Thesis 1 — Tip PR anti-churn checkout (Tick 337–340 / 357).
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

# Prefer fresh tip/secrets JSON; fall back to resolve via Python.
# Tick 351: tip_pr_head_ref fallback when tip_pr_commit_branch empty but
# mergeable is not CONFLICTING (UNKNOWN/null used to skip anti-churn).
BRANCH=""
if [[ -f docs/icml_tip_status.json ]]; then
  BRANCH="$(python3 -c "
import json
from pathlib import Path
p = Path('docs/icml_tip_status.json')
d = json.loads(p.read_text(encoding='utf-8'))
branch = d.get('tip_pr_commit_branch') or ''
if not branch:
    mergeable = str(d.get('tip_pr_mergeable') or '').strip().upper()
    state = str(d.get('tip_pr_merge_state_status') or '').strip().upper()
    head = (d.get('tip_pr_head_ref') or '').strip()
    if head and mergeable != 'CONFLICTING' and state != 'DIRTY':
        branch = head
print(branch)
" 2>/dev/null || true)"
fi
if [[ -z "${BRANCH}" ]]; then
  BRANCH="$(python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path('scripts').resolve()))
from icml_env_checks import prefer_tip_pr_commit_branch, resolve_icml_tip_pr
pr = resolve_icml_tip_pr()
print(prefer_tip_pr_commit_branch(pr) or '')
" 2>/dev/null || true)"
fi

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
