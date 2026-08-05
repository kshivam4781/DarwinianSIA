# ICML Thesis 1 — Ready checklist

**STATUS: IN_PROGRESS**

Do not set STATUS: READY until every item below is checked and evidence paths are real.

## Criteria

### 1. PRIMARY — Condition D beats B
- [ ] D beats B on ≥3/5 seeds for gens-to-threshold (25% or 30%), **or**
- [ ] D beats B on ≥3/5 seeds for cost-to-threshold (≥15% fewer tokens/calls), **or**
- [ ] Non-trivial mean final accuracy gap (not ~1pp noise)
- Evidence: offline synthetic pilot `1810–1814` vs `1820–1824` (Tick 22; cost-to-threshold metric) — D gens30 wins **4/5** (B: 0), D cost30 wins **4/5** (B: 0; eval-call proxy), D final wins **5/5**, mean final gap ~**6.15pp**. Offline PRIMARY-shaped signal only — **not** live GPQA; leave unchecked for READY. Live → `docs/paper_artifacts.md` Table 1

### 2. MECHANISM — H2 or case study
- [x] Unit-level H2: contradiction bias skews DNA vs uniform (`SIA/tests/test_cabs_bridge.py`)
- [x] Dry-run in-loop H2 path: scoped mutation bias after `--cabs-inline` (`runs/run_1401`, `SIA/tests/test_cabs_inline_dry_run.py`)
- [x] Scoped feedback injects same DNA candidates as bias (`load_cabs_agenda` + `test_cabs_agenda_includes_scoped_dna_feedback_targets`)
- [x] Fitness-weighted bias: higher-fitness contradiction side ranked first + rank-weighted mutate (`test_mutation_bias_prefers_higher_fitness_side`)
- [x] Preferred-allele anchoring + singleton-bias skip (Tick 10) — Tick 17: outsiders preserved; ε-greedy explores
- [x] Bias-aware crossover (Tick 11) — soft preferred inherit in `crossover(..., bias=)` + `test_bias_aware_crossover_prefers_winner_allele`
- [x] Delayed crossover bias (Tick 12) — fair XO gen1→gen2; soft bias XO from gen2→gen3+ (`apply_crossover_bias`, `test_breed_offspring_can_delay_crossover_bias`)
- [x] Tempered early mutation bias (Tick 13) — soft rank-weighted mutate gen1→gen2; full preferred anchoring from gen≥2 (`apply_mutation_anchor`, `test_biased_mutate_can_soften_preferred_anchor`)
- [x] Delayed **all** mutation bias (Tick 14) — fair mutate+XO gen1→gen2; full CABS steering from gen≥2 (`apply_mutation_bias`, `test_breed_offspring_can_delay_all_mutation_bias`)
- [x] Compressed latent fitness scale (Tick 16) — `[0.02, 0.34]` keeps gen-1 under 30% (`test_deterministic_fitness_scale_keeps_mid_dna_under_threshold`)
- [x] ε-greedy mutation + live population bias harvest (Tick 17) — escape suboptimal frozen contradiction pairs
- [x] Directed ε-explore outside disputed pools (Tick 20) — explore samples only outsiders (`test_biased_mutate_directed_explore_never_redraws_pool`)
- [x] H5 protocol (Tick 18–19) — steered-window (`min_generation=2`) + population-mean forward Δfitness (`delta_horizon=2`; `scripts/epistemic_results.py`)
- [x] Cost-to-threshold PRIMARY helper (Tick 22) — tokens/USD/eval-calls; ≥15% savings wins (`cost_to_threshold`, `primary_cost30_pass`)
- [x] Documented case study (tie → contradiction → different DNA → fitness lift) with artifacts — offline dry-run `docs/case_study_offline.md` + `run_1823` (`stepwise` preferred → gen2 share **0.25**; lift +0.0869)
- [ ] Live API-run H2 DNA trait skew under contradiction bias
- Evidence: unit + dry-run G1 + scoped feedback + fitness-weighted order + preferred anchoring + bias-aware/delayed XO + tempered early mutation + delay-all mutation bias + compressed fitness scale + ε-greedy/live harvest + directed explore + H5 protocol + cost-to-threshold + offline case study; live GPQA still pending (no API keys)

### 3. VALIDITY — H5
- [ ] Spearman ρ (`epistemic_value_t` vs `Δfitness_t+1`) > 0.3 on live / publishable runs
- Evidence: offline multi-seed Condition D `1820–1824` (`max_gen=6`) → ρ>0.3 on **5/5** seeds (0.4 / 0.8 / 0.8 / 1.0 / 0.4) using population-mean forward Δfitness (`delta_horizon=2`) and gen≥2 pairs. Still **not** live GPQA.

### 4. PAPER
- [x] Figure 1 draft (offline B vs D learning curves) — `docs/figures/fig1_learning_curves.png`
- [x] Figure 2 draft (H2 DNA histogram / case-study support) — `docs/figures/fig2_mechanism.png`
- [ ] Table 1 (primary metrics by seed) — offline stub filled (incl. cost30); live empty
- [ ] Table 2 (H2/H5 / cost) — offline cost30 **4/5** filled; live empty
- [x] Abstract draft (scaffold in `docs/paper_artifacts.md` — live results TBD)
- [x] Limitations (honest; kept updated in `docs/paper_artifacts.md`)
- [ ] Reproducible **live** run IDs listed in `docs/paper_artifacts.md` (dry-run IDs present; live pending)
- Metrics helper: `scripts/epistemic_results.py`; offline pilot: `scripts/offline_bvd_case_study.py`
- G2 layout helper: `scripts/prepare_gpqa_smoke_data.py` (Tick 21; CLI dry-run `run_1800` — not live)

## Gate tracker (Section 21.5)

| Gate | Status |
|------|--------|
| G0 mechanism unit tests | **PASS** (2026-08-03; + delay-all Tick 14; + compressed fitness Tick 16; + ε-greedy/live harvest Tick 17; + H5 protocol Tick 18–19; + directed explore Tick 20; + cost-to-threshold Tick 22) |
| G1 dry-run Condition D | **PASS** (2026-08-04) — `run_1401` + `test_cabs_inline_dry_run.py` |
| G2 smoke GPQA subset | **HARNESS READY** (Tick 21: `prepare_gpqa_smoke_data.py` + CLI dry-run `run_1800`); **live** G2 still BLOCKED (no API keys; need real GPQA diamond) |
| G3 pilot B vs D | Offline synthetic pilot refreshed (Tick 22; gens30 **4/5**; cost30 **4/5**; H5 **5/5**); **live** G3 NOT STARTED |
| G4 5-seed + metrics | NOT STARTED (live) |
| G5 paper pack | PARTIAL (offline figs + case study + offline PRIMARY gens30/cost30 4/5 + offline H5 5/5); live pack NOT STARTED |
