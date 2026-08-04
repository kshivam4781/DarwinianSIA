# ICML paper artifacts

**Status:** offline mechanism pack + synthetic B vs D pilot (2026-08-04 Tick 8). No publishable **live** GPQA figures/tables yet.

## Abstract (draft — do not claim READY)

We study whether a Contradiction-Aware Belief System (CABS) improves sample efficiency of population-based Darwinian self-improvement. Fitness-only evolution (Condition B) is compared to epistemic-full steering (Condition D: beliefs → contradictions → research questions → fitness-weighted biased mutation / scoped feedback). Offline dry-run pilots with DNA-transferable synthetic fitness show Condition D winning final fitness on 4/5 seeds and a concrete case study (contradiction → preferred DNA → preserved winning genome). **Live multi-seed GPQA subset results pending.** Mechanism claim requires measurable DNA trait skew under contradiction bias (H2) and predictive validity of epistemic value for next-step fitness gain (H5, Spearman ρ > 0.3) on live runs.

## Reproducible run IDs

| Condition | Seed | Run ID | Status |
|-----------|------|--------|--------|
| D epistemic_full (dry-run G1) | 42 | 1401 | **PASS** harness (no API; synthetic GPQA fixture; gitignored `runs/run_1401`) |
| D epistemic_full (dry-run H5 smoke) | 7 | 1402 | Offline only — pre-fix; constant epistemic_value=11.9 → ρ undefined; H2 memory in-bias 0.875 |
| D epistemic_full (dry-run H5 after epi fix) | 7 | 1403 | Offline — age-weighted + flow epi **12.9→8.31**; H5 ρ **0.5** (pass); H2 memory in-bias **0.875**; not live GPQA |
| B darwinian-only (offline pilot) | 11/22/33/44/55 | 1410–1414 | Synthetic DNA-hash fitness; gitignored `runs/` |
| D epistemic_full (offline pilot) | 11/22/33/44/55 | 1420–1424 | Synthetic; case study on `1420`; D final wins 4/5 |
| B darwinian-only | — | — | none yet (live) |
| D epistemic_full | — | — | none yet (live) |

Reserve unused integer IDs; never overwrite. Next live IDs suggested: B `1201+`, D `1301+` (Section 21.7).

## Table 1 — Primary (B vs D)

### Offline synthetic pilot (Tick 8 — not PRIMARY)

| Seed | B final | D final | B gens@25% | D gens@25% | Winner (final) |
|------|---------|---------|------------|------------|----------------|
| 11 | 0.7828 | 0.8122 | 1 | 1 | D |
| 22 | 0.8866 | 0.9273 | 1 | 1 | D |
| 33 | 0.9267 | 0.8061 | 1 | 1 | B |
| 44 | 0.7118 | 0.9170 | 1 | 1 | D |
| 55 | 0.8801 | 0.9311 | 1 | 1 | D |

Mean final: B ≈ 0.838, D ≈ 0.879 (gap ~4.1pp synthetic). Gens-to-25% uninformative (threshold hit at gen1 for both). Source: `docs/offline_bvd_summary.json`.

### Live GPQA

| Seed | B final acc | D final acc | B gens@25% | D gens@25% | B tokens | D tokens | Winner |
|------|-------------|-------------|------------|------------|----------|----------|--------|
| — | — | — | — | — | — | — | — |

## Table 2 — Mechanism / validity

| Metric | Value | Pass? |
|--------|-------|-------|
| H2 trait skew (live API) | — | — |
| H2 dry-run scoped bias (G1) | memory∈{failure_based,none}; tool_strategy∈{aggressive,minimal}; ≠ full enums | yes (dry-run) |
| H2 dry-run in-bias share (run_1402/1403) | memory in-bias **0.875** | informative (dry-run) |
| H2 offline pilot D (Tick 8) | in-bias share **0.81–1.0** across seeds 11–55 | informative (dry-run) |
| H2 unit skew test | pass (2026-08-03) | yes (unit) |
| Fitness-weighted bias order | higher-fitness side first; rank-weighted mutate | yes (unit, Tick 7) |
| Case study chain | `docs/case_study_offline.md` (`run_1420`) | yes (offline) |
| H5 Spearman ρ | offline `run_1403` ρ **0.5** (n=3); Tick-8 multi-seed often ρ<0; live pending | offline yes on 1403 only; live need > 0.3 |

## Figures

| Fig | Description | Path |
|-----|-------------|------|
| 1 | Accuracy / cost curves B vs D (offline draft) | `docs/figures/fig1_learning_curves.png` |
| 2 | H2 DNA skew / case-study support (offline draft) | `docs/figures/fig2_mechanism.png` |

## Case study (offline)

See `docs/case_study_offline.md`. Summary: gen1 contradiction on `tool_strategy` (`selective`@0.5234 vs `aggressive`@0.1640) → fitness-weighted bias prefers `selective` → gen2 preferred share 0.75 → gen2 agent_2 preserves winning genome at 0.5234 (lift +0.3594 vs loser).

## Limitations (honest, keep updated)

- Mutation bias was previously a no-op (full enum); fixed and **validated on dry-run G1** (`run_1401`) but **not yet on live GPQA**.
- Pre-Tick-7 bias treated both contradiction sides uniformly; now fitness-weighted (unit-tested) but **unverified on live GPQA**.
- Scoped feedback now mirrors mutation-bias DNA candidates (2026-08-04); still untested on live rewrite quality.
- `--cabs-inline` + G1 dry-run PASS (2026-08-04); G2–G4 **live** B vs D evidence still missing.
- Dry-run fitness previously collapsed to 1.0 via mock eval; fixed 2026-08-04 with DNA-deterministic fitness. Tick 8: fitness is **DNA-transferable** (no agent_id/gen in hash) so offline case studies work. Still **not** live GPQA accuracy.
- Offline H5 on dry-run D (`run_1402`) had Δfitness but **constant** `epistemic_value` (11.9) → Spearman undefined. Fixed 2026-08-04 with age-weighted open priorities + knowledge_gain/resolution flow (`run_1403` ρ=0.5). Tick-8 five-seed offline H5 often **negative** — treat 1403 as a single-seed smoke, not multi-seed validity.
- Offline synthetic D final wins 4/5 with ~4pp mean gap — **informative for harness only**; gens-to-25% saturated at gen1; **not** a PRIMARY claim.
- No cloud API keys in this environment as of 2026-08-04 — no new paid evidence this tick.
- Expect Condition D token cost ≥ B if CABS/committee calls are counted; primary win may be gens-to-threshold or cost-to-threshold, not raw final accuracy.
- Small eval subsets and seed counts limit statistical power; avoid overclaiming.

## Code pins

| Component | Note |
|-----------|------|
| Contradiction-scoped bias | `SIA/sia/evolution/cabs_bridge.py::load_mutation_bias` |
| Fitness-weighted bias order | `load_mutation_bias` + rank-weighted `_biased_choice` (Tick 7) |
| Scoped feedback DNA targets | `SIA/sia/evolution/cabs_bridge.py::load_cabs_agenda` |
| Biased mutate | `SIA/sia/evolution/operators.py::mutate` |
| Condition D inline analyze | `SIA/sia/evolution/cabs_inline.py` + `--cabs-inline` |
| H5 epistemic_value series | `belief_store/epistemic_value.jsonl` (age-weighted open priorities + knowledge_gain/resolution flow) |
| Dry-run DNA fitness | `SIA/sia/evolution/dry_run.py::deterministic_fitness` (DNA-transferable as of Tick 8) |
| Metrics / H5–H2 helpers | `scripts/epistemic_results.py` |
| Offline B vs D + case study | `scripts/offline_bvd_case_study.py` |
| H2 unit test | `SIA/tests/test_cabs_bridge.py` |
| Inline unit test | `SIA/tests/test_cabs_inline.py` |
| G1 dry-run Condition D | `SIA/tests/test_cabs_inline_dry_run.py` |
| Epistemic metrics tests | `SIA/tests/test_epistemic_results.py` |
