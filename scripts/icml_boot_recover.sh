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
# Chicken-egg from main (this script not present yet) — Tick 272 lineage pick
# (never committerdate-only; greenfield main branches can be newer than tip):
#   git fetch origin '+refs/heads/cursor/icml-epistemic-results-*:refs/remotes/origin/cursor/icml-epistemic-results-*'
#   TIP_REF=$(bash scripts/icml_pick_remote_tip.sh --require scripts/icml_boot_recover.sh)  # if picker present
#   # else: scan refs that contain this script + highest Tick (see AGENTS.md)
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
  git fetch origin \
    '+refs/heads/cursor/icml-epistemic-results-*:refs/remotes/origin/cursor/icml-epistemic-results-*' \
    '+refs/heads/cursor/icml-epistemic-evolution-*:refs/remotes/origin/cursor/icml-epistemic-evolution-*' \
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
  git for-each-ref --format='%(refname)' \
    'refs/remotes/origin/cursor/icml-epistemic-results-*' \
    'refs/remotes/origin/cursor/icml-epistemic-evolution-*' 2>/dev/null
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
exit 0
