# Agent guide — SIA-CABS / DarwinianSIA

## Start here (required)

Before planning, coding, or running commands, read:

**[`docs/HACKATHON_MASTER_PLAN.md`](docs/HACKATHON_MASTER_PLAN.md)**

That document is the single source of truth for CABS architecture, APIs, hardware, blockers, phases, budgets, and run commands. **Section 21** is the ICML Thesis 1 epistemic-evolution protocol (persistent agent). Sections 18–20 cover Darwinian merge contracts.

## ICML persistent agent (cron / cloud)

Automation ticks often boot a **fresh branch from `main`** without `docs/ICML_*` or live runners.

1. If `docs/ICML_READY.md` says **STATUS: READY** → stop (already complete).
2. Run the **single cron entry** (Tick 271) — tip recover + secrets gate + live or preflight:

```bash
# Preferred once tip tree exists:
bash scripts/icml_cron_entry.sh

# Chicken-egg from main (entry script absent — Tick 270/271):
git fetch origin '+refs/heads/cursor/icml-epistemic-results-*:refs/remotes/origin/cursor/icml-epistemic-results-*'
TIP_REF=$(git for-each-ref --format='%(refname)' --sort=-committerdate \
  'refs/remotes/origin/cursor/icml-epistemic-results-*' | head -1)
git show "${TIP_REF}:scripts/icml_cron_entry.sh" | bash -s --
```

`icml_cron_entry.sh` recovers tip, writes `docs/icml_tip_status.json` + `docs/icml_secrets_status.json`, then either runs `run_icml_live_pipeline.py --live --fetch-diamond` (when secrets present) or preflight-only.

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
