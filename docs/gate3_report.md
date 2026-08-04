# Gate 3 report — Pilot B vs D

**Status:** Offline synthetic pilot **DONE** (2026-08-04 Tick 8); **live** G3 still blocked on API keys

Gate 3 (Section 21.5): pilot Condition B vs D on 1–2 seeds, `--eval_subset 15`, `max_gen ≤ 5`, before full 5-seed spend.

## Offline synthetic pilot (Tick 8 — not a live G3 substitute)

| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Run IDs |
|------|-------|-----|-------|---------|-------------|---------|
| B | 11,22,33,44,55 | 4 | 2 | 4 | 3 | `1410–1414` |
| D | 11,22,33,44,55 | 4 | 2 | 4 | 3 | `1420–1424` |

Harness: `scripts/offline_bvd_case_study.py` (DNA-transferable dry-run fitness).

| Metric | Result |
|--------|--------|
| D final-fitness wins | **4/5** |
| B final-fitness wins | 1/5 |
| Mean final (B / D) | ~0.838 / ~0.879 (~4.1pp) |
| Gens-to-25% | Both hit gen1 (uninformative) |
| Case study | `docs/case_study_offline.md` (`run_1420`) |
| Figures | `docs/figures/fig1_learning_curves.png`, `fig2_mechanism.png` |
| Summary JSON | `docs/offline_bvd_summary.json` |

## Blockers (live G3)

1. No `ANTHROPIC_API_KEY` / `NEBIUS_API_KEY` in this cloud environment (verified empty).
2. Bundled GPQA `data/public` not present in checkout — G2/G3 need dataset + keys (offline pilot used synthetic fixture).
3. ~~G1 dry-run~~ **PASS** 2026-08-04 (`runs/run_1401` dry-run; `SIA/tests/test_cabs_inline_dry_run.py`).
4. Offline pilot validates harness + case study only — **not** PRIMARY.

## Prerequisites completed

- [x] G0: contradiction-scoped mutation bias + unit H2 skew test
- [x] `--cabs-inline` Condition D loop hook + `epistemic_value.jsonl`
- [x] G1: dry-run Condition D (belief_store + scoped bias + gen≥2 DNA)
- [x] Scoped feedback DNA targets in CABS agenda (same pool as mutation bias)
- [x] Dry-run DNA-deterministic fitness + epistemic_results metrics script (2026-08-04 Tick 5)
- [x] Non-constant epistemic_value (age decay + flow) → offline H5 ρ=0.5 on `run_1403` (Tick 6)
- [x] Fitness-weighted mutation bias (higher-fitness contradiction side preferred; Tick 7)
- [x] DNA-transferable dry-run fitness + offline B vs D case study (Tick 8)
- [ ] G2: smoke GPQA subset (live)

## Live pilot plan (when unblocked)

| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Notes |
|------|-------|-----|-------|---------|-------------|-------|
| B | 1–2 | 4 | 2 | 5 | 15 | `--darwinian` only |
| D | 1–2 | 4 | 2 | 5 | 15 | `--cabs --cabs-inline` |

Record run IDs, final accuracy, gens-to-25%/30%, token/call counts, H2 histograms, H5 ρ in this file after the live pilot.
