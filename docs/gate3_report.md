# Gate 3 report — Pilot B vs D

**Status:** NOT STARTED (2026-08-03)

Gate 3 (Section 21.5): pilot Condition B vs D on 1–2 seeds, `--eval_subset 15`, `max_gen ≤ 5`, before full 5-seed spend.

## Blockers

1. `--cabs-inline` not implemented (Condition D / epistemic_full).
2. No `ANTHROPIC_API_KEY` / `NEBIUS_API_KEY` in this cloud environment (verified empty).
3. No historical GPQA darwinian run dirs in this checkout (`runs/` absent).

## Prerequisites completed

- [x] G0: contradiction-scoped mutation bias + unit H2 skew test
- [ ] G1: dry-run Condition D
- [ ] G2: smoke GPQA subset

## Pilot plan (when unblocked)

| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Notes |
|------|-------|-----|-------|---------|-------------|-------|
| B | 1–2 | 4 | 2 | 5 | 15 | `--darwinian` only |
| D | 1–2 | 4 | 2 | 5 | 15 | `--cabs --cabs-inline` |

Record run IDs, final accuracy, gens-to-25%/30%, token/call counts, H2 histograms, H5 ρ in this file after the pilot.
