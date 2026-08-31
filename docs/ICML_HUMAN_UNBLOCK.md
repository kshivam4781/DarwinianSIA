# ICML Thesis 1 — Human unblock (secrets)

**STATUS:** Live G2→G3→G4 is blocked on **API secrets** (Anthropic + Nebius).  
GPQA diamond needs **either** `HF_TOKEN` (+ dataset accept) **or** a local `gpqa_diamond.csv`.

Package install / uv / Portal Save are **not** required for live after Tick 265–267
(in-preflight Astral uv + `huggingface_hub` + SIA `PYTHONPATH` bootstrap).
Portal Save remains optional for warmer boots — see `docs/icml_portal_save_target.json`.

## What to add (required)

Add these **Cloud Agent / automation secrets** (never commit them; never paste into git):

| Secret | Why |
|--------|-----|
| `ANTHROPIC_API_KEY` | Meta + feedback agents (Claude) |
| `NEBIUS_API_KEY` | Target agent inference |
| `HF_TOKEN` | Download gated `Idavidrein/gpqa` for `--fetch-diamond` (**or** skip via CSV below) |

Also (if using HF): accept the HuggingFace dataset **`Idavidrein/gpqa`** while logged in as the token owner.

### Optional: local diamond CSV (Tick 277 — skips HF)

If you already have `gpqa_diamond.csv`, drop it at one of:

- `/tmp/gpqa_diamond.csv`
- `docs/private/gpqa_diamond.csv` (gitignored)
- path in `$ICML_DIAMOND_CSV` / `$SIA_DIAMOND_CSV`

Cron auto-detects it, sets `diamond_csv_present` in `docs/icml_secrets_status.json`, and passes `--diamond-csv` so `HF_TOKEN` is not required.

You may also put API keys in a gitignored repo-root `.env` (Tick 277 loads missing names into the process env; values are never logged).

## Where to add them

1. Automation: https://cursor.com/automations/bf73dff3-8f7a-11f1-a7d1-d6b4613131ce  
   → Secrets / environment attached to this automation (preferred so every cron tick inherits them).
2. Or linked env dashboard: https://cursor.com/dashboard/cloud-agents/environments/e/31d13f14-9d04-11f1-a7d1-d6b4613131ce

Machine-readable presence check (no values): `docs/icml_secrets_status.json`  
(rewritten each pipeline preflight / Tick 268+).

## After secrets land

Next automation cron (or a manual agent) should run the **single entry** (Tick 271/272):

```bash
# Preferred once tip tree exists:
bash scripts/icml_cron_entry.sh

# Chicken-egg from main (scripts absent) — Tick 272 lineage pick
# (never committerdate-only; greenfield main branches can outdate the tip):
git fetch origin '+refs/heads/cursor/icml-epistemic-results-*:refs/remotes/origin/cursor/icml-epistemic-results-*'
TIP_REF=""
BEST_TICK=-1
TMP=$(mktemp -d)
while IFS= read -r ref; do
  git cat-file -e "${ref}:scripts/icml_cron_entry.sh" 2>/dev/null || continue
  git show "${ref}:docs/ICML_PROGRESS.md" >"$TMP/p" 2>/dev/null || continue
  tick=$(grep -oE 'Tick[[:space:]]+[0-9]+' "$TMP/p" | head -1 | grep -oE '[0-9]+' || true)
  [[ -z "$tick" ]] && continue
  if [[ "$tick" -gt "$BEST_TICK" ]]; then BEST_TICK=$tick; TIP_REF=$ref; fi
done < <(git for-each-ref --format='%(refname)' 'refs/remotes/origin/cursor/icml-epistemic-results-*')
rm -rf "$TMP"
git show "${TIP_REF}:scripts/icml_cron_entry.sh" | bash -s --
```

That recovers tip (lineage-aware via `icml_pick_remote_tip.sh` / boot recover), then chains G2 → G3 → G4 serially under the ~$20 budget ceiling
and refreshes `docs/paper_artifacts.md` / `docs/ICML_READY.md` when criteria pass.
Without secrets it stops at preflight (no paid spend).
**Tick 273–287:** auto-live requires `fetch_diamond_ok` = API keys + (`HF_TOKEN` **or** local diamond CSV). Tick 287 fixed a latent host abort: GPQA `--eval_subset` no longer imports pandas at module load (G2 dry-run `run_1852` green on system Python without host pandas). Tick 278 also auto-wires that CSV inside G2/G3/G4/pipeline when `--fetch-diamond` is set (cron flag optional). Tick 279 prefers `uv pip install` for runtime deps on pip-less interpreters. Tick 280 installs those packages into the **user site** (`uv pip --target`), so read-only system Pythons no longer Permission-deny `runtime_deps`. Tick 281 also puts that user site on **`PYTHONPATH`** so `PYTHONNOUSERSITE` / venv children still import `huggingface_hub` for `--fetch-diamond`. Tick 282 runs that bootstrap **before** HF materialize (`ensure_deps_before_diamond_fetch`) so cold boots do not ImportError ahead of install. Tick 283 reconciles live stack spend from actual run `total_cost_usd` (× meta overhead) so G4 is not refused/overrun under the ~$20 ceiling. Tick 284 persists that spend to `docs/icml_budget_spent.json` and **resumes** mid-stack (skips completed G2/G3/G4 run IDs). Tick 285 **stops gitignoring** that ledger and trusts it cross-VM when `runs/` are absent (commit the ledger with the tip after live gates). Tick 286 **discards ephemeral preflight dirt** before tip `--apply` and ships a **zero** committed ledger so recover cannot stick on a stale Tick.

Machine-readable tip check: `docs/icml_tip_status.json` (pipeline refuses
`--live` if local Tick lags remote tip / `ICML_PROGRESS` is missing).

Do **not** set `ICML_READY` STATUS: READY from offline pilots alone.
