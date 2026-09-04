#!/usr/bin/env bash
# ICML tip recover that works from a main-only tree (Tick 270).
#
# Cron often boots a fresh branch from main without docs/ICML_PROGRESS.md or
# scripts/icml_recover_tip.py. This pure-bash helper only needs git + origin:
# it fetches ICML tip refs, picks the highest Tick with secrets-first lineage
# preference, and optionally hard-resets HEAD to that tip.
#
# Usage (from repo root, even on main once this file exists):
#   bash scripts/icml_boot_recover.sh              # print tip; exit 0 if local OK
#   bash scripts/icml_boot_recover.sh --fetch      # refresh remote refs first
#   bash scripts/icml_boot_recover.sh --apply      # git reset --hard to tip
#
# Chicken-egg from main (this script not present yet) — Tick 272/331/332 lineage pick
# (never committerdate-only; greenfield main branches can be newer than tip).
# Tick 331/332: also fetch/scan cursor/bc-* cloud cron boots:
#   git fetch origin \
#     '+refs/heads/cursor/icml-epistemic-results-*:refs/remotes/origin/cursor/icml-epistemic-results-*' \
#     '+refs/heads/cursor/bc-*:refs/remotes/origin/cursor/bc-*'
#   TIP_REF=$(bash scripts/icml_pick_remote_tip.sh --require scripts/icml_boot_recover.sh)  # if picker present
#   # else: scan refs that contain this script + highest Tick (see AGENTS.md / HUMAN_UNBLOCK)
#   git show "${TIP_REF}:scripts/icml_boot_recover.sh" | bash -s -- --fetch --apply
#
# Prefer once tip tree is present:
#   python3 scripts/icml_recover_tip.py --apply

set -euo pipefail

FETCH=0
APPLY=0
for arg in "$@"; do
  case "$arg" in
    --fetch) FETCH=1 ;;
    --apply) APPLY=1 ;;
    -h|--help)
      sed -n '2,28p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $arg (want --fetch / --apply)" >&2
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

if [[ "$FETCH" -eq 1 ]]; then
  # Tick 331: also fetch cursor/bc-* (cloud cron boot branches).
  git fetch origin \
    '+refs/heads/cursor/icml-epistemic-results-*:refs/remotes/origin/cursor/icml-epistemic-results-*' \
    '+refs/heads/cursor/icml-epistemic-evolution-*:refs/remotes/origin/cursor/icml-epistemic-evolution-*' \
    '+refs/heads/cursor/bc-*:refs/remotes/origin/cursor/bc-*' \
    2>/dev/null || git fetch origin --prune 2>/dev/null || true
fi

# Grep a file (avoid printf|grep -q under pipefail → SIGPIPE false negatives).
file_has() {
  local pat="$1" file="$2"
  grep -qi -- "$pat" "$file" 2>/dev/null
}

score_lineage_file() {
  local file="$1"
  local score=0
  file_has 'secrets-first' "$file" && score=$((score + 1)) || true
  file_has 'write_icml_secrets_status' "$file" && score=$((score + 1)) || true
  file_has 'ensure_icml_runtime_deps' "$file" && score=$((score + 1)) || true
  file_has 'ensure_uv_on_path' "$file" && score=$((score + 1)) || true
  file_has 'Astral uv' "$file" && score=$((score + 1)) || true
  echo "$score"
}

parse_tick_file() {
  local file="$1"
  # Newest Tick heading is near the top of ICML_PROGRESS.md
  grep -oE 'Tick[[:space:]]+[0-9]+' "$file" 2>/dev/null | head -1 | grep -oE '[0-9]+' || true
}

best_tick=-1
best_score=-1
best_ref=""
best_sha=""

TMPDIR_REC="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_REC"' EXIT

while IFS= read -r ref; do
  [[ -z "$ref" ]] && continue
  prog="${TMPDIR_REC}/progress.txt"
  if ! git show "${ref}:docs/ICML_PROGRESS.md" >"$prog" 2>/dev/null; then
    continue
  fi
  [[ -s "$prog" ]] || continue
  tick="$(parse_tick_file "$prog")"
  [[ -z "$tick" ]] && continue
  score="$(score_lineage_file "$prog")"
  sha="$(git rev-parse --short "${ref}" 2>/dev/null || echo "?")"
  # Prefer higher Tick; tie-break on lineage_score.
  if [[ "$tick" -gt "$best_tick" ]] || \
     { [[ "$tick" -eq "$best_tick" ]] && [[ "$score" -gt "$best_score" ]]; }; then
    best_tick="$tick"
    best_score="$score"
    best_ref="$ref"
    best_sha="$sha"
  fi
done < <(
  # Tick 331: include cursor/bc-* cloud cron boots (ICML_PROGRESS filter below).
  git for-each-ref --format='%(refname)' \
    'refs/remotes/origin/cursor/icml-epistemic-results-*' \
    'refs/remotes/origin/cursor/icml-epistemic-evolution-*' \
    'refs/remotes/origin/cursor/bc-*' 2>/dev/null
)

local_tick=""
if [[ -f docs/ICML_PROGRESS.md ]]; then
  local_tick="$(parse_tick_file docs/ICML_PROGRESS.md)"
fi

tip_ok=0
blockers=()
if [[ -z "$local_tick" ]]; then
  blockers+=("docs/ICML_PROGRESS.md missing or has no Tick heading — cron likely booted from main")
elif [[ -n "$best_ref" ]] && [[ "$local_tick" -lt "$best_tick" ]]; then
  blockers+=("local Tick ${local_tick} behind remote tip Tick ${best_tick} (${best_ref})")
fi
if [[ ${#blockers[@]} -eq 0 ]] && [[ -n "$local_tick" ]]; then
  tip_ok=1
fi
# No remotes but local progress → OK for offline.
if [[ -z "$best_ref" ]] && [[ -n "$local_tick" ]]; then
  tip_ok=1
fi

echo "local_tick=${local_tick:-}"
echo "remote_tip_tick=${best_tick}"
echo "remote_tip_ref=${best_ref}"
echo "remote_tip_sha=${best_sha}"
echo "remote_tip_lineage_score=${best_score}"
echo "tip_ok_for_live=${tip_ok}"
for b in "${blockers[@]+"${blockers[@]}"}"; do
  echo "  BLOCK: $b"
done

if [[ "$APPLY" -eq 0 ]]; then
  if [[ -n "$best_ref" ]] && [[ "$tip_ok" -eq 0 ]]; then
    echo "Recover: bash scripts/icml_boot_recover.sh --apply"
    echo "  (or: git reset --hard ${best_ref})"
  fi
  if [[ "$tip_ok" -eq 1 ]] || [[ -n "$best_ref" ]]; then
    exit 0
  fi
  exit 1
fi

if [[ -z "$best_ref" ]]; then
  echo "No remote ICML tip found — cannot --apply" >&2
  exit 5
fi

dirty="$(git status --porcelain 2>/dev/null || true)"
if [[ -n "$dirty" ]]; then
  # Tick 286: preflight dirties gate/pipeline/secrets/tip reports — discard
  # those ephemerals so tip --apply is not stuck on a stale Tick.
  if command -v python3 >/dev/null 2>&1 && [[ -f scripts/icml_env_checks.py ]]; then
    if python3 - <<'PY'
import sys
sys.path.insert(0, "scripts")
from icml_env_checks import discard_ephemeral_icml_dirt
ok, detail = discard_ephemeral_icml_dirt()
print(detail)
raise SystemExit(0 if ok else 1)
PY
    then
      dirty="$(git status --porcelain 2>/dev/null || true)"
    else
      echo "Ephemeral discard failed or non-ephemeral dirt remains" >&2
    fi
  fi
fi
if [[ -n "$dirty" ]]; then
  echo "Working tree dirty — refuse --apply (commit/stash first):" >&2
  echo "$dirty" | head -20 >&2
  exit 3
fi

if [[ "$tip_ok" -eq 1 ]] && [[ "${local_tick}" == "${best_tick}" ]]; then
  echo "Already on tip Tick ${local_tick}; --apply is a no-op reset to ${best_ref}"
fi

git reset --hard "$best_ref"
echo "Recovered tip: HEAD now at ${best_ref}"
git log -1 --oneline

# Tick 339: tip PR anti-churn checkout after --apply.
# Tick 338 only auto-checkouts inside icml_cron_entry.sh. Chicken-egg
# `git show <tip>:…/icml_boot_recover.sh | bash -s -- --apply` still left
# HEAD on the greenfield boot branch name → new tip PR every cron when
# agents skipped cron_entry or committed before it. Checkout here so both
# recover paths land on tip_pr_commit_branch.
if [[ -f scripts/icml_checkout_tip_pr_branch.sh ]]; then
  _cur_branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  echo "tip_pr_anti_churn_checkout (boot_recover): attempting from ${_cur_branch}"
  if bash scripts/icml_checkout_tip_pr_branch.sh; then
    echo "tip_pr_anti_churn_checkout=ok branch=$(git rev-parse --abbrev-ref HEAD)"
  else
    echo "tip_pr_anti_churn_checkout=skip_or_fail (continuing on ${_cur_branch}; do NOT open a new tip PR)" >&2
  fi
  unset _cur_branch
fi
exit 0
