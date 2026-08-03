# ICML Thesis 1 — Ready checklist

**STATUS: IN_PROGRESS**

Do not set STATUS: READY until every item below is checked and evidence paths are real.

## Criteria

### 1. PRIMARY — Condition D beats B
- [ ] D beats B on ≥3/5 seeds for gens-to-threshold (25% or 30%), **or**
- [ ] D beats B on ≥3/5 seeds for cost-to-threshold (≥15% fewer tokens/calls), **or**
- [ ] Non-trivial mean final accuracy gap (not ~1pp noise)
- Evidence: _pending live runs_ → `docs/paper_artifacts.md` Table 1

### 2. MECHANISM — H2 or case study
- [x] Unit-level H2: contradiction bias skews DNA vs uniform (`SIA/tests/test_cabs_bridge.py`)
- [ ] Live-run H2 DNA trait skew under contradiction bias, **or**
- [ ] Documented case study (tie → contradiction → different DNA/code → fitness lift) with artifacts
- Evidence: unit pass; live artifacts pending

### 3. VALIDITY — H5
- [ ] Spearman ρ (`epistemic_value_t` vs `Δfitness_t+1`) > 0.3
- Evidence: _pending_

### 4. PAPER
- [ ] Figure 1 (learning curves B vs D)
- [ ] Figure 2 (mechanism / H2 or case study)
- [ ] Table 1 (primary metrics by seed)
- [ ] Table 2 (H2/H5 / cost)
- [ ] Abstract draft
- [ ] Limitations (honest: prior gaps, token cost, small-N)
- [ ] Reproducible run IDs listed in `docs/paper_artifacts.md`

## Gate tracker (Section 21.5)

| Gate | Status |
|------|--------|
| G0 mechanism unit tests | **PASS** (2026-08-03) |
| G1 dry-run Condition D | FAIL / not run (`--cabs-inline` missing) |
| G2 smoke GPQA subset | BLOCKED (no API keys) |
| G3 pilot B vs D | NOT STARTED |
| G4 5-seed + metrics | NOT STARTED |
| G5 paper pack | NOT STARTED |
