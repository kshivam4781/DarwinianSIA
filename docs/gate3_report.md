# Gate 3 report — Pilot B vs D

**Status:** Offline synthetic pilot **refreshed** (2026-08-05 Tick 15, `max_gen=6`); **live** G3 still blocked on API keys

Gate 3 (Section 21.5): pilot Condition B vs D on 1–2 seeds, `--eval_subset 15`, `max_gen ≤ 5`, before full 5-seed spend.

## Offline synthetic pilot (Tick 15 — not a live G3 substitute)

| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Run IDs |
|------|-------|-----|-------|---------|-------------|---------|
| B | 11,22,33,44,55 | 4 | 2 | 6 | 3 | `1630–1634` |
| D | 11,22,33,44,55 | 4 | 2 | 6 | 3 | `1640–1644` |

Harness: `scripts/offline_bvd_case_study.py` (additive latent dry-run fitness + delay-all mutation bias until gen≥2 + delayed soft bias-aware crossover; longer horizon).

| Metric | Result |
|--------|--------|
| D final-fitness wins (>1pp) | **3/5** |
| B final-fitness wins (>1pp) | **1/5** |
| Mean final (B / D) | ~0.282 / ~0.307 (~**2.55pp**) |
| D gens-to-30% wins | **0/5** (B: 1) — still fail |
| Gens-to-25% | Both hit gen1 (still saturated) |
| Gens-to-30% early | **4/5** seeds hit 30% by gen≤2 for **both** B and D |
| H5 ρ>0.3 (D seeds) | **2/5** (0.6 / 0.3 / 0.1 / 0.3 / 0.4) |
| Case study | `docs/case_study_offline.md` (`run_1640`) — gen2 preferred share **0.5** |
| Figures | `docs/figures/fig1_learning_curves.png`, `fig2_mechanism.png` |
| Summary JSON | `docs/offline_bvd_summary.json` |

**Finding:** extending horizon to `max_gen=6` under delay-all DNA steering does **not** unlock gens30. Root cause is **threshold saturation** (most seeds already at/above 30% by gen≤2 for both conditions), not insufficient biased breeding rounds. Final/H5 slightly regressed vs Tick 14 `max_gen=4` (final 4/5 → 3/5; H5 3/5 → 2/5; mean 3.34pp → 2.55pp).

Prior Tick-14 pilot `1610–1614` / `1620–1624` remains the best offline final-win snapshot. Tick-8 hash-fitness “D final 4/5” remains **withdrawn** (non-causal).

## Blockers (live G3)

1. No `ANTHROPIC_API_KEY` / `NEBIUS_API_KEY` in this cloud environment (verified empty).
2. Bundled GPQA `data/public` not present in checkout — G2/G3 need dataset + keys (offline pilot used synthetic fixture).
3. ~~G1 dry-run~~ **PASS** 2026-08-04 (`runs/run_1401` dry-run; `SIA/tests/test_cabs_inline_dry_run.py`).
4. Offline pilot validates harness + case study — **not** live PRIMARY; gens30 offline fail (threshold saturation); H5 offline soft.

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
- [x] Soft bias-aware crossover (Tick 11) — final wins 3/5 offline
- [x] Delayed bias-aware crossover (Tick 12) — mutation bias dominated early collapse
- [x] Tempered early mutation bias (Tick 13) — soft mutate gen1→gen2; H5 3/5; gens30 still 0/5
- [x] Delay-all mutation bias (Tick 14) — fair breed gen1→gen2; final 4/5; mean ~3.34pp; gens30 still 0/5
- [x] Longer-horizon offline re-pilot (Tick 15) — `max_gen=6`; gens30 still 0/5 (threshold saturation)
- [ ] G2: smoke GPQA subset (live)

## Live pilot plan (when unblocked)

| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Notes |
|------|-------|-----|-------|---------|-------------|-------|
| B | 1–2 | 4 | 2 | 5 | 15 | `--darwinian` only |
| D | 1–2 | 4 | 2 | 5 | 15 | `--cabs --cabs-inline` |

Record run IDs, final accuracy, gens-to-25%/30%, token/call counts, H2 histograms, H5 ρ in this file after the live pilot.
