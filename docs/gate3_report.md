# Gate 3 report — Pilot B vs D

**Status:** Offline synthetic pilot **refreshed** (2026-08-05 Tick 20, directed ε-explore); **live** G3 still blocked on API keys

Gate 3 (Section 21.5): pilot Condition B vs D on 1–2 seeds, `--eval_subset 15`, `max_gen ≤ 5`, before full 5-seed spend.

## Offline synthetic pilot (Tick 20 — not a live G3 substitute)

| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Run IDs |
|------|-------|-----|-------|---------|-------------|---------|
| B | 11,22,33,44,55 | 4 | 2 | 6 | 3 | `1780–1784` |
| D | 11,22,33,44,55 | 4 | 2 | 6 | 3 | `1790–1794` |

Harness: `scripts/offline_bvd_case_study.py` (compressed additive latent dry-run fitness [0.02, 0.34] + delay-all mutation bias until gen≥2 + directed ε-explore outside disputed pools + latest-gen bias harvest + delayed soft bias-aware crossover). H5 via `scripts/epistemic_results.compute_h5(min_generation=2, fitness_key="mean", delta_horizon=2)`.

| Metric | Result |
|--------|--------|
| D final-fitness wins (>1pp) | **5/5** |
| B final-fitness wins (>1pp) | **0/5** |
| Mean final (B / D) | ~0.253 / ~0.314 (~**6.15pp**) |
| D gens-to-30% wins | **4/5** (B: 0) — offline PRIMARY gens30; seed 22 unlocked |
| Gens-to-25% | Both hit gen1 (still saturated at 25%) |
| Gen-1 ≥30% | **0/5** seeds (saturation still fixed) |
| H5 ρ>0.3 (D seeds) | **5/5** (0.4 / 0.8 / 0.8 / 1.0 / 0.4) — mean forward Δ; gen≥2; horizon=2 |
| Case study | `docs/case_study_offline.md` (`run_1793`) — gen2 preferred share **0.25**; lift +0.0869 |
| Figures | `docs/figures/fig1_learning_curves.png`, `fig2_mechanism.png` |
| Summary JSON | `docs/offline_bvd_summary.json` |

**Finding:** Tick 19 left seed 22 under 30% because uniform ε-sampling often re-drew `minimal`/`aggressive`. Tick 20 directs explore to alleles **outside** the disputed pool → seed 22 discovers `selective` (gen4), crosses 30% (gen5), and offline gens30 rises to **4/5** while H5 stays **5/5** and mean gap ~**6.15pp**.

Prior Tick-19 pilot `1750–1754` / `1760–1764` remains the first offline H5 **5/5** snapshot. Tick-17 `1670–1674` / `1680–1684` remains the first offline gens30 PRIMARY-shaped snapshot. Tick-8 hash-fitness “D final 4/5” remains **withdrawn** (non-causal).

## Blockers (live G3)

1. No `ANTHROPIC_API_KEY` / `NEBIUS_API_KEY` in this cloud environment (verified empty; secrets re-requested 2026-08-05 Tick 20).
2. Bundled GPQA `data/public` not present in checkout — G2/G3 need dataset + keys (offline pilot used synthetic fixture).
3. ~~G1 dry-run~~ **PASS** 2026-08-04 (`runs/run_1401` dry-run; `SIA/tests/test_cabs_inline_dry_run.py`).
4. Offline pilot validates harness + case study + offline gens30 **4/5** + offline H5 **5/5** — **not** live PRIMARY.

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
- [x] ε-greedy mutation + live bias harvest (Tick 17) — gens30 **3/5**; final **5/5**; mean ~5.35pp
- [x] H5 steered-window + mean Δfitness (Tick 18) — H5 **4/5**; gens30/final held
- [x] H5 forward-horizon Δfitness (Tick 19) — H5 **5/5** (`delta_horizon=2`); gens30/final held
- [x] Directed ε-explore outside disputed pools (Tick 20) — gens30 **4/5**; mean ~6.15pp; H5 **5/5**
- [ ] G2: smoke GPQA subset (live)

## Live pilot plan (when unblocked)

| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Notes |
|------|-------|-----|-------|---------|-------------|-------|
| B | 1–2 | 4 | 2 | 5 | 15 | `--darwinian` only |
| D | 1–2 | 4 | 2 | 5 | 15 | `--cabs --cabs-inline` |

Record run IDs, final accuracy, gens-to-25%/30%, token/call counts, H2 histograms, H5 ρ in this file after the live pilot.
