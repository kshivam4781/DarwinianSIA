# Gate 3 report — Pilot B vs D

**Status:** Offline synthetic pilot **refreshed** (2026-08-04 Tick 10); **live** G3 still blocked on API keys

Gate 3 (Section 21.5): pilot Condition B vs D on 1–2 seeds, `--eval_subset 15`, `max_gen ≤ 5`, before full 5-seed spend.

## Offline synthetic pilot (Tick 10 — not a live G3 substitute)

| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Run IDs |
|------|-------|-----|-------|---------|-------------|---------|
| B | 11,22,33,44,55 | 4 | 2 | 4 | 3 | `1510–1514` |
| D | 11,22,33,44,55 | 4 | 2 | 4 | 3 | `1520–1524` |

Harness: `scripts/offline_bvd_case_study.py` (additive latent dry-run fitness + preferred-allele anchoring + singleton-bias skip).

| Metric | Result |
|--------|--------|
| D final-fitness wins (>1pp) | **2/5** |
| B final-fitness wins (>1pp) | **0/5** |
| Mean final (B / D) | ~0.282 / ~0.308 (~**2.56pp**) |
| D gens-to-30% wins | **2/5** (B: 0) |
| Gens-to-25% | Both hit gen1 (still often saturated) |
| H5 ρ>0.3 (D seeds) | **4/5**; pooled ρ≈0.23 |
| Case study | `docs/case_study_offline.md` (`run_1520`) |
| Figures | `docs/figures/fig1_learning_curves.png`, `fig2_mechanism.png` |
| Summary JSON | `docs/offline_bvd_summary.json` |

Prior Tick-9 pilot `1470–1474` / `1480–1484` superseded for PRIMARY tables (mean gap was noise). Tick-8 hash-fitness “D final 4/5” remains **withdrawn** (non-causal).

## Blockers (live G3)

1. No `ANTHROPIC_API_KEY` / `NEBIUS_API_KEY` in this cloud environment (verified empty).
2. Bundled GPQA `data/public` not present in checkout — G2/G3 need dataset + keys (offline pilot used synthetic fixture).
3. ~~G1 dry-run~~ **PASS** 2026-08-04 (`runs/run_1401` dry-run; `SIA/tests/test_cabs_inline_dry_run.py`).
4. Offline pilot validates harness + H5/case study + bias fixes — **not** live PRIMARY.

## Prerequisites completed

- [x] G0: contradiction-scoped mutation bias + unit H2 skew test
- [x] `--cabs-inline` Condition D loop hook + `epistemic_value.jsonl`
- [x] G1: dry-run Condition D (belief_store + scoped bias + gen≥2 DNA)
- [x] Scoped feedback DNA targets in CABS agenda (same pool as mutation bias)
- [x] Dry-run DNA-deterministic fitness + epistemic_results metrics script
- [x] Non-constant epistemic_value (age decay + flow) → offline H5 on `run_1403`
- [x] Fitness-weighted mutation bias (higher-fitness contradiction side preferred)
- [x] DNA-transferable dry-run fitness + offline B vs D case study (Tick 8)
- [x] Steering opportunity + additive latent fitness → multi-seed H5 4/5 (Tick 9)
- [x] Preferred-allele anchoring + singleton bias skip (Tick 10)
- [ ] G2: smoke GPQA subset (live)

## Live pilot plan (when unblocked)

| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Notes |
|------|-------|-----|-------|---------|-------------|-------|
| B | 1–2 | 4 | 2 | 5 | 15 | `--darwinian` only |
| D | 1–2 | 4 | 2 | 5 | 15 | `--cabs --cabs-inline` |

Record run IDs, final accuracy, gens-to-25%/30%, token/call counts, H2 histograms, H5 ρ in this file after the live pilot.
