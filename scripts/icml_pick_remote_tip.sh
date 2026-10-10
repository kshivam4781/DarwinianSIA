#!/usr/bin/env bash
# ICML Tip 272 / 331 — lineage-aware remote tip picker (no apply).
#
# Greenfield cron branches from main can have a newer committerdate than the
# real tip but lack ICML scripts. Date-only `for-each-ref | head -1` then
# breaks chicken-egg `git show <tip>:scripts/icml_cron_entry.sh`.
#
# This helper scans remote ICML refs, keeps only those that contain a required
# blob (default: scripts/icml_cron_entry.sh), scores Tick + secrets-first
# lineage, and prints the winning ref on stdout.
# Tick 331: also scans cursor/bc-* cloud cron boot branches.
#
# Usage:
#   bash scripts/icml_pick_remote_tip.sh
#   bash scripts/icml_pick_remote_tip.sh --fetch
#   bash scripts/icml_pick_remote_tip.sh --require scripts/icml_boot_recover.sh
#   TIP_REF=$(bash scripts/icml_pick_remote_tip.sh)
#
# Chicken-egg (this file absent on main):
#   Prefer `git show <known-tip>:scripts/icml_cron_entry.sh | bash` after a
#   lineage scan inlined in AGENTS.md / ICML_HUMAN_UNBLOCK.md (Tick 272).

set -euo pipefail

FETCH=0
REQUIRE="scripts/icml_cron_entry.sh"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --fetch) FETCH=1 ;;
    --require)
      shift
      REQUIRE="${1:-}"
      if [[ -z "$REQUIRE" ]]; then
        echo "--require needs a blob path" >&2
        exit 2
      fi
      ;;
    -h|--help)
      sed -n '2,24p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $1 (want --fetch / --require PATH)" >&2
      exit 2
      ;;
  esac
  shift
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
  file_has 'icml_cron_entry' "$file" && score=$((score + 1)) || true
  echo "$score"
}

parse_tick_file() {
  local file="$1"
  grep -oE 'Tick[[:space:]]+[0-9]+' "$file" 2>/dev/null | head -1 | grep -oE '[0-9]+' || true
}

best_tick=-1
best_score=-1
best_ref=""

TMPDIR_PICK="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_PICK"' EXIT

while IFS= read -r ref; do
  [[ -z "$ref" ]] && continue
  if ! git cat-file -e "${ref}:${REQUIRE}" 2>/dev/null; then
    continue
  fi
  prog="${TMPDIR_PICK}/progress.txt"
  if ! git show "${ref}:docs/ICML_PROGRESS.md" >"$prog" 2>/dev/null; then
    continue
  fi
  [[ -s "$prog" ]] || continue
  tick="$(parse_tick_file "$prog")"
  [[ -z "$tick" ]] && continue
  score="$(score_lineage_file "$prog")"
  if [[ "$tick" -gt "$best_tick" ]] || \
     { [[ "$tick" -eq "$best_tick" ]] && [[ "$score" -gt "$best_score" ]]; }; then
    best_tick="$tick"
    best_score="$score"
    best_ref="$ref"
  fi
done < <(
  # Tick 331: include cursor/bc-* cloud cron boots (require blob filters junk).
  git for-each-ref --format='%(refname)' \
    'refs/remotes/origin/cursor/icml-epistemic-results-*' \
    'refs/remotes/origin/cursor/icml-epistemic-evolution-*' \
    'refs/remotes/origin/cursor/bc-*' 2>/dev/null
)

if [[ -z "$best_ref" ]]; then
  echo "No remote ICML tip with ${REQUIRE} + ICML_PROGRESS Tick" >&2
  exit 5
fi

echo "$best_ref"
