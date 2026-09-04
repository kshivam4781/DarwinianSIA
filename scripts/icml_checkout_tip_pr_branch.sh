#!/usr/bin/env bash
# ICML Thesis 1 — Tip PR anti-churn checkout (Tick 337–338).
#
# Cron boots a greenfield branch every tick. Opening a *new* tip PR supersedes
# the MERGEABLE one and defeats tip→main. When tip/secrets JSON has
# tip_pr_anti_churn=true / tip_pr_commit_branch set, checkout that branch so
# subsequent commits update the existing tip PR (open_git_pr branch=<that>).
#
# Tick 338: `bash scripts/icml_cron_entry.sh` calls this automatically after
# writing tip/secrets status (manual use still OK for agents mid-tick).
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
BRANCH=""
if [[ -f docs/icml_tip_status.json ]]; then
  BRANCH="$(python3 -c "
import json
from pathlib import Path
p = Path('docs/icml_tip_status.json')
d = json.loads(p.read_text(encoding='utf-8'))
print(d.get('tip_pr_commit_branch') or '')
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
  echo "tip_pr_anti_churn: no MERGEABLE tip_pr_commit_branch (main may already have tip, or tip PR CONFLICTING)" >&2
  exit 2
fi

echo "tip_pr_commit_branch=${BRANCH}"
if [[ "${DRY_RUN}" -eq 1 ]]; then
  exit 0
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
