#!/usr/bin/env bash
# ICML Thesis 1 — single cron entry (Tick 271–278 / 329).
#
# Cron often boots from main without ICML tip docs. This entry:
#   1. Recovers the highest-Tick tip (chicken-egg safe)
#   2. Writes tip + secrets status (presence only; loads .env for missing keys)
#   3. If tip OK + fetch_diamond_ok (API keys + HF **or** local diamond CSV)
#      → live G2→G3→G4 (--fetch-diamond [, --diamond-csv])
#   4. Else → preflight only WITH --fetch-diamond (Tick 276) and optional
#      --diamond-csv (Tick 277); print *full* human_next (Tick 329 dual
#      unblock: merge tip→main + secrets); exit 0 (not READY)
#
# Tick 273: do NOT launch --fetch-diamond live on anthropic+nebius alone —
# missing HF_TOKEN would fail diamond materialization after tip recover.
# Tick 276: preflight also passes --fetch-diamond so gate2/3/4 reports require HF.
# Tick 277: load gitignored .env; auto-detect local gpqa_diamond.csv and pass
# --diamond-csv so HF is optional when a real CSV is present.
# Tick 278: G2/G3/G4/pipeline also autowire the same CSV under --fetch-diamond
# (cron --diamond-csv remains belt-and-suspenders).
#
# Preferred once tip tree exists:
#   bash scripts/icml_cron_entry.sh
#   bash scripts/icml_cron_entry.sh --preflight-only
#   bash scripts/icml_cron_entry.sh --live   # forces live attempt (still refuses without secrets)
#
# Chicken-egg from main (this script not present yet) — Tick 272 lineage pick
# (do NOT use committerdate-only head -1; greenfield main branches are newer):
#   git fetch origin '+refs/heads/cursor/icml-epistemic-results-*:refs/remotes/origin/cursor/icml-epistemic-results-*'
#   TIP_REF=$(bash scripts/icml_pick_remote_tip.sh 2>/dev/null)  # if already recovered
#   # else inline: see AGENTS.md / docs/ICML_HUMAN_UNBLOCK.md Tick 272 recipe
#   git show "${TIP_REF}:scripts/icml_cron_entry.sh" | bash -s --

set -euo pipefail

MODE="auto"  # auto | preflight | live
for arg in "$@"; do
  case "$arg" in
    --preflight-only) MODE="preflight" ;;
    --live) MODE="live" ;;
    -h|--help)
      sed -n '2,28p' "$0"
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

echo "=== ICML cron entry (Tick 271–273) mode=${MODE} ==="

# --- Tip recover (chicken-egg) -------------------------------------------------
# Tick 272: pick tip by highest Tick + lineage among refs that actually contain
# boot_recover / cron_entry — never committerdate-only (greenfield main traps).
_pick_tip_ref() {
  local require="${1:-scripts/icml_boot_recover.sh}"
  if [[ -f scripts/icml_pick_remote_tip.sh ]]; then
    bash scripts/icml_pick_remote_tip.sh --require "$require" 2>/dev/null || true
    return 0
  fi
  # Inline fallback (picker script itself missing on main).
  local best_tick=-1 best_score=-1 best_ref="" ref prog tick score
  local tmp
  tmp="$(mktemp -d)"
  while IFS= read -r ref; do
    [[ -z "$ref" ]] && continue
    git cat-file -e "${ref}:${require}" 2>/dev/null || continue
    prog="${tmp}/progress.txt"
    git show "${ref}:docs/ICML_PROGRESS.md" >"$prog" 2>/dev/null || continue
    [[ -s "$prog" ]] || continue
    tick="$(grep -oE 'Tick[[:space:]]+[0-9]+' "$prog" 2>/dev/null | head -1 | grep -oE '[0-9]+' || true)"
    [[ -z "$tick" ]] && continue
    score=0
    grep -qi 'secrets-first' "$prog" 2>/dev/null && score=$((score + 1)) || true
    grep -qi 'ensure_uv_on_path' "$prog" 2>/dev/null && score=$((score + 1)) || true
    grep -qi 'icml_cron_entry' "$prog" 2>/dev/null && score=$((score + 1)) || true
    if [[ "$tick" -gt "$best_tick" ]] || \
       { [[ "$tick" -eq "$best_tick" ]] && [[ "$score" -gt "$best_score" ]]; }; then
      best_tick="$tick"
      best_score="$score"
      best_ref="$ref"
    fi
  done < <(
    git for-each-ref --format='%(refname)' \
      'refs/remotes/origin/cursor/icml-epistemic-results-*' \
      'refs/remotes/origin/cursor/icml-epistemic-evolution-*' 2>/dev/null
  )
  rm -rf "$tmp"
  echo "$best_ref"
}

recover_tip() {
  if [[ -f scripts/icml_boot_recover.sh ]]; then
    bash scripts/icml_boot_recover.sh --fetch --apply
    return $?
  fi
  echo "scripts/icml_boot_recover.sh missing — chicken-egg fetch from tip (Tick 272 lineage)"
  git fetch origin \
    '+refs/heads/cursor/icml-epistemic-results-*:refs/remotes/origin/cursor/icml-epistemic-results-*' \
    '+refs/heads/cursor/icml-epistemic-evolution-*:refs/remotes/origin/cursor/icml-epistemic-evolution-*' \
    2>/dev/null || git fetch origin --prune 2>/dev/null || true
  local tip_ref
  tip_ref="$(_pick_tip_ref scripts/icml_boot_recover.sh)"
  if [[ -z "${tip_ref}" ]]; then
    tip_ref="$(_pick_tip_ref scripts/icml_cron_entry.sh)"
  fi
  if [[ -z "${tip_ref}" ]]; then
    echo "No remote ICML tip with recover scripts — cannot recover" >&2
    return 5
  fi
  echo "Chicken-egg tip_ref=${tip_ref}"
  # Prefer tip's lineage-aware recoverer over hard-reset.
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
    # Tick 286: discard preflight-only dirt before refusing tip apply.
    if command -v python3 >/dev/null 2>&1 && [[ -f scripts/icml_env_checks.py ]]; then
      python3 - <<'PY' || true
import sys
sys.path.insert(0, "scripts")
from icml_env_checks import discard_ephemeral_icml_dirt
ok, detail = discard_ephemeral_icml_dirt()
print(f"ephemeral_discard: ok={ok} {detail}")
raise SystemExit(0 if ok else 1)
PY
    fi
  fi
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
from icml_env_checks import (
    write_icml_secrets_status,
    write_icml_tip_status,
    ensure_budget_spent_ledger_initialized,
)
root = Path(".").resolve()
tip = write_icml_tip_status(root / "docs" / "icml_tip_status.json", fetch=False)
sec = write_icml_secrets_status(root / "docs" / "icml_secrets_status.json")
ledger_path, ledger_created = ensure_budget_spent_ledger_initialized(root)
print(f"tip_ok_for_live={tip.get('tip_ok_for_live')} local_tick={tip.get('local_tick')}")
print(
    "secrets_ok_for_paid_sia="
    f"{sec.get('secrets_ok_for_paid_sia')} "
    f"fetch_diamond_ok={sec.get('fetch_diamond_ok')} "
    f"anthropic={sec.get('anthropic_key_present')} "
    f"nebius={sec.get('nebius_key_present')} "
    f"hf={sec.get('hf_token_present')} "
    f"diamond_csv={sec.get('diamond_csv_present')}"
)
if sec.get("diamond_csv_path"):
    print(f"diamond_csv_path={sec.get('diamond_csv_path')}")
print(f"budget_ledger={ledger_path} created={ledger_created}")
PY
fi

SECRETS_OK=0
if [[ -f docs/icml_secrets_status.json ]] && grep -q '"secrets_ok_for_paid_sia": true' docs/icml_secrets_status.json; then
  SECRETS_OK=1
fi
# Tick 273/277: cron --fetch-diamond needs HF **or** local diamond CSV.
FETCH_DIAMOND_OK=0
if [[ -f docs/icml_secrets_status.json ]] && grep -q '"fetch_diamond_ok": true' docs/icml_secrets_status.json; then
  FETCH_DIAMOND_OK=1
fi
TIP_OK=0
if [[ -f docs/icml_tip_status.json ]] && grep -q '"tip_ok_for_live": true' docs/icml_tip_status.json; then
  TIP_OK=1
fi
CRON_LIVE_OK=0
if [[ -f docs/icml_secrets_status.json ]] && grep -q '"cron_live_ok": true' docs/icml_secrets_status.json; then
  CRON_LIVE_OK=1
elif [[ "$SECRETS_OK" -eq 1 && "$FETCH_DIAMOND_OK" -eq 1 ]]; then
  CRON_LIVE_OK=1
fi

# Tick 277: optional local CSV path from secrets status (never commit the CSV).
DIAMOND_CSV=""
if [[ -f docs/icml_secrets_status.json ]]; then
  DIAMOND_CSV="$(python3 - <<'PY'
import json
from pathlib import Path
p = Path("docs/icml_secrets_status.json")
try:
    data = json.loads(p.read_text(encoding="utf-8"))
except Exception:
    print("")
else:
    path = data.get("diamond_csv_path") or ""
    print(path if data.get("diamond_csv_present") else "")
PY
)"
fi

_pipeline_diamond_args() {
  # Always --fetch-diamond (Tick 276); add --diamond-csv when present (Tick 277).
  local args=(--fetch-diamond)
  if [[ -n "${DIAMOND_CSV}" && -f "${DIAMOND_CSV}" ]]; then
    args+=(--diamond-csv "${DIAMOND_CSV}")
  fi
  printf '%s\n' "${args[@]}"
}

run_preflight() {
  echo "=== Preflight (no paid spend; --fetch-diamond to match live) ==="
  if [[ -f scripts/run_icml_live_pipeline.py ]]; then
    # Tick 276/277: same diamond args as live so gate reports match intent.
    mapfile -t _dargs < <(_pipeline_diamond_args)
    python3 scripts/run_icml_live_pipeline.py --preflight-only "${_dargs[@]}" || true
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
  mapfile -t _dargs < <(_pipeline_diamond_args)
  python3 scripts/run_icml_live_pipeline.py --live "${_dargs[@]}"
}

# Tick 329: print *all* human_next lines on blocked paths (not only auto /
# not only lines[0]). Tick 328 put merge tip→main first in human_next when
# main lacks tip; --preflight-only / live-refuse previously stayed silent.
print_human_next() {
  if [[ -f docs/icml_secrets_status.json ]]; then
    python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("docs/icml_secrets_status.json").read_text(encoding="utf-8"))
lines = data.get("human_next") or []
if lines:
    print("=== Human next (dual unblock) ===")
    for i, line in enumerate(lines, 1):
        print(f"  {i}. {line}")
else:
    print(
        "Human: add NEBIUS_API_KEY + (HF_TOKEN or local gpqa_diamond.csv) "
        "per docs/ICML_HUMAN_UNBLOCK.md (ANTHROPIC optional under Nebius meta)"
    )
PY
  else
    echo "Human: add NEBIUS_API_KEY + (HF_TOKEN or local gpqa_diamond.csv) per docs/ICML_HUMAN_UNBLOCK.md (ANTHROPIC optional under Nebius meta)"
  fi
}

case "$MODE" in
  preflight)
    # Tick 329: surface dual unblock even on --preflight-only (no paid spend).
    print_human_next
    run_preflight
    exit 0
    ;;
  live)
    if [[ "$TIP_OK" -ne 1 ]]; then
      echo "Refusing --live: tip not OK (see docs/icml_tip_status.json)" >&2
      print_human_next
      run_preflight
      exit 3
    fi
    if [[ "$CRON_LIVE_OK" -ne 1 ]]; then
      echo "Refusing --live: need API keys + (HF_TOKEN or local diamond CSV) for --fetch-diamond (see docs/ICML_HUMAN_UNBLOCK.md)" >&2
      echo "  secrets_ok_for_paid_sia=${SECRETS_OK} fetch_diamond_ok=${FETCH_DIAMOND_OK} diamond_csv=${DIAMOND_CSV:-none}" >&2
      print_human_next
      run_preflight
      exit 4
    fi
    run_live
    exit $?
    ;;
  auto)
    if [[ "$TIP_OK" -eq 1 && "$CRON_LIVE_OK" -eq 1 ]]; then
      run_live
      exit $?
    fi
    echo "Auto: blockers remain (tip_ok=${TIP_OK} secrets_ok=${SECRETS_OK} fetch_diamond_ok=${FETCH_DIAMOND_OK}) — preflight only"
    # Tick 292/329: Anthropic-optional human_next from secrets status (full list).
    print_human_next
    run_preflight
    exit 0
    ;;
esac
