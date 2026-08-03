# ICML paper artifacts

**Status:** scaffold only (2026-08-03). No publishable figures/tables yet.

## Abstract (draft — do not claim READY)

We study whether a Contradiction-Aware Belief System (CABS) improves sample efficiency of population-based Darwinian self-improvement. Fitness-only evolution (Condition B) is compared to epistemic-full steering (Condition D: beliefs → contradictions → research questions → biased mutation / scoped feedback). **Results pending multi-seed GPQA subset runs.** Mechanism claim requires measurable DNA trait skew under contradiction bias (H2) and predictive validity of epistemic value for next-step fitness gain (H5, Spearman ρ > 0.3).

## Reproducible run IDs

| Condition | Seed | Run ID | Status |
|-----------|------|--------|--------|
| B darwinian-only | — | — | none yet |
| D epistemic_full | — | — | none yet |

Reserve unused integer IDs; never overwrite.

## Table 1 — Primary (B vs D)

_Empty until G3/G4._

| Seed | B final acc | D final acc | B gens@25% | D gens@25% | B tokens | D tokens | Winner |
|------|-------------|-------------|------------|------------|----------|----------|--------|

## Table 2 — Mechanism / validity

| Metric | Value | Pass? |
|--------|-------|-------|
| H2 trait skew (live) | — | — |
| H2 unit skew test | pass (2026-08-03) | yes (unit only) |
| H5 Spearman ρ | — | need > 0.3 |

## Figures

| Fig | Description | Path |
|-----|-------------|------|
| 1 | Accuracy / cost curves B vs D | `docs/figures/fig1_learning_curves.png` (missing) |
| 2 | H2 DNA skew or case-study chain | `docs/figures/fig2_mechanism.png` (missing) |

## Limitations (honest, keep updated)

- Mutation bias was previously a no-op (full enum); fixed in code but **not yet validated on live GPQA**.
- `--cabs-inline` is implemented (2026-08-03) but G1 dry-run / G2–G4 live B vs D evidence still missing.
- No cloud API keys in this environment as of 2026-08-03 — no new paid evidence this tick.
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
