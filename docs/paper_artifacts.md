# ICML paper artifacts

**Status:** scaffold only (2026-08-03). No publishable figures/tables yet.

## Abstract (draft — do not claim READY)

We study whether a Contradiction-Aware Belief System (CABS) improves sample efficiency of population-based Darwinian self-improvement. Fitness-only evolution (Condition B) is compared to epistemic-full steering (Condition D: beliefs → contradictions → research questions → biased mutation / scoped feedback). **Results pending multi-seed GPQA subset runs.** Mechanism claim requires measurable DNA trait skew under contradiction bias (H2) and predictive validity of epistemic value for next-step fitness gain (H5, Spearman ρ > 0.3).

## Reproducible run IDs

| Condition | Seed | Run ID | Status |
|-----------|------|--------|--------|
| D epistemic_full (dry-run G1) | 42 | 1401 | **PASS** harness (no API; synthetic GPQA fixture; gitignored `runs/run_1401`) |
| B darwinian-only | — | — | none yet (live) |
| D epistemic_full | — | — | none yet (live) |

Reserve unused integer IDs; never overwrite. Next live IDs suggested: B `1201+`, D `1301+` (Section 21.7).

## Table 1 — Primary (B vs D)

_Empty until G3/G4._

| Seed | B final acc | D final acc | B gens@25% | D gens@25% | B tokens | D tokens | Winner |
|------|-------------|-------------|------------|------------|----------|----------|--------|

## Table 2 — Mechanism / validity

| Metric | Value | Pass? |
|--------|-------|-------|
| H2 trait skew (live API) | — | — |
| H2 dry-run scoped bias (G1) | memory∈{failure_based,none}; tool_strategy∈{aggressive,minimal}; ≠ full enums | yes (dry-run) |
| H2 unit skew test | pass (2026-08-03) | yes (unit) |
| H5 Spearman ρ | — | need > 0.3 (dry-run epi series present; need Δfitness) |

## Figures

| Fig | Description | Path |
|-----|-------------|------|
| 1 | Accuracy / cost curves B vs D | `docs/figures/fig1_learning_curves.png` (missing) |
| 2 | H2 DNA skew or case-study chain | `docs/figures/fig2_mechanism.png` (missing) |

## Limitations (honest, keep updated)

- Mutation bias was previously a no-op (full enum); fixed and **validated on dry-run G1** (`run_1401`) but **not yet on live GPQA**.
- `--cabs-inline` + G1 dry-run PASS (2026-08-04); G2–G4 live B vs D evidence still missing.
- No cloud API keys in this environment as of 2026-08-04 — no new paid evidence this tick.
- Expect Condition D token cost ≥ B if CABS/committee calls are counted; primary win may be gens-to-threshold or cost-to-threshold, not raw final accuracy.
- Small eval subsets and seed counts limit statistical power; avoid overclaiming.

## Code pins

| Component | Note |
|-----------|------|
| Contradiction-scoped bias | `SIA/sia/evolution/cabs_bridge.py::load_mutation_bias` |
| Biased mutate | `SIA/sia/evolution/operators.py::mutate` |
| Condition D inline analyze | `SIA/sia/evolution/cabs_inline.py` + `--cabs-inline` |
| H5 epistemic_value series | `belief_store/epistemic_value.jsonl` (written by inline hook) |
| H2 unit test | `SIA/tests/test_cabs_bridge.py` |
| Inline unit test | `SIA/tests/test_cabs_inline.py` |
| G1 dry-run Condition D | `SIA/tests/test_cabs_inline_dry_run.py` |
