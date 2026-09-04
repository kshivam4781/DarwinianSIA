# Agent guide — SIA-CABS / DarwinianSIA

## Start here (required)

Before planning, coding, or running commands, read:

**[`docs/HACKATHON_MASTER_PLAN.md`](docs/HACKATHON_MASTER_PLAN.md)**

That document is the single source of truth for CABS architecture, APIs, hardware, blockers, phases, budgets, and run commands. **Section 21** is the ICML Thesis 1 epistemic-evolution protocol (persistent agent). Sections 18–20 cover Darwinian merge contracts.

## ICML persistent agent (cron / cloud)

Automation ticks often boot a **fresh branch from `main`** without `docs/ICML_*` or live runners.
**Tick 327:** `main` still has hackathon-era AGENTS (no ICML tip files) until the tip PR is merged — recover tip every boot; ask human to merge tip → `main` + add secrets (`docs/ICML_HUMAN_UNBLOCK.md`).
**Tick 328:** machine-readable `docs/icml_secrets_status.json` / tip status / pipeline Next also surface merge tip→main via `main_has_icml_tip` (does not gate paid live).
**Tick 330:** `human_next` includes the concrete tip PR URL (`tip_pr_url`) so operators do not guess among 300+ draft tip PRs.
**Tick 331:** tip pickers also scan `cursor/bc-*` cloud cron branches (not only `icml-epistemic-results-*`).
**Tick 332:** `ICML_HUMAN_UNBLOCK.md` chicken-egg recipe (+ script-header recipes) also fetch/scan `cursor/bc-*` (Tick 331 fixed pickers/AGENTS only).
**Live secrets (Tick 289+):** `NEBIUS_API_KEY` + (`HF_TOKEN` **or** local `gpqa_diamond.csv`). `ANTHROPIC_API_KEY` is **optional** under default Nebius pydantic-ai meta. See `docs/ICML_HUMAN_UNBLOCK.md`. Load local `.env` with `source scripts/load_env.sh` (Linux/cloud) or `. .\scripts\load_env.ps1` (Windows).

1. If `docs/ICML_READY.md` says **STATUS: READY** → stop (already complete).
2. Run the **single cron entry** (Tick 271/272) — tip recover + secrets gate + live or preflight:

```bash
# Preferred once tip tree exists:
bash scripts/icml_cron_entry.sh

# Chicken-egg from main (entry script absent) — Tick 272 lineage pick
# (never committerdate-only: greenfield main branches can be newer than tip).
# Tick 331: also scan cursor/bc-* cloud cron boots.
git fetch origin \
  '+refs/heads/cursor/icml-epistemic-results-*:refs/remotes/origin/cursor/icml-epistemic-results-*' \
  '+refs/heads/cursor/bc-*:refs/remotes/origin/cursor/bc-*'
TIP_REF=""
BEST_TICK=-1
TMP=$(mktemp -d)
while IFS= read -r ref; do
  git cat-file -e "${ref}:scripts/icml_cron_entry.sh" 2>/dev/null || continue
  git show "${ref}:docs/ICML_PROGRESS.md" >"$TMP/p" 2>/dev/null || continue
  tick=$(grep -oE 'Tick[[:space:]]+[0-9]+' "$TMP/p" | head -1 | grep -oE '[0-9]+' || true)
  [[ -z "$tick" ]] && continue
  if [[ "$tick" -gt "$BEST_TICK" ]]; then BEST_TICK=$tick; TIP_REF=$ref; fi
done < <(git for-each-ref --format='%(refname)' \
  'refs/remotes/origin/cursor/icml-epistemic-results-*' \
  'refs/remotes/origin/cursor/bc-*')
rm -rf "$TMP"
git show "${TIP_REF}:scripts/icml_cron_entry.sh" | bash -s --
```

`icml_cron_entry.sh` recovers tip (lineage-aware; `scripts/icml_pick_remote_tip.sh`), writes `docs/icml_tip_status.json` + `docs/icml_secrets_status.json`, then either runs `run_icml_live_pipeline.py --live --fetch-diamond` (when secrets present) or preflight-only.

3. Follow Section 21 + `docs/ICML_PROGRESS.md` / `docs/ICML_HUMAN_UNBLOCK.md` for diagnosis if entry exits without READY.
4. Never set READY from offline / preflight alone. Do not re-trigger Portal Save every tick.

## Two-repo layout (this monorepo)

| Area | Path | Build |
|------|------|-------|
| **CABS** | `cabs/`, `sia_cabs/` | Beliefs, contradictions, Tavily, committee |
| **Darwinian** | `SIA/` | Population evolution, DNA, `civilization.json` |

## Quick rules

1. **Phase order is mandatory:** 0 → 1 → 2 → 3 (hackathon). ICML: G0 → G5 per Section 21.5.
2. **Money:** Do not run GPQA/LawBench without checking API keys and budget (Section 8 / 21.6). Never run full LawBench without user approval. ~$20 ICML ceiling unless docs raise it.
3. **Hardware:** Local GPU unused. Inference via Nebius API; orchestration on CPU.
4. **Run IDs:** Must be **integers**; never overwrite existing runs.
5. **Scope:** No `--focus weights` / RL mode. Prefer `--no-web` for long runs. No parallel full GPQA jobs.
6. **Status:** After work, update Section 12 + `docs/ICML_PROGRESS.md` + `docs/ICML_READY.md`.

## Project summary

- **What:** SIA-CABS — Contradiction-Aware Belief System + Darwinian epistemic steering (Condition D)
- **Winning thesis:** Belief → Contradiction → Research question → Biased mutation / scoped feedback → Better sample efficiency than fitness-only Darwinian
- **CLI:** `sia` / `sia-cabs` / `sia-cabs-tools`; live: `scripts/run_icml_live_pipeline.py`
