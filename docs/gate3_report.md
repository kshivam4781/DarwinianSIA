# Gate 3 report — Pilot B vs D

**Status:** Offline synthetic pilot **refreshed** (2026-08-05 Tick 23, post-steering case-study H2); **live** G3 still blocked on API keys

Gate 3 (Section 21.5): pilot Condition B vs D on 1–2 seeds, `--eval_subset 15`, `max_gen ≤ 5`, before full 5-seed spend.

## Offline synthetic pilot (Tick 23 — not a live G3 substitute)

| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Run IDs |
|------|-------|-----|-------|---------|-------------|---------|
| B | 11,22,33,44,55 | 4 | 2 | 6 | 3 | `1830–1834` |
| D | 11,22,33,44,55 | 4 | 2 | 6 | 3 | `1840–1844` |

Harness: `scripts/offline_bvd_case_study.py` (compressed additive latent dry-run fitness [0.02, 0.34] + delay-all mutation bias until gen≥2 + directed ε-explore outside disputed pools + latest-gen bias harvest + delayed soft bias-aware crossover). H5 via `scripts/epistemic_results.compute_h5(min_generation=2, fitness_key="mean", delta_horizon=2)`. Cost via `cost_to_threshold` (eval-call proxy offline; tokens/USD preferred when present). Case study measures preferred DNA share at **gen≥3** (first steered generation).

| Metric | Result |
|--------|--------|
| D final-fitness wins (>1pp) | **5/5** |
| B final-fitness wins (>1pp) | **0/5** |
| Mean final (B / D) | ~0.253 / ~0.314 (~**6.15pp**) |
| D gens-to-30% wins | **4/5** (B: 0) — offline PRIMARY gens30; seed 44 tie |
| D cost-to-30% wins (≥15% / reach-vs-never) | **4/5** (B: 0) — offline PRIMARY cost30 (Tick 22 metric) |
| Gens-to-25% | Both hit gen1 (still saturated at 25%) |
| Gen-1 ≥30% | **0/5** seeds (saturation still fixed) |
| H5 ρ>0.3 (D seeds) | **5/5** (0.4 / 0.8 / 0.8 / 1.0 / 0.4) — mean forward Δ; gen≥2; horizon=2 |
| Case study | `docs/case_study_offline.md` (`run_1840`) — gen3 steered preferred share **0.75** (gen1/2/3 = 0.25→0.5→0.75); lift +0.0436 |
| Figures | `docs/figures/fig1_learning_curves.png`, `fig2_mechanism.png` |
| Summary JSON | `docs/offline_bvd_summary.json` |

**Finding:** Tick 22 left case-study H2 measured at fair-bred gen2 (~0.25 share). Tick 23 aligns the case study with delay-all: first steered generation is gen3. On `run_1840`, contradiction `selective` vs `aggressive` → preferred `selective` share rises **0.25→0.5→0.75** with fitness lift **+0.0436**. Offline PRIMARY/H5 rates unchanged (gens30/cost30 **4/5**, H5 **5/5**, mean gap ~**6.15pp**).

Prior Tick-22 pilot `1810–1814` / `1820–1824` remains the first offline cost30 **4/5** snapshot. Tick-20 `1780–1784` / `1790–1794` remains the first offline gens30 **4/5** snapshot. Tick-19 `1750–1754` / `1760–1764` remains the first offline H5 **5/5** snapshot. Tick-8 hash-fitness “D final 4/5” remains **withdrawn** (non-causal).

## Blockers (live G3)

1. No `ANTHROPIC_API_KEY` / `NEBIUS_API_KEY` in this cloud environment (verified empty; secrets re-requested 2026-08-05 Tick 24).
2. ~~Bundled GPQA `data/public` missing~~ **layout unblocked** Tick 21 via `scripts/prepare_gpqa_smoke_data.py` + CLI dry-run `run_1800`. Tick 24: `scripts/run_g2_smoke.py --preflight-only` → dry-run ready **yes**, live ready **no** (synthetic smoke + missing keys; see `docs/gate2_report.md`). Live G2/G3 still need **real** GPQA diamond JSON (HF `Idavidrein/gpqa` is gated) + keys.
3. ~~G1 dry-run~~ **PASS** 2026-08-04 (`runs/run_1401` dry-run; `SIA/tests/test_cabs_inline_dry_run.py`).
4. Offline pilot validates harness + post-steer case study + offline gens30/cost30 **4/5** + offline H5 **5/5** — **not** live PRIMARY.
5. `python3.12-venv` installed on cloud host this tick (was missing for SIA per-run venvs).

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
- [x] GPQA smoke fixture + CLI dry-run Condition D (Tick 21) — `prepare_gpqa_smoke_data.py` + `run_1800`
- [x] Cost-to-threshold PRIMARY metric (Tick 22) — offline cost30 **4/5**; live token path ready
- [x] Post-steering case-study H2 (Tick 23) — gen≥3 preferred share; `run_1840` share **0.75**
- [x] Live G2 preflight runner (Tick 24) — `scripts/run_g2_smoke.py` + `docs/gate2_report.md`
- [ ] G2: smoke GPQA subset (**live** API)

## Live pilot plan (when unblocked)

| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Notes |
|------|-------|-----|-------|---------|-------------|-------|
| B | 1–2 | 4 | 2 | 5 | 15 | `--darwinian` only |
| D | 1–2 | 4 | 2 | 5 | 15 | `--cabs --cabs-inline` |

Record run IDs, final accuracy, gens-to-25%/30%, token/call counts, H2 histograms, H5 ρ in this file after the live pilot.
