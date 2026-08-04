# ICML Thesis 1 — Ready checklist

**STATUS: IN_PROGRESS**

Do not set STATUS: READY until every item below is checked and evidence paths are real.

## Criteria

### 1. PRIMARY — Condition D beats B
- [ ] D beats B on ≥3/5 seeds for gens-to-threshold (25% or 30%), **or**
- [ ] D beats B on ≥3/5 seeds for cost-to-threshold (≥15% fewer tokens/calls), **or**
- [ ] Non-trivial mean final accuracy gap (not ~1pp noise)
- Evidence: offline synthetic pilot `1510–1514` vs `1520–1524` (Tick 10) — D final wins **2/5** (>1pp margin), gens30 wins **2/5**, mean final gap ~**2.56pp** (improved from Tick 9 ~0.2pp; still not ≥3/5 seed wins). **Not** live GPQA; do not count for READY. Live → `docs/paper_artifacts.md` Table 1

### 2. MECHANISM — H2 or case study
- [x] Unit-level H2: contradiction bias skews DNA vs uniform (`SIA/tests/test_cabs_bridge.py`)
- [x] Dry-run in-loop H2 path: scoped mutation bias after `--cabs-inline` (`runs/run_1401`, `SIA/tests/test_cabs_inline_dry_run.py`)
- [x] Scoped feedback injects same DNA candidates as bias (`load_cabs_agenda` + `test_cabs_agenda_includes_scoped_dna_feedback_targets`)
- [x] Fitness-weighted bias: higher-fitness contradiction side ranked first + rank-weighted mutate (`test_mutation_bias_prefers_higher_fitness_side`)
- [x] Preferred-allele anchoring + singleton-bias skip (Tick 10) — `operators._biased_choice` + `load_mutation_bias` len≥2 gate
- [x] Documented case study (tie → contradiction → different DNA → fitness lift) with artifacts — offline dry-run `docs/case_study_offline.md` + `run_1520` (`selective` preferred → gen2 share 1.0; lift +0.0866)
- [ ] Live API-run H2 DNA trait skew under contradiction bias
- Evidence: unit + dry-run G1 + scoped feedback + fitness-weighted order + preferred anchoring + offline case study; live GPQA still pending (no API keys)

### 3. VALIDITY — H5
- [ ] Spearman ρ (`epistemic_value_t` vs `Δfitness_t+1`) > 0.3 on live / publishable runs
- Evidence: offline multi-seed Condition D `1520–1524` → ρ>0.3 on **4/5** seeds (0.5 / 0.5 / −1.0 / 0.5 / 0.5); pooled ρ≈**0.23** (n=15; below 0.3 — seed-level pass, pooled soft). Still **not** live GPQA.

### 4. PAPER
- [x] Figure 1 draft (offline B vs D learning curves) — `docs/figures/fig1_learning_curves.png`
- [x] Figure 2 draft (H2 DNA histogram / case-study support) — `docs/figures/fig2_mechanism.png`
- [ ] Table 1 (primary metrics by seed) — offline stub filled; live empty
- [ ] Table 2 (H2/H5 / cost) — partial offline; live empty
- [x] Abstract draft (scaffold in `docs/paper_artifacts.md` — live results TBD)
- [x] Limitations (honest; kept updated in `docs/paper_artifacts.md`)
- [ ] Reproducible **live** run IDs listed in `docs/paper_artifacts.md` (dry-run IDs present; live pending)
- Metrics helper: `scripts/epistemic_results.py`; offline pilot: `scripts/offline_bvd_case_study.py`

## Gate tracker (Section 21.5)

| Gate | Status |
|------|--------|
| G0 mechanism unit tests | **PASS** (2026-08-03) |
| G1 dry-run Condition D | **PASS** (2026-08-04) — `run_1401` + `test_cabs_inline_dry_run.py` |
| G2 smoke GPQA subset | BLOCKED (no API keys) |
| G3 pilot B vs D | Offline synthetic pilot refreshed (Tick 10); **live** G3 NOT STARTED |
| G4 5-seed + metrics | NOT STARTED (live) |
| G5 paper pack | PARTIAL (offline figs + case study + H5); live pack NOT STARTED |
