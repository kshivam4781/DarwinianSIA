# ICML Thesis 1 — Human unblock (secrets)

**STATUS:** Live G2→G3→G4 is blocked on **`NEBIUS_API_KEY`** (+ HF/CSV).  
**Tick 289:** `ANTHROPIC_API_KEY` is **optional** while the default meta profile is
`kimi-nebius-pydantic-meta` (Nebius). Set `ICML_META_AGENT_PROFILE=default-meta`
only if you intentionally want Claude meta (then Anthropic becomes required again).

GPQA diamond needs **either** `HF_TOKEN` (+ dataset accept) **or** a local `gpqa_diamond.csv`.

Package install / uv / Portal Save are **not** required for live after Tick 265–267
(in-preflight Astral uv + `huggingface_hub` + `pydantic-ai` + SIA `PYTHONPATH` bootstrap).
Portal Save remains optional for warmer boots — see `docs/icml_portal_save_target.json`.

## What to add (required)

Add these **Cloud Agent / automation secrets** (never commit them; never paste into git):

| Secret | Why |
|--------|-----|
| `NEBIUS_API_KEY` | Target + meta/feedback (Kimi on Nebius; Tick 288–289) |
| `HF_TOKEN` | Download gated `Idavidrein/gpqa` for `--fetch-diamond` (**or** skip via CSV below) |
| `ANTHROPIC_API_KEY` | **Optional** under Tick 289 Nebius meta; required only with `default-meta` |

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
**Tick 273–304:** auto-live requires `fetch_diamond_ok` = `NEBIUS_API_KEY` + (`HF_TOKEN` **or** local diamond CSV); Anthropic optional under Tick 289 Nebius meta. Tick 304 sources `offline_bvd_case_study.py` CLI defaults from `icml_g3g4_live_shape()` and refuses divergent shape unless `--allow-shape-override` (closes hardcoded-default drift vs Tick 300–302 locks). Tick 303 wires recipe + offline Bvd locks into G3/G4 direct `--live` preflight (was pipeline-only). Tick 302 regenerates offline Figs 1–2 at live shape and locks `figures` in `docs/offline_bvd_summary.json` (Tick 300 left `figures: []`). Tick 301 extends that lock to paper/READY/Section12/case-study ID citations. Tick 300 re-pilots offline B vs D at exact live Nebius shape (`1890–1904`) and locks summary shape + gate3 offline table via `committed_offline_bvd_matches_live_shape` (preflight + `--live` refuse). Tick 299 enforces the Tick-298 recipe↔shape lock on pipeline preflight + `--live` refuse (no longer tests-only). Tick 298 locks committed gate3/4 + Section 21.7 recipes to `icml_g3g4_live_shape()` so shape changes cannot ship with stale pop3-like operator recipes (Tick 297 failure mode). Tick 297 syncs Section 21.7 + gate/pipeline reports to Tick 296 shape (stale pop3 recipes removed). Tick 296 cost-neutrally restores Nebius G3/G4 **pop4 × eval5 × max_gen6** (4×5×6=120 agent-evals) after offline showed Tick 295 **pop3** collapses PRIMARY/H5; G3/G4 max_gen hard cap raised to 6. Tick 295 cost-neutrally restored Nebius G3/G4 **max_gen=5** (eval10→8; 3×8×5=120 agent-evals) so PRIMARY gens30 is not truncated vs offline seed 22. Tick 294 floors Nebius G3/G4 `elite_count` at **2** (cost-neutral; Tick 293 elite=1 collapsed crossover to same-parent clones / H2). Tick 293 shrinks Nebius G3/G4 budget-fit shape with stack estimate **$19** so Tick 291 Kimi metering cannot mid-stack refuse/overrun the ~$20 ceiling. Tick 292 aligns cron/gate **human** Next/refuse strings with that (no hard `ANTHROPIC + NEBIUS` demand). Tick 291 meters Nebius Kimi USD ($0.95/$4.00 per 1M) + token→USD budget reconcile (meta overhead 3.0) so live spend is not under-counted. Tick 290 merges GPQA `submission.json` tokens/USD into subset `results.json` (PRIMARY cost + budget reconcile). Tick 288 wires `--target-agent-profile kimi-nebius-target` into G2/G3/G4 and retargets the GPQA reference from Tinker→Nebius/Kimi (Section 6.8 latent abort). Tick 287 fixed a latent host abort: GPQA `--eval_subset` no longer imports pandas at module load (G2 dry-run `run_1852` green on system Python without host pandas). Tick 278 also auto-wires that CSV inside G2/G3/G4/pipeline when `--fetch-diamond` is set (cron flag optional). Tick 279 prefers `uv pip install` for runtime deps on pip-less interpreters. Tick 280 installs those packages into the **user site** (`uv pip --target`), so read-only system Pythons no longer Permission-deny `runtime_deps`. Tick 281 also puts that user site on **`PYTHONPATH`** so `PYTHONNOUSERSITE` / venv children still import `huggingface_hub` for `--fetch-diamond`. Tick 282 runs that bootstrap **before** HF materialize (`ensure_deps_before_diamond_fetch`) so cold boots do not ImportError ahead of install. Tick 283 reconciles live stack spend from actual run `total_cost_usd` (× meta overhead) so G4 is not refused/overrun under the ~$20 ceiling. Tick 284 persists that spend to `docs/icml_budget_spent.json` and **resumes** mid-stack (skips completed G2/G3/G4 run IDs). Tick 285 **stops gitignoring** that ledger and trusts it cross-VM when `runs/` are absent (commit the ledger with the tip after live gates). Tick 286 **discards ephemeral preflight dirt** before tip `--apply` and ships a **zero** committed ledger so recover cannot stick on a stale Tick.

Machine-readable tip check: `docs/icml_tip_status.json` (pipeline refuses
`--live` if local Tick lags remote tip / `ICML_PROGRESS` is missing).

Do **not** set `ICML_READY` STATUS: READY from offline pilots alone.
