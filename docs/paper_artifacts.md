# ICML paper artifacts

**Status:** offline mechanism pack + synthetic B vs D pilot (Tick 23; post-steering H2 case study) + GPQA CLI harness dry-run `run_1800` (Tick 21). No publishable **live** GPQA figures/tables yet.

## Abstract (draft — do not claim READY)

We study whether a Contradiction-Aware Belief System (CABS) improves sample efficiency of population-based Darwinian self-improvement. Fitness-only evolution (Condition B) is compared to epistemic-full steering (Condition D: beliefs → contradictions → research questions → fitness-weighted biased mutation / bias-aware crossover / scoped feedback). Offline dry-run pilots with additive latent DNA fitness show a concrete case study (contradiction → preferred DNA → population skew → fitness lift). Delaying all Condition D DNA steering until breeding from gen≥2 prevents early preferred-allele collapse. Compressing the latent fitness ceiling to 0.34 (Tick 16) removes gen-1 threshold saturation. Tick 17 adds ε-greedy exploration plus latest-generation DNA harvest into the bias pool; Tick 20 makes explore **directed** (sample only alleles outside the disputed pool) so suboptimal frozen pairs (e.g. minimal vs aggressive) discover better outsiders (`selective`) — offline gens-to-30% wins on **4/5** seeds (final **5/5**, mean gap ~**6.15pp**). Tick 18–19 score H5 only after steering is active (gen≥2) against population-mean forward Δfitness over a 2-gen horizon → offline H5 ρ>0.3 on **5/5** seeds. Tick 22 adds **cost-to-threshold** (PRIMARY criterion b): cumulative tokens/USD when present, else eval-call proxies; D wins cost-to-30% on **4/5** seeds (≥15% fewer calls, or reach-vs-never). Tick 23 fixes the mechanism case study to report H2 DNA skew at the **first steered generation (gen≥3)** under delay-all — e.g. `tool_strategy=selective` share 0.25→0.5→0.75 across gen1/2/3 with fitness lift vs the loser side. **Live multi-seed GPQA subset results are pending.** Mechanism claim requires measurable DNA trait skew under contradiction bias (H2) and predictive validity of epistemic value for next-step fitness gain (H5) on live runs.


## Reproducible run IDs

| Condition | Seed | Run ID | Status |
|-----------|------|--------|--------|
| D epistemic_full (dry-run G1) | 42 | 1401 | **PASS** harness (no API; synthetic GPQA fixture; gitignored `runs/run_1401`) |
| D epistemic_full (dry-run H5 smoke) | 7 | 1402 | Offline only — pre-fix; constant epistemic_value=11.9 → ρ undefined; H2 memory in-bias 0.875 |
| D epistemic_full (dry-run H5 after epi fix) | 7 | 1403 | Offline — age-weighted + flow epi; H5 ρ **0.5**; not live GPQA |
| B / D (Tick 8–16 mid pilots) | 11–55 | 1410–1664 | Superseded — see prior ICML_PROGRESS ticks |
| B / D (Tick 17 ε-greedy pilot) | 11–55 | 1670–1674 / 1680–1684 | First offline gens30 **3/5**; H5 2/5 under old protocol |
| B / D (Tick 18 H5 protocol) | 11–55 | 1730–1734 / 1740–1744 | H5 **4/5** under gen≥2 + mean Δ; seed 11 ρ=0.0 |
| B / D (Tick 19 H5 horizon) | 11–55 | 1750–1754 / 1760–1764 | H5 **5/5**; gens30 **3/5**; seed 22 still under 30% |
| B / D (Tick 20 directed explore) | 11–55 | 1780–1784 / 1790–1794 | gens30 **4/5**; H5 **5/5**; superseded by Tick 22 IDs for cost columns |
| D epistemic_full (CLI dry-run harness Tick 21) | 42 | 1800 | Real `sia run --task gpqa --cabs --cabs-inline --dry-run` after `prepare_gpqa_smoke_data.py`; belief_store + scoped bias; **not** live GPQA |
| B / D (Tick 22 cost-to-threshold) | 11–55 | 1810–1814 / 1820–1824 | First offline cost30 **4/5**; case study `1823` (gen2 share era) |
| B darwinian-only (offline pilot Tick 23) | 11/22/33/44/55 | 1830–1834 | Post-steering case-study H2 (`max_gen=6`); gitignored `runs/` |
| D epistemic_full (offline pilot Tick 23) | 11/22/33/44/55 | 1840–1844 | Final **5/5**; gens30 **4/5**; cost30 **4/5**; H5 **5/5**; case study on `1840` (gen3 steered share **0.75**) |
| B darwinian-only | — | — | none yet (live) |
| D epistemic_full | — | — | none yet (live) |

Reserve unused integer IDs; never overwrite. Next live IDs suggested: B `1201+`, D `1301+` (Section 21.7); offline next ≥1850. Before live G2: `python scripts/prepare_gpqa_smoke_data.py` (or replace with real diamond JSON — HF `Idavidrein/gpqa` is gated), then drop `--dry-run`.

## Table 1 — Primary (B vs D)

### Offline synthetic pilot (Tick 23 — not live PRIMARY)

| Seed | B final | D final | B gens@30% | D gens@30% | B cost@30% | D cost@30% | Winner (final>1pp / gens30 / cost30) |
|------|---------|---------|------------|------------|------------|------------|--------------------------------------|
| 11 | 0.2652 | 0.3035 | — | 4 | — | 48 calls | D / D / D |
| 22 | 0.2258 | 0.3060 | — | 5 | — | 60 calls | D / D / D |
| 33 | 0.2950 | 0.3235 | — | 3 | — | 36 calls | D / D / D |
| 44 | 0.2220 | 0.3109 | 2 | 2 | 24 | 24 calls | D / tie / tie |
| 55 | 0.2550 | 0.3266 | — | 4 | — | 48 calls | D / D / D |

Mean final: B ≈ 0.253, D ≈ 0.314 (gap ~**6.15pp**). D final wins **5/5**; gens30 wins **4/5**; cost30 wins **4/5** (offline PRIMARY-shaped on (a) and (b)). Cost unit = cumulative agent eval-calls (`pop × eval_subset` summed until threshold); live runs will prefer token/USD fields. Source: `docs/offline_bvd_summary.json`.

### Live GPQA

| Seed | B final acc | D final acc | B gens@25% | D gens@25% | B tokens | D tokens | Winner |
|------|-------------|-------------|------------|------------|----------|----------|--------|
| — | — | — | — | — | — | — | — |

## Table 2 — Mechanism / validity

| Metric | Value | Pass? |
|--------|-------|-------|
| H2 trait skew (live API) | — | — |
| H2 dry-run scoped bias (G1) | memory∈{failure_based,none}; tool_strategy∈{aggressive,minimal}; ≠ full enums | yes (dry-run) |
| H2 offline pilot D (Tick 23) | directed ε-explore + live harvest; **post-steer** gen3 preferred share **0.75** (`run_1840`; gen1/2/3 = 0.25→0.5→0.75) | informative (dry-run) |
| H2 unit skew test | pass (+ preferred anchoring + bias-aware / delayed XO + tempered early mutate + delay-all + ε-greedy + directed explore) | yes (unit) |
| Fitness-weighted bias order | higher-fitness side first; exponential rank weights | yes (unit) |
| Singleton bias skip | `load_mutation_bias` requires ≥2 distinct candidates | yes (unit, Tick 10) |
| Bias-aware crossover | soft p=0.85 preferred inherit; delayed until breeding from gen≥2 | yes (unit, Tick 11–12) |
| Tempered early mutation | soft rank-weighted mutate option retained (`anchor_preferred`) | yes (unit, Tick 13) |
| Delay-all mutation bias | fair mutate gen1→gen2; full bias+anchor from gen≥2 (`apply_mutation_bias`) | yes (unit, Tick 14) |
| Compressed latent fitness | output scale `[0.02, 0.34]` (Tick 16) | yes (unit) |
| ε-greedy + live bias harvest | explore + adopt better latest-gen alleles (Tick 17) | yes (unit) |
| Directed ε-explore | explore samples only outsiders of disputed pool (Tick 20) | yes (unit + offline) |
| Cost-to-threshold | tokens/USD preferred; else eval-calls; ≥15% savings or reach-vs-never (Tick 22) | yes (unit + offline **4/5**) |
| H5 protocol | `min_generation=2`, `fitness_key=mean`, `delta_horizon=2` (Tick 18–19) | yes (unit + offline) |
| Case study chain | `docs/case_study_offline.md` (`run_1840`) | yes (offline; post-steer gen≥3) |
| H5 Spearman ρ | offline D `1840–1844`: **5/5** ρ>0.3 (0.4 / 0.8 / 0.8 / 1.0 / 0.4); live pending | offline pass; live need > 0.3 |
| Steering opportunity term | `fitness_gap × (1 − preferred share)` in epi | yes (unit + offline) |

## Figures

| Fig | Description | Path |
|-----|-------------|------|
| 1 | Accuracy / cost curves B vs D (offline draft) | `docs/figures/fig1_learning_curves.png` |
| 2 | H2 DNA skew / case-study support (offline draft) | `docs/figures/fig2_mechanism.png` |

## Case study (offline)

See `docs/case_study_offline.md`. Summary: gen1 contradiction on `tool_strategy` (`selective` vs `aggressive`) → fitness-weighted bias prefers `selective` → preferred share gen1/2/3 = **0.25→0.5→0.75** (gen3 = first steered gen under delay-all) → fitness lift **+0.0436** vs loser side (`run_1840`, Tick 23).

## Limitations (honest, keep updated)

- Mutation bias was previously a no-op (full enum); fixed and **validated on dry-run G1** (`run_1401`) but **not yet on live GPQA**.
- Same-allele cross-agent “contradictions” previously created singleton bias pools that wiped better elites; Tick 10 skips those pools — still **unverified on live GPQA**.
- Pre-Tick-7 bias treated both contradiction sides uniformly; now fitness-weighted + preferred-allele anchoring (unit-tested) but **unverified on live GPQA**.
- Soft bias-aware crossover (Tick 11) raised offline final seed wins to 3/5 but **hurt gens-to-30% (0/5) and H5 (2/5)** vs Tick 10.
- Delayed crossover bias (Tick 12) **did not restore gens30/H5** — mutation bias alone collapsed preferred alleles by gen2.
- Tempered early mutation bias (Tick 13) **partially restored H5 (3/5)** and mean gap (~1.66pp) but **gens30 still 0/5**; case-study preferred share could still hit 1.0 by gen2 under soft rank weights.
- Delay-all mutation bias (Tick 14) **fixed gen2 preferred collapse** (share 0.5) and raised final wins to **4/5** / mean gap ~**3.34pp**, but **gens30 still 0/5** at `max_gen=4` and H5 remains **3/5**.
- Longer-horizon re-pilot (Tick 15, `max_gen=6`) **does not unlock gens30** — 4/5 seeds hit 30% by gen≤2 for both B and D (threshold saturation).
- Compressed latent fitness (Tick 16, ceiling 0.34) **fixes gen-1 saturation** and raises gens30 to **2/5**; final 3/5 / mean ~2.26pp / H5 2/5. Gens-to-25% remains saturated.
- Pre-Tick-17 bias could **trap** populations in suboptimal frozen contradiction pairs (e.g. minimal vs aggressive) by forcing outsiders onto the local winner and never sampling unexplored alleles.
- ε-greedy + live harvest (Tick 17) unlocks offline gens30 **3/5** / final **5/5** / mean ~**5.35pp**, but uniform explore still wasted budget re-drawing pool alleles (seed 22 never found `selective`).
- Tick 18 H5 protocol (gen≥2 + mean Δ) restored offline H5 to **4/5**; Tick 19 forward-horizon (`delta_horizon=2`) recovers seed 11 → offline H5 **5/5**.
- Tick 20 directed explore unlocks seed 22 → offline gens30 **4/5** / mean ~**6.15pp** / H5 **5/5**. Still **not publishable** without live GPQA.
- Tick 22 cost-to-threshold uses **eval-call proxies** offline (no real tokens in dry-run). Live GPQA should prefer `total_*_tokens` / `total_cost_usd`. Expect Condition D **token** cost ≥ B if CABS/committee calls are counted even when eval-call cost-to-threshold favors D.
- Pre-Tick-23 case studies reported gen2 preferred share under delay-all (fair breed) — that understated H2; Tick 23 measures gen≥3.
- Scoped feedback now mirrors mutation-bias DNA candidates (2026-08-04); still untested on live rewrite quality.
- `--cabs-inline` + G1 dry-run PASS (2026-08-04); G2–G4 **live** B vs D evidence still missing.
- Tick 8 opaque DNA-hash fitness made offline D final 4/5 look strong but was **non-causal**; Tick 9–23 additive latent fitness is honest — offline gens30/cost30 **4/5** / H5 **5/5** but still **not publishable** without live GPQA (no API keys).
- No cloud API keys in this environment as of 2026-08-05 — no new paid evidence this tick; secrets re-requested for G2.
- Real GPQA diamond on HuggingFace (`Idavidrein/gpqa`) is **gated** (401 without accepted access + token); smoke fixture only for dry-run.
- Tick 21 unblocks gitignored GPQA layout via synthetic smoke fixture + CLI dry-run `run_1800`; **does not** satisfy live G2 (answers are synthetic; no Nebius/Anthropic calls).
- Small eval subsets and seed counts limit statistical power; avoid overclaiming.

## Code pins

| Component | Note |
|-----------|------|
| Contradiction-scoped bias | `SIA/sia/evolution/cabs_bridge.py::load_mutation_bias` |
| Singleton bias skip | `load_mutation_bias` requires ≥2 distinct candidates (Tick 10) |
| Fitness-weighted bias order | `load_mutation_bias` + exponential rank-weighted `_biased_choice` |
| Preferred-allele anchoring | `SIA/sia/evolution/operators.py::_biased_choice` (Tick 10; Tick 17 preserves outsiders) |
| ε-greedy mutation explore | `_BIAS_MUTATE_EXPLORE_EPS` in `_biased_choice` (Tick 17) |
| Directed ε-explore | explore samples only outsiders of disputed pool (Tick 20) |
| Live population bias harvest | `cabs_bridge._values_from_latest_population` (Tick 17) |
| Tempered early mutation | `anchor_preferred` / `apply_mutation_anchor` (Tick 13; now gated with delay-all) |
| Delay-all mutation bias | `breed_offspring(..., apply_mutation_bias=)` + `population.py` gen≥2 gate (Tick 14) |
| Bias-aware crossover | `SIA/sia/evolution/operators.py::_crossover_pick` + `crossover(..., bias=)` (Tick 11; soft p=0.85) |
| Delayed crossover bias | `breed_offspring(..., apply_crossover_bias=)` + `population.py` gen≥2 gate (Tick 12) |
| Scoped feedback DNA targets | `SIA/sia/evolution/cabs_bridge.py::load_cabs_agenda` |
| Biased mutate | `SIA/sia/evolution/operators.py::mutate` |
| Condition D inline analyze | `SIA/sia/evolution/cabs_inline.py` + `--cabs-inline` |
| H5 epistemic_value series | `belief_store/epistemic_value.jsonl` (age + flow + steering opportunity) |
| H5 protocol | `scripts/epistemic_results.py::compute_h5` (`min_generation=2`, `fitness_key=mean`, `delta_horizon=2`; Tick 18–19) |
| Cost-to-threshold | `scripts/epistemic_results.py::cost_to_threshold` / `_cost_win` (Tick 22; tokens > usd > calls) |
| Dry-run DNA fitness | `SIA/sia/evolution/dry_run.py::deterministic_fitness` (additive latent; Tick 16 scale `[0.02, 0.34]`) |
| Metrics / H5–H2 helpers | `scripts/epistemic_results.py` (gens-to-30% + cost-to-30% wins) |
| Offline B vs D + case study | `scripts/offline_bvd_case_study.py` (Tick 23: post-steer gen≥3 H2) |
