#!/usr/bin/env bash
# ICML Thesis 1 — single cron entry (Tick 271).
#
# Cron often boots from main without ICML tip docs. This entry:
#   1. Recovers the highest-Tick tip (chicken-egg safe)
#   2. Writes tip + secrets status (presence only)
#   3. If secrets + tip OK → live G2→G3→G4 (--fetch-diamond)
#   4. Else → preflight only; print blockers; exit 0 (not READY)
#
# Preferred once tip tree exists:
#   bash scripts/icml_cron_entry.sh
#   bash scripts/icml_cron_entry.sh --preflight-only
#   bash scripts/icml_cron_entry.sh --live   # forces live attempt (still refuses without secrets)
#
# Chicken-egg from main (this script not present yet):
#   git fetch origin '+refs/heads/cursor/icml-epistemic-results-*:refs/remotes/origin/cursor/icml-epistemic-results-*'
#   TIP_REF=$(git for-each-ref --format='%(refname)' --sort=-committerdate \
#     'refs/remotes/origin/cursor/icml-epistemic-results-*' | head -1)
#   git show "${TIP_REF}:scripts/icml_cron_entry.sh" | bash -s --

set -euo pipefail

MODE="auto"  # auto | preflight | live
for arg in "$@"; do
  case "$arg" in
    --preflight-only) MODE="preflight" ;;
    --live) MODE="live" ;;
    -h|--help)
      sed -n '2,24p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $arg (want --preflight-only / --live)" >&2
      exit 2
      ;;
  esac
done

# Resolve repo root even when piped via `git show … | bash`.
if ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  cd "$ROOT"
else
  echo "Not inside a git repo" >&2
  exit 2
fi

echo "=== ICML cron entry (Tick 271) mode=${MODE} ==="

# --- Tip recover (chicken-egg) -------------------------------------------------
recover_tip() {
  if [[ -f scripts/icml_boot_recover.sh ]]; then
    bash scripts/icml_boot_recover.sh --fetch --apply
    return $?
  fi
  echo "scripts/icml_boot_recover.sh missing — chicken-egg fetch from tip"
  git fetch origin \
    '+refs/heads/cursor/icml-epistemic-results-*:refs/remotes/origin/cursor/icml-epistemic-results-*' \
    '+refs/heads/cursor/icml-epistemic-evolution-*:refs/remotes/origin/cursor/icml-epistemic-evolution-*' \
    2>/dev/null || git fetch origin --prune 2>/dev/null || true
  local tip_ref
  tip_ref="$(
    git for-each-ref --format='%(refname)' --sort=-committerdate \
      'refs/remotes/origin/cursor/icml-epistemic-results-*' \
      'refs/remotes/origin/cursor/icml-epistemic-evolution-*' 2>/dev/null | head -1
  )"
  if [[ -z "${tip_ref}" ]]; then
    echo "No remote ICML tip found — cannot recover" >&2
    return 5
  fi
  # Prefer tip's lineage-aware recoverer over date-only checkout.
  if git cat-file -e "${tip_ref}:scripts/icml_boot_recover.sh" 2>/dev/null; then
    git show "${tip_ref}:scripts/icml_boot_recover.sh" | bash -s -- --apply
    return $?
  fi
  echo "Tip lacks boot_recover — hard-reset to ${tip_ref}"
  git reset --hard "${tip_ref}"
}

# Only apply when progress missing / lagging (avoid clobbering in-progress edits).
need_recover=0
if [[ ! -f docs/ICML_PROGRESS.md ]]; then
  need_recover=1
elif [[ -f scripts/icml_boot_recover.sh ]]; then
  # Non-apply status check: tip_ok_for_live=0 → recover.
  status_out="$(bash scripts/icml_boot_recover.sh --fetch 2>/dev/null || true)"
  echo "$status_out"
  # Avoid `printf|grep -q` under pipefail (SIGPIPE); use case match.
  case "$status_out" in
    *tip_ok_for_live=0*) need_recover=1 ;;
  esac
else
  need_recover=1
fi

if [[ "$need_recover" -eq 1 ]]; then
  if [[ -n "$(git status --porcelain 2>/dev/null || true)" ]]; then
    echo "Working tree dirty — skip tip --apply; commit/stash first or recover manually" >&2
    echo "Dirty paths:" >&2
    git status --porcelain | head -20 >&2
  else
    recover_tip
    # Re-enter this script from tip tree when we were piped from git show.
    if [[ -f scripts/icml_cron_entry.sh ]] && [[ "${ICML_CRON_REEXEC:-0}" != "1" ]]; then
      export ICML_CRON_REEXEC=1
      exec bash scripts/icml_cron_entry.sh "$@"
    fi
  fi
fi

# --- Status (presence only) ----------------------------------------------------
if command -v python3 >/dev/null 2>&1 && [[ -f scripts/icml_env_checks.py ]]; then
  python3 - <<'PY'
from pathlib import Path
import sys
sys.path.insert(0, "scripts")
from icml_env_checks import write_icml_secrets_status, write_icml_tip_status
root = Path(".").resolve()
tip = write_icml_tip_status(root / "docs" / "icml_tip_status.json", fetch=False)
sec = write_icml_secrets_status(root / "docs" / "icml_secrets_status.json")
print(f"tip_ok_for_live={tip.get('tip_ok_for_live')} local_tick={tip.get('local_tick')}")
print(
    "secrets_ok_for_paid_sia="
    f"{sec.get('secrets_ok_for_paid_sia')} "
    f"anthropic={sec.get('anthropic_key_present')} "
    f"nebius={sec.get('nebius_key_present')} "
    f"hf={sec.get('hf_token_present')}"
)
PY
fi

SECRETS_OK=0
if [[ -f docs/icml_secrets_status.json ]] && grep -q '"secrets_ok_for_paid_sia": true' docs/icml_secrets_status.json; then
  SECRETS_OK=1
fi
TIP_OK=0
if [[ -f docs/icml_tip_status.json ]] && grep -q '"tip_ok_for_live": true' docs/icml_tip_status.json; then
  TIP_OK=1
fi

run_preflight() {
  echo "=== Preflight (no paid spend) ==="
  if [[ -f scripts/run_icml_live_pipeline.py ]]; then
    python3 scripts/run_icml_live_pipeline.py --preflight-only || true
  else
    echo "run_icml_live_pipeline.py missing — tip recover incomplete" >&2
    return 1
  fi
}

run_live() {
  echo "=== Live G2→G3→G4 (--fetch-diamond) ==="
  if [[ ! -f scripts/run_icml_live_pipeline.py ]]; then
    echo "run_icml_live_pipeline.py missing — tip recover incomplete" >&2
    return 1
  fi
  python3 scripts/run_icml_live_pipeline.py --live --fetch-diamond
}

case "$MODE" in
  preflight)
    run_preflight
    exit 0
    ;;
  live)
    if [[ "$TIP_OK" -ne 1 ]]; then
      echo "Refusing --live: tip not OK (see docs/icml_tip_status.json)" >&2
      run_preflight
      exit 3
    fi
    if [[ "$SECRETS_OK" -ne 1 ]]; then
      echo "Refusing --live: secrets missing (see docs/ICML_HUMAN_UNBLOCK.md)" >&2
      run_preflight
      exit 4
    fi
    run_live
    exit $?
    ;;
  auto)
    if [[ "$TIP_OK" -eq 1 && "$SECRETS_OK" -eq 1 ]]; then
      run_live
      exit $?
    fi
    echo "Auto: blockers remain (tip_ok=${TIP_OK} secrets_ok=${SECRETS_OK}) — preflight only"
    echo "Human: add secrets per docs/ICML_HUMAN_UNBLOCK.md; accept HF Idavidrein/gpqa"
    run_preflight
    exit 0
    ;;
esac
