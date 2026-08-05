# Gate 3 report — Pilot B vs D

**Status:** Offline synthetic pilot **refreshed** (2026-08-05 Tick 16, compressed latent fitness); **live** G3 still blocked on API keys

Gate 3 (Section 21.5): pilot Condition B vs D on 1–2 seeds, `--eval_subset 15`, `max_gen ≤ 5`, before full 5-seed spend.

## Offline synthetic pilot (Tick 16 — not a live G3 substitute)

| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Run IDs |
|------|-------|-----|-------|---------|-------------|---------|
| B | 11,22,33,44,55 | 4 | 2 | 6 | 3 | `1650–1654` |
| D | 11,22,33,44,55 | 4 | 2 | 6 | 3 | `1660–1664` |

Harness: `scripts/offline_bvd_case_study.py` (compressed additive latent dry-run fitness [0.02, 0.34] + delay-all mutation bias until gen≥2 + delayed soft bias-aware crossover).

| Metric | Result |
|--------|--------|
| D final-fitness wins (>1pp) | **3/5** |
| B final-fitness wins (>1pp) | **1/5** |
| Mean final (B / D) | ~0.253 / ~0.275 (~**2.26pp**) |
| D gens-to-30% wins | **2/5** (B: 0) — improved from Tick 15's 0/5; still short of ≥3/5 |
| Gens-to-25% | Both hit gen1 (still saturated at 25%) |
| Gen-1 ≥30% | **0/5** seeds (saturation fixed vs Tick 15's 4/5 early hits) |
| H5 ρ>0.3 (D seeds) | **2/5** (0.6 / 0.3 / 0.1 / 0.3 / 0.4) |
| Case study | `docs/case_study_offline.md` (`run_1660`) — gen2 preferred share **0.5**; lift +0.0420 |
| Figures | `docs/figures/fig1_learning_curves.png`, `fig2_mechanism.png` |
| Summary JSON | `docs/offline_bvd_summary.json` |

**Finding:** compressing the additive latent fitness ceiling from 0.38 → 0.34 makes gens-to-30% discriminative again. Seeds 11 and 55 are clear D reach-vs-never wins (D@gen3 / D@gen5; B never ≥30%). Seed 44 still ties at gen2 via a lucky fair-breed spike; seeds 22/33 never cross 30%. Final/H5 roughly stable vs Tick 15.

Prior Tick-14 pilot `1610–1614` / `1620–1624` remains the best offline final-win snapshot (4/5, ~3.34pp). Tick-8 hash-fitness “D final 4/5” remains **withdrawn** (non-causal).

## Blockers (live G3)

1. No `ANTHROPIC_API_KEY` / `NEBIUS_API_KEY` in this cloud environment (verified empty).
2. Bundled GPQA `data/public` not present in checkout — G2/G3 need dataset + keys (offline pilot used synthetic fixture).
3. ~~G1 dry-run~~ **PASS** 2026-08-04 (`runs/run_1401` dry-run; `SIA/tests/test_cabs_inline_dry_run.py`).
4. Offline pilot validates harness + case study — **not** live PRIMARY; gens30 offline **2/5** (short of 3/5); H5 offline soft.

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
- [x] Compressed latent fitness scale (Tick 16) — `[0.02, 0.34]`; gens30 **2/5**; gen-1 saturation fixed
- [ ] G2: smoke GPQA subset (live)

## Live pilot plan (when unblocked)

| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Notes |
|------|-------|-----|-------|---------|-------------|-------|
| B | 1–2 | 4 | 2 | 5 | 15 | `--darwinian` only |
| D | 1–2 | 4 | 2 | 5 | 15 | `--cabs --cabs-inline` |

Record run IDs, final accuracy, gens-to-25%/30%, token/call counts, H2 histograms, H5 ρ in this file after the live pilot.
