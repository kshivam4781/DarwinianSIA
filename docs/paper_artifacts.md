# ICML paper artifacts

**Status:** offline mechanism pack + synthetic B vs D pilot refreshed (2026-08-05 Tick 16, compressed latent fitness [0.02, 0.34]). No publishable **live** GPQA figures/tables yet.

## Abstract (draft — do not claim READY)

We study whether a Contradiction-Aware Belief System (CABS) improves sample efficiency of population-based Darwinian self-improvement. Fitness-only evolution (Condition B) is compared to epistemic-full steering (Condition D: beliefs → contradictions → research questions → fitness-weighted biased mutation / bias-aware crossover / scoped feedback). Offline dry-run pilots with additive latent DNA fitness show a concrete case study (contradiction → preferred DNA → population skew → fitness lift). Delaying all Condition D DNA steering until breeding from gen≥2 prevents early preferred-allele collapse (case-study gen2 share 0.5). Compressing the latent fitness ceiling to 0.34 (Tick 16) removes gen-1 threshold saturation and unlocks offline gens-to-30% wins (**2/5**, up from 0/5); final wins remain **3/5** (mean gap ~**2.26pp**). **Live multi-seed GPQA subset results are pending.** Mechanism claim requires measurable DNA trait skew under contradiction bias (H2) and predictive validity of epistemic value for next-step fitness gain (H5) on live runs.


## Reproducible run IDs

| Condition | Seed | Run ID | Status |
|-----------|------|--------|--------|
| D epistemic_full (dry-run G1) | 42 | 1401 | **PASS** harness (no API; synthetic GPQA fixture; gitignored `runs/run_1401`) |
| D epistemic_full (dry-run H5 smoke) | 7 | 1402 | Offline only — pre-fix; constant epistemic_value=11.9 → ρ undefined; H2 memory in-bias 0.875 |
| D epistemic_full (dry-run H5 after epi fix) | 7 | 1403 | Offline — age-weighted + flow epi; H5 ρ **0.5**; not live GPQA |
| B / D (Tick 8 hash-fitness pilot) | 11–55 | 1410–1414 / 1420–1424 | Superseded — non-causal hash fitness |
| B / D (Tick 9 mid pilots) | 11–55 | 1430–1464 / 1470–1484 | Superseded by Tick 10 bias fix |
| B / D (Tick 10 mid: anchoring-only) | 11–55 | 1490–1494 / 1500–1504 | Intermediate — singleton bias still wiped elites |
| B / D (Tick 10 preferred-anchor pilot) | 11–55 | 1510–1514 / 1520–1524 | Superseded by Tick 11 bias-aware XO |
| B / D (Tick 11 hard-XO mid) | 11–55 | 1530–1534 / 1540–1544 | Intermediate — hard preferred XO over-collapsed diversity |
| B / D (Tick 11 soft-XO pilot) | 11–55 | 1550–1554 / 1560–1564 | Superseded by Tick 12 delayed-XO pilot |
| B / D (Tick 12 delayed-XO pilot) | 11–55 | 1570–1574 / 1580–1584 | Superseded by Tick 13 tempered-mutation pilot |
| B / D (Tick 13 tempered-mutation pilot) | 11–55 | 1590–1594 / 1600–1604 | Superseded by Tick 14 delay-all mutation bias |
| B / D (Tick 14 delay-all, max_gen=4) | 11–55 | 1610–1614 / 1620–1624 | Best offline final (4/5, ~3.34pp); H5 3/5; gens30 0/5 |
| B / D (Tick 15 longer-horizon) | 11–55 | 1630–1634 / 1640–1644 | Superseded — gens30 0/5 via threshold saturation |
| B darwinian-only (offline pilot Tick 16) | 11/22/33/44/55 | 1650–1654 | Compressed fitness control (`max_gen=6`); gitignored `runs/` |
| D epistemic_full (offline pilot Tick 16) | 11/22/33/44/55 | 1660–1664 | Final 3/5; gens30 **2/5**; H5 2/5; case study on `1660` |
| B darwinian-only | — | — | none yet (live) |
| D epistemic_full | — | — | none yet (live) |

Reserve unused integer IDs; never overwrite. Next live IDs suggested: B `1201+`, D `1301+` (Section 21.7).

## Table 1 — Primary (B vs D)

### Offline synthetic pilot (Tick 16, compressed fitness — not PRIMARY)

| Seed | B final | D final | B gens@25% | D gens@25% | B gens@30% | D gens@30% | Winner (final>1pp / gens30) |
|------|---------|---------|------------|------------|------------|------------|------------------------------|
| 11 | 0.2652 | 0.3017 | 1 | 1 | — | 3 | D / D |
| 22 | 0.2258 | 0.2653 | 1 | 1 | — | — | D / tie |
| 33 | 0.2950 | 0.2756 | 1 | 1 | — | — | B / tie |
| 44 | 0.2220 | 0.2211 | 1 | 1 | 2 | 2 | tie / tie |
| 55 | 0.2550 | 0.3125 | 1 | 1 | — | 5 | D / D |

Mean final: B ≈ 0.253, D ≈ 0.275 (gap ~**2.26pp**). D final wins 3/5; gens30 wins **2/5**. Source: `docs/offline_bvd_summary.json`. Tick 14 (`max_gen=4`) remains best offline final (4/5, ~3.34pp).

### Live GPQA

| Seed | B final acc | D final acc | B gens@25% | D gens@25% | B tokens | D tokens | Winner |
|------|-------------|-------------|------------|------------|----------|----------|--------|
| — | — | — | — | — | — | — | — |

## Table 2 — Mechanism / validity

| Metric | Value | Pass? |
|--------|-------|-------|
| H2 trait skew (live API) | — | — |
| H2 dry-run scoped bias (G1) | memory∈{failure_based,none}; tool_strategy∈{aggressive,minimal}; ≠ full enums | yes (dry-run) |
| H2 offline pilot D (Tick 16) | delay-all DNA steering until gen≥2; case-study gen2 preferred share **0.5** (`run_1660`) | informative (dry-run) |
| H2 unit skew test | pass (+ preferred-allele anchoring + bias-aware / delayed XO + tempered early mutate + delay-all mutation bias) | yes (unit) |
| Fitness-weighted bias order | higher-fitness side first; exponential rank weights | yes (unit) |
| Singleton bias skip | `load_mutation_bias` requires ≥2 distinct candidates | yes (unit, Tick 10) |
| Bias-aware crossover | soft p=0.85 preferred inherit; delayed until breeding from gen≥2 | yes (unit, Tick 11–12) |
| Tempered early mutation | soft rank-weighted mutate option retained (`anchor_preferred`) | yes (unit, Tick 13) |
| Delay-all mutation bias | fair mutate gen1→gen2; full bias+anchor from gen≥2 (`apply_mutation_bias`) | yes (unit, Tick 14) |
| Compressed latent fitness | output scale `[0.02, 0.34]` (Tick 16) | yes (unit) |
| Case study chain | `docs/case_study_offline.md` (`run_1660`) | yes (offline) |
| H5 Spearman ρ | offline D `1660–1664` (`max_gen=6`): **2/5** ρ>0.3; Tick 14 best **3/5**; live pending | offline soft; live need > 0.3 |
| Steering opportunity term | `fitness_gap × (1 − preferred share)` in epi | yes (unit + offline) |

## Figures

| Fig | Description | Path |
|-----|-------------|------|
| 1 | Accuracy / cost curves B vs D (offline draft) | `docs/figures/fig1_learning_curves.png` |
| 2 | H2 DNA skew / case-study support (offline draft) | `docs/figures/fig2_mechanism.png` |

## Case study (offline)

See `docs/case_study_offline.md`. Summary: gen1 contradiction on `tool_strategy` (`selective` vs `aggressive`) → fitness-weighted bias prefers `selective` → gen2 preferred share **0.5** (fair early breed) → fitness lift **+0.0420** vs loser side (`run_1660`, Tick 16).

## Limitations (honest, keep updated)

- Mutation bias was previously a no-op (full enum); fixed and **validated on dry-run G1** (`run_1401`) but **not yet on live GPQA**.
- Same-allele cross-agent “contradictions” previously created singleton bias pools that wiped better elites; Tick 10 skips those pools — still **unverified on live GPQA**.
- Pre-Tick-7 bias treated both contradiction sides uniformly; now fitness-weighted + preferred-allele anchoring (unit-tested) but **unverified on live GPQA**.
- Soft bias-aware crossover (Tick 11) raised offline final seed wins to 3/5 but **hurt gens-to-30% (0/5) and H5 (2/5)** vs Tick 10.
- Delayed crossover bias (Tick 12) **did not restore gens30/H5** — mutation bias alone collapsed preferred alleles by gen2.
- Tempered early mutation bias (Tick 13) **partially restored H5 (3/5)** and mean gap (~1.66pp) but **gens30 still 0/5**; case-study preferred share could still hit 1.0 by gen2 under soft rank weights.
- Delay-all mutation bias (Tick 14) **fixed gen2 preferred collapse** (share 0.5) and raised final wins to **4/5** / mean gap ~**3.34pp**, but **gens30 still 0/5** at `max_gen=4` and H5 remains **3/5**.
- Longer-horizon re-pilot (Tick 15, `max_gen=6`) **does not unlock gens30** — 4/5 seeds hit 30% by gen≤2 for both B and D (threshold saturation).
- Compressed latent fitness (Tick 16, ceiling 0.34) **fixes gen-1 saturation** and raises gens30 to **2/5** (still short of ≥3/5); final 3/5 / mean ~2.26pp / H5 2/5. Gens-to-25% remains saturated.
- Scoped feedback now mirrors mutation-bias DNA candidates (2026-08-04); still untested on live rewrite quality.
- `--cabs-inline` + G1 dry-run PASS (2026-08-04); G2–G4 **live** B vs D evidence still missing.
- Tick 8 opaque DNA-hash fitness made offline D final 4/5 look strong but was **non-causal**; Tick 9–16 additive latent fitness is honest — offline PRIMARY still **not publishable** (gens30 2/5; H5 soft; no live GPQA).
- No cloud API keys in this environment as of 2026-08-05 — no new paid evidence this tick.
- Expect Condition D token cost ≥ B if CABS/committee calls are counted; primary win may be gens-to-threshold or cost-to-threshold, not raw final accuracy.
- Small eval subsets and seed counts limit statistical power; avoid overclaiming.

## Code pins

| Component | Note |
|-----------|------|
| Contradiction-scoped bias | `SIA/sia/evolution/cabs_bridge.py::load_mutation_bias` |
| Singleton bias skip | `load_mutation_bias` requires ≥2 distinct candidates (Tick 10) |
| Fitness-weighted bias order | `load_mutation_bias` + exponential rank-weighted `_biased_choice` |
| Preferred-allele anchoring | `SIA/sia/evolution/operators.py::_biased_choice` (Tick 10) |
| Tempered early mutation | `anchor_preferred` / `apply_mutation_anchor` (Tick 13; now gated with delay-all) |
| Delay-all mutation bias | `breed_offspring(..., apply_mutation_bias=)` + `population.py` gen≥2 gate (Tick 14) |
| Bias-aware crossover | `SIA/sia/evolution/operators.py::_crossover_pick` + `crossover(..., bias=)` (Tick 11; soft p=0.85) |
| Delayed crossover bias | `breed_offspring(..., apply_crossover_bias=)` + `population.py` gen≥2 gate (Tick 12) |
| Scoped feedback DNA targets | `SIA/sia/evolution/cabs_bridge.py::load_cabs_agenda` |
| Biased mutate | `SIA/sia/evolution/operators.py::mutate` |
| Condition D inline analyze | `SIA/sia/evolution/cabs_inline.py` + `--cabs-inline` |
| H5 epistemic_value series | `belief_store/epistemic_value.jsonl` (age + flow + steering opportunity) |
| Dry-run DNA fitness | `SIA/sia/evolution/dry_run.py::deterministic_fitness` (additive latent; Tick 16 scale `[0.02, 0.34]`) |
| Metrics / H5–H2 helpers | `scripts/epistemic_results.py` (gens-to-30% wins) |
| Offline B vs D + case study | `scripts/offline_bvd_case_study.py` |
| H2 unit test | `SIA/tests/test_cabs_bridge.py` |
| Inline unit test | `SIA/tests/test_cabs_inline.py` |
| G1 dry-run Condition D | `SIA/tests/test_cabs_inline_dry_run.py` |
| Epistemic metrics tests | `SIA/tests/test_epistemic_results.py` |
