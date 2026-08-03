# ICML Thesis 1 — Progress log

Persistent agent ticks append newest entries at the top.

---

## 2026-08-03T20:36Z — Tick 1 (first automation run)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Section 21: **created** this tick
- API keys in cloud env: **absent** (no paid GPQA this tick)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
Condition D’s causal mechanism was broken: `SIA/sia/evolution/cabs_bridge.py::load_mutation_bias` dumped the **full DNA trait enum** into the bias pool whenever an open RQ named a `dna_field`. That makes biased mutation statistically identical to Condition B (uniform Darwinian mutation), so PRIMARY (D≻B) and MECHANISM (H2 skew) could not pass even with perfect runs.

Secondary gaps (still open):
- `--cabs-inline` not implemented (Condition D / epistemic_full)
- No live B vs D runs / run artifacts
- H5 Spearman ρ not computable yet
- Paper Figs/Tables / abstract not written

### What this tick did (ONE step)
Fixed contradiction-scoped mutation bias + regression tests (H2 unit gate):
- `SIA/sia/evolution/cabs_bridge.py` (+ synced `sia-upstream/` copy)
- `SIA/tests/test_cabs_bridge.py` — asserts bias ≠ full enum; DNA-file path; mutate skew vs uniform
- Added Section 21 ICML protocol; scaffolded paper/gate/ready docs

### Metrics delta
| Metric | Before | After |
|--------|--------|-------|
| Mutation bias = full enum (bug) | Yes (D≈B) | **No** — candidates from contradiction DNA/beliefs |
| H2 unit skew test | Missing | **Pass** (`biased_mass == n`, > uniform) |
| PRIMARY D beats B (≥3/5 seeds) | No data | No data (no API) |
| H5 Spearman ρ | No data | No data |
| Paper artifacts | Missing | Stubs only |

### Next recommended step
Implement `--cabs-inline` in SIA darwinian loop (analyze + optional offline committee after each gen eval, before breeding) so Condition D can refresh `belief_store/` in-process; then G1 dry-run + G2 smoke when keys available.
