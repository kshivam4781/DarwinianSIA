# ICML paper artifacts

**Status:** offline mechanism pack + synthetic B vs D pilot refreshed (2026-08-04 Tick 10). No publishable **live** GPQA figures/tables yet.

## Abstract (draft — do not claim READY)

We study whether a Contradiction-Aware Belief System (CABS) improves sample efficiency of population-based Darwinian self-improvement. Fitness-only evolution (Condition B) is compared to epistemic-full steering (Condition D: beliefs → contradictions → research questions → fitness-weighted biased mutation / scoped feedback). Offline dry-run pilots with additive latent DNA fitness show a concrete case study (contradiction → preferred DNA → population skew → fitness lift) and multi-seed H5 validity (Spearman ρ > 0.3 on 4/5 seeds) after preferred-allele anchoring and skipping singleton same-allele bias pools. **Offline PRIMARY (D≻B on ≥3/5 seeds) is not yet met** (gens30 2/5; mean final gap ~2.6pp); **live multi-seed GPQA subset results pending.** Mechanism claim requires measurable DNA trait skew under contradiction bias (H2) and predictive validity of epistemic value for next-step fitness gain (H5) on live runs.


## Reproducible run IDs

| Condition | Seed | Run ID | Status |
|-----------|------|--------|--------|
| D epistemic_full (dry-run G1) | 42 | 1401 | **PASS** harness (no API; synthetic GPQA fixture; gitignored `runs/run_1401`) |
| D epistemic_full (dry-run H5 smoke) | 7 | 1402 | Offline only — pre-fix; constant epistemic_value=11.9 → ρ undefined; H2 memory in-bias 0.875 |
| D epistemic_full (dry-run H5 after epi fix) | 7 | 1403 | Offline — age-weighted + flow epi; H5 ρ **0.5**; not live GPQA |
| B / D (Tick 8 hash-fitness pilot) | 11–55 | 1410–1414 / 1420–1424 | Superseded — non-causal hash fitness |
| B / D (Tick 9 mid pilots) | 11–55 | 1430–1464 / 1470–1484 | Superseded by Tick 10 bias fix |
| B / D (Tick 10 mid: anchoring-only) | 11–55 | 1490–1494 / 1500–1504 | Intermediate — singleton bias still wiped elites |
| B darwinian-only (offline pilot Tick 10) | 11/22/33/44/55 | 1510–1514 | Additive latent + singleton gate; gitignored `runs/` |
| D epistemic_full (offline pilot Tick 10) | 11/22/33/44/55 | 1520–1524 | H5 4/5 ρ>0.3; case study on `1520` |
| B darwinian-only | — | — | none yet (live) |
| D epistemic_full | — | — | none yet (live) |

Reserve unused integer IDs; never overwrite. Next live IDs suggested: B `1201+`, D `1301+` (Section 21.7).

## Table 1 — Primary (B vs D)

### Offline synthetic pilot (Tick 10 — not PRIMARY)

| Seed | B final | D final | B gens@25% | D gens@25% | B gens@30% | D gens@30% | Winner (final>1pp / gens30) |
|------|---------|---------|------------|------------|------------|------------|------------------------------|
| 11 | 0.2658 | 0.3404 | 1 | 1 | — | 2 | D / D |
| 22 | 0.2479 | 0.3016 | 1 | 1 | 3 | 2 | D / D |
| 33 | 0.3047 | 0.3057 | 1 | 1 | 1 | 1 | tie / tie |
| 44 | 0.2715 | 0.2712 | 1 | 1 | 2 | 2 | tie / tie |
| 55 | 0.3224 | 0.3216 | 1 | 1 | 1 | 1 | tie / tie |

Mean final: B ≈ 0.282, D ≈ 0.308 (gap ~**2.56pp**). D final wins 2/5; gens30 wins 2/5. Source: `docs/offline_bvd_summary.json`.

### Live GPQA

| Seed | B final acc | D final acc | B gens@25% | D gens@25% | B tokens | D tokens | Winner |
|------|-------------|-------------|------------|------------|----------|----------|--------|
| — | — | — | — | — | — | — | — |

## Table 2 — Mechanism / validity

| Metric | Value | Pass? |
|--------|-------|-------|
| H2 trait skew (live API) | — | — |
| H2 dry-run scoped bias (G1) | memory∈{failure_based,none}; tool_strategy∈{aggressive,minimal}; ≠ full enums | yes (dry-run) |
| H2 offline pilot D (Tick 10) | preferred anchoring; in-bias share often high when multi-value bias present | informative (dry-run) |
| H2 unit skew test | pass (+ preferred-allele anchoring) | yes (unit) |
| Fitness-weighted bias order | higher-fitness side first; exponential rank weights | yes (unit) |
| Singleton bias skip | `load_mutation_bias` requires ≥2 distinct candidates | yes (unit, Tick 10) |
| Case study chain | `docs/case_study_offline.md` (`run_1520`) | yes (offline) |
| H5 Spearman ρ | offline D `1520–1524`: **4/5** ρ>0.3; pooled ρ≈**0.23** (n=15); live pending | offline seed-level yes; pooled soft; live need > 0.3 |
| Steering opportunity term | `fitness_gap × (1 − preferred share)` in epi | yes (unit + offline) |

## Figures

| Fig | Description | Path |
|-----|-------------|------|
| 1 | Accuracy / cost curves B vs D (offline draft) | `docs/figures/fig1_learning_curves.png` |
| 2 | H2 DNA skew / case-study support (offline draft) | `docs/figures/fig2_mechanism.png` |

## Case study (offline)

See `docs/case_study_offline.md`. Summary: gen1 contradiction on `tool_strategy` (`selective` vs `aggressive`) → fitness-weighted bias prefers `selective` → gen2 preferred share **1.0** → fitness lift **+0.0866** vs loser side (`run_1520`).

## Limitations (honest, keep updated)

- Mutation bias was previously a no-op (full enum); fixed and **validated on dry-run G1** (`run_1401`) but **not yet on live GPQA**.
- Same-allele cross-agent “contradictions” previously created singleton bias pools that wiped better elites; Tick 10 skips those pools — still **unverified on live GPQA**.
- Pre-Tick-7 bias treated both contradiction sides uniformly; now fitness-weighted + preferred-allele anchoring (unit-tested) but **unverified on live GPQA**.
- Scoped feedback now mirrors mutation-bias DNA candidates (2026-08-04); still untested on live rewrite quality.
- `--cabs-inline` + G1 dry-run PASS (2026-08-04); G2–G4 **live** B vs D evidence still missing.
- Tick 8 opaque DNA-hash fitness made offline D final 4/5 look strong but was **non-causal**; Tick 9–10 additive latent fitness is honest — offline PRIMARY still **fails** seed-win bars (final 2/5, gens30 2/5) despite mean gap ~2.56pp.
- Offline H5: seed-level **4/5** ρ>0.3 but pooled ρ≈0.23 (below 0.3). Still synthetic; live GPQA required for READY.
- No cloud API keys in this environment as of 2026-08-04 — no new paid evidence this tick.
- Expect Condition D token cost ≥ B if CABS/committee calls are counted; primary win may be gens-to-threshold or cost-to-threshold, not raw final accuracy.
- Small eval subsets and seed counts limit statistical power; avoid overclaiming.

## Code pins

| Component | Note |
|-----------|------|
| Contradiction-scoped bias | `SIA/sia/evolution/cabs_bridge.py::load_mutation_bias` |
| Singleton bias skip | `load_mutation_bias` requires ≥2 distinct candidates (Tick 10) |
| Fitness-weighted bias order | `load_mutation_bias` + exponential rank-weighted `_biased_choice` |
| Preferred-allele anchoring | `SIA/sia/evolution/operators.py::_biased_choice` (Tick 10) |
| Scoped feedback DNA targets | `SIA/sia/evolution/cabs_bridge.py::load_cabs_agenda` |
| Biased mutate | `SIA/sia/evolution/operators.py::mutate` |
| Condition D inline analyze | `SIA/sia/evolution/cabs_inline.py` + `--cabs-inline` |
| H5 epistemic_value series | `belief_store/epistemic_value.jsonl` (age + flow + steering opportunity) |
| Dry-run DNA fitness | `SIA/sia/evolution/dry_run.py::deterministic_fitness` (additive latent as of Tick 9) |
| Metrics / H5–H2 helpers | `scripts/epistemic_results.py` (gens-to-30% wins) |
| Offline B vs D + case study | `scripts/offline_bvd_case_study.py` |
| H2 unit test | `SIA/tests/test_cabs_bridge.py` |
| Inline unit test | `SIA/tests/test_cabs_inline.py` |
| G1 dry-run Condition D | `SIA/tests/test_cabs_inline_dry_run.py` |
| Epistemic metrics tests | `SIA/tests/test_epistemic_results.py` |
