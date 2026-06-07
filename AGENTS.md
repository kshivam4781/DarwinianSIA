# Agent guide — SIA-CABS hackathon

## Start here (required)

Before planning, coding, or running commands, read:

**[`docs/HACKATHON_MASTER_PLAN.md`](docs/HACKATHON_MASTER_PLAN.md)**

That document is the single source of truth for CABS architecture, APIs, hardware, blockers, phases, budgets, and run commands. Section 18–19 cover the **split-repo strategy** and merge contracts with Darwinian. **Section 20** is the full CABS + Darwinian merge implementation plan (file-level tasks, phases, testing, demo).

## Two-repo split (do not mix scope)

| Repo | Path | Build |
|------|------|-------|
| **SIA2 (this repo)** | `c:\Users\MSPSA\Documents\SIA2` | CABS, Tavily, committee |
| **Darwinian** | `c:\Users\MSPSA\Documents\SIA` | Population evolution, DNA, `civilization.json` |

Work in parallel; merge in Phase 7 per **Section 20**. Do not implement Darwinian loop code here unless the user explicitly asks (SIA2 owns CABS-side merge: analyze, cross-agent contradictions, civilization ingest).

## Quick rules

1. **Phase order is mandatory:** 0 → 1 → 2 → 3. Never skip Phase 0 gates.
2. **Money:** Do not run GPQA/LawBench without checking API keys and budget (Section 8). Never run full LawBench without user approval. Split budget ~60% SIA2 / ~40% SIA.
3. **Hardware:** Local GPU is unused. Inference goes through Nebius API; orchestration runs on CPU.
4. **Windows:** Windows venv fix is applied in `sia-upstream/sia/layout.py`.
5. **Run IDs:** Must be **integers** (`901`, `902`, `903`, …). SIA will not overwrite runs.
6. **Scope:** No weights/RL mode, no OpenClaw migration, no Darwinian in this repo.
7. **Status:** After work, update Section 12 in `docs/HACKATHON_MASTER_PLAN.md`.

## Project summary

- **What:** SIA-CABS — Contradiction-Aware Belief System (Layer 1 of unified stack)
- **Track:** Track 3 (Novel Self-Improvement Methodology)
- **CLI:** `sia-cabs` (CABS enabled), `sia` (baseline), `sia-cabs-tools` (analyze/agenda)
- **Workspace:** `c:\Users\MSPSA\Documents\SIA2`
- **Python:** 3.13 in `.venv` (`py -3.13`)

## Current status (2026-06-06)

- Phase 0 **complete** — smoke runs `run_901` / `run_902`
- **Next:** Phase 1 — structured beliefs, 3-gen validation (`run_id 903`)

## Sibling repo pointer

Darwinian work: `c:\Users\MSPSA\Documents\SIA` → read `SIA/docs/HACKATHON_FINISH_LINE.md` for submission sprint.
