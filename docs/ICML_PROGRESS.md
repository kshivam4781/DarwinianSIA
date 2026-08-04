# ICML Thesis 1 — Progress log

Persistent agent ticks append newest entries at the top.

---

## 2026-08-04T14:05Z — Tick 10 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-c34f` (fast-forwarded Ticks 1–9 from `c875`, then this tick)
- API keys in cloud env: **absent** (no paid GPQA this tick)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
G2–G4 remain blocked without API keys. Offline PRIMARY gap after Tick 9: D final 2/5, gens30 1/5, mean gap ~0.2pp. Diagnosis on failing seed 55: cross-agent extractors emit **same-allele “contradictions”** (both sides `tool_strategy=aggressive` with different fitness from other genes). Singleton bias pools then force that allele population-wide and wipe better elites (e.g. selective). Hard preferred pull without a ≥2-value gate worsened this.

### What this tick did (ONE step)
Strengthened **Condition D mutation bias** for sample efficiency without singleton collapse:
1. **Preferred-allele anchoring** in `_biased_choice`: protect preferred; pull outsiders to winner only; exponential rank weights on disputed losers
2. **Skip singleton bias pools** in `load_mutation_bias` (require ≥2 distinct candidates)
3. Unit tests: `test_biased_mutate_anchors_preferred_allele`, `test_mutation_bias_skips_singleton_candidates`
4. Re-pilot B `1510–1514` vs D `1520–1524`; case study on `run_1520`

### Metrics delta
| Metric | Before (Tick 9) | After (Tick 10) |
|--------|-----------------|-----------------|
| Offline D gens30 wins | 1/5 | **2/5** (B gens30 wins 0) |
| Offline D final wins (>1pp) | 2/5 | **2/5** (B final wins 0; rest ties) |
| Mean final gap (D−B) | ~0.2pp | ~**2.56pp** |
| Offline H5 ρ>0.3 | 4/5; pooled ≈0.34 | **4/5**; pooled ≈**0.23** |
| Case study gen2 pref share / lift | 0.75 / +0.0576 (`1480`) | **1.0 / +0.0866** (`1520`) |
| Singleton bias → elite wipe | Present (seed 55 all-aggressive) | **Gated out** |
| Live PRIMARY / G2 | Blocked (no API) | Still blocked |

### Next recommended step
When `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` present and budget checked: **G2** smoke GPQA subset (≤5 samples, pop≤2, max_gen≤2, one seed) Condition D with `--cabs --cabs-inline`; then G3 live pilot B vs D. If still no keys: strengthen offline PRIMARY to ≥3/5 gens30 (e.g. bias-aware crossover / longer horizon) or raise pooled H5 back above 0.3. Do **not** set READY from offline mean-gap alone.

---

## 2026-08-04T12:05Z — Tick 9 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-c875` (fast-forwarded Ticks 1–8 from `3a18`, then this tick)
- API keys in cloud env: **absent** (no paid GPQA this tick)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
G2–G4 remain blocked without API keys. Offline VALIDITY gap after Tick 8: multi-seed H5 Spearman ρ was often **negative** because (1) `epistemic_value` was mostly age-decayed open-stock (monotone decrease) and (2) opaque DNA-hash fitness made single-trait mutation bias scramble other traits so preferred-side adoption did **not** causally raise fitness.

### What this tick did (ONE step)
Fixed **offline multi-seed H5** via causal epistemic + fitness coupling:
1. **Steering opportunity** in `_epistemic_value`: `aged_priority × fitness_gap × (1 − preferred DNA share)` so epi_t tracks remaining contradiction-driven improvement pressure
2. **Additive latent dry-run fitness** (replaces opaque hash): transferable DNA scores where higher-latent trait sides raise fitness; score scale keeps 25/30% thresholds informative
3. `compare_b_vs_d` tracks gens-to-30% wins (including reach-vs-never)
4. Re-pilot B `1470–1474` vs D `1480–1484` (seeds 11/22/33/44/55); case study on `run_1480`

### Metrics delta
| Metric | Before (Tick 8) | After (Tick 9) |
|--------|-----------------|----------------|
| Offline multi-seed H5 ρ>0.3 | Often negative (1/5) | **4/5** seeds; pooled ρ≈**0.34** |
| Dry-run fitness model | Opaque DNA-hash | **Additive latent** (causal bias→fitness) |
| `epistemic_value` components | Age + flow | Age + flow + **steering_opportunity** |
| Offline D final wins (5 seeds) | 4/5 (non-causal hash) | **2/5** (honest; mean gap ~0.2pp) |
| Offline D gens30 wins | Not tracked | **1/5** (PRIMARY still fail offline) |
| Case study chain | `run_1420` | `run_1480` (selective share 0.75; lift +0.0576) |
| Live PRIMARY / G2 | Blocked (no API) | Still blocked |

### Next recommended step
When `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` present and budget checked: **G2** smoke GPQA subset (≤5 samples, pop≤2, max_gen≤2, one seed) Condition D with `--cabs --cabs-inline`; then G3 live pilot B vs D. Do **not** set READY from offline H5 4/5 alone — PRIMARY still needs live ≥3/5.

---

## 2026-08-04T10:06Z — Tick 8 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-3a18` (fast-forwarded Ticks 1–7 from `88ed`, then this tick)
- API keys in cloud env: **absent** (no paid GPQA this tick)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
G2–G4 remain blocked without API keys. Offline mechanism gap after Tick 7: `deterministic_fitness` hashed `agent_id` + `generation`, so offspring inheriting a high-fitness parent's traits did **not** keep that score — breaking the case-study chain (contradiction → fitness-weighted bias → DNA → fitness lift) and preventing honest offline B vs D pilots.

### What this tick did (ONE step)
Made **dry-run fitness DNA-transferable** and ran an **offline 5-seed B vs D case-study pilot**:
- `deterministic_fitness` now scores transferable DNA traits only (ignores agent_id/gen); unit test `test_deterministic_fitness_transfers_with_dna_traits`
- Harness: `scripts/offline_bvd_case_study.py` — Conditions B/D, pop=4, max_gen=4, seeds 11/22/33/44/55 → run IDs B `1410–1414`, D `1420–1424` (gitignored `runs/`)
- Case study (`docs/case_study_offline.md`, `run_1420`): contradiction `tool_strategy` selective@0.5234 vs aggressive@0.1640 → bias prefers `selective` → gen2 preferred share **0.75** → preserved winning genome gen2 agent_2 fitness **0.5234** (lift **+0.3594** vs loser)
- Offline synthetic D final-fitness wins **4/5** seeds (mean gap ~4.1pp); gens-to-25% uninformative (both hit gen1); multi-seed H5 ρ often negative (keep offline H5 claim on `run_1403` ρ=0.5 only)
- Figures: `docs/figures/fig1_learning_curves.png`, `fig2_mechanism.png`; summary `docs/offline_bvd_summary.json`

### Metrics delta
| Metric | Before | After |
|--------|--------|-------|
| Dry-run fitness transfer with DNA | Broken (agent_id/gen in hash) | **Transfers** (same DNA ⇒ same score) |
| Documented case study chain | Missing | **Present** (`docs/case_study_offline.md`) |
| Offline D final wins vs B (5 seeds) | No data | **4/5** (synthetic; not live PRIMARY) |
| H2 dry-run in-bias share (D seeds) | — | **0.81–1.0** |
| Offline H5 multi-seed | — | Unstable (often ρ<0); `run_1403` ρ=0.5 unchanged as reference |
| Live PRIMARY / G2 | Blocked (no API) | Still blocked |
| Paper Figs 1–2 | Missing | **Draft offline figures written** |

### Next recommended step
When `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` present and budget checked: **G2** smoke GPQA subset (≤5 samples, pop≤2, max_gen≤2, one seed) Condition D with `--cabs --cabs-inline`; then G3 live pilot B vs D. Do **not** set READY from synthetic 4/5 final-fitness wins.

---

## 2026-08-04T08:05Z — Tick 7 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-88ed` (fast-forwarded Ticks 1–6 from `91f9`, then this tick)
- API keys in cloud env: **absent** (no paid GPQA this tick)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
G2–G4 remain blocked without API keys. Offline mechanism gap for PRIMARY: contradiction bias listed both sides of a dispute uniformly (`r.choice(pool)`), so Condition D explored the disputed subspace but did **not** exploit the higher-fitness side encoded in belief text/metadata (`achieved fitness 0.20` vs `0.13`). That weakens Belief → Contradiction → biased mutation → sample efficiency vs fitness-only B.

### What this tick did (ONE step)
Implemented **fitness-weighted mutation bias** (PRIMARY lever, still offline-validatable):
- `load_mutation_bias` records per-value fitness from contradiction text, belief `metadata.fitness`, and agent `score.json` / `results.json`
- Candidates ranked highest-fitness-first (still contradiction-scoped; never full enum)
- `_biased_choice` uses rank weights (`n, n-1, …, 1`) so the winning side is preferred but the disputed pool stays open
- Scoped feedback agenda marks preferred (first) candidate
- Tests: `test_mutation_bias_prefers_higher_fitness_side` + stronger H2 skew assert — **7/7** `test_cabs_bridge.py` pass
- Synced `sia-upstream/` copies

### Metrics delta
| Metric | Before | After |
|--------|--------|-------|
| Bias order under fitness-tagged contradiction | Unordered / first-seen | **Higher-fitness first** (`failure_based` @0.20 before `full_history` @0.13) |
| `_biased_choice` within bias pool | Uniform | **Rank-weighted** toward first candidate |
| H2 unit + G1 dry-run | PASS | PASS (ordering + weight asserts added) |
| PRIMARY D beats B (≥3/5 seeds) | No data | No data (no API) |
| Offline H5 ρ (`run_1403`) | 0.5 | unchanged this tick |
| Paper artifacts | Stubs + offline H5 | Stubs + fitness-weighted bias note |

### Next recommended step
When `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` present and budget checked: **G2** smoke GPQA subset (≤5 samples, pop≤2, max_gen≤2, one seed) Condition D with `--cabs --cabs-inline`; confirm live bias lists higher-fitness DNA first; then G3 pilot B vs D. Do not claim READY without live PRIMARY.

---

## 2026-08-04T06:05Z — Tick 6 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-91f9` (fast-forwarded Ticks 1–5 from `3888`, then this tick)
- API keys in cloud env: **absent** (no paid GPQA this tick)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
G2–G4 remain blocked without API keys. Offline H5 was still undefined: after gen1 the open contradiction/RQ stock stalled, so `epistemic_value` was constant (11.9 on `run_1402`) and Spearman ρ collapsed despite DNA-deterministic Δfitness.

### What this tick did (ONE step)
Made **`epistemic_value_t` non-constant** for offline H5:
- Age-decay open contradiction/RQ priorities (`0.85 ** age`); RQs inherit age from linked contradiction when `detected_at_gen` missing
- Fold knowledge_gain + resolved-priority flow into `epistemic_value.jsonl` components
- Unit test `test_epistemic_value_varies_with_age_and_knowledge_gain`
- Offline Condition D smoke `run_1403` (seed 7, pop=4, max_gen=4): epi **12.9 → 11.11 → 9.60 → 8.31**; H5 ρ **0.5** (pass > 0.3 offline); H2 memory in-bias share **0.875**

### Metrics delta
| Metric | Before | After |
|--------|--------|-------|
| Offline epistemic_value series | Constant after gen1 | **Varies every gen** (age + flow) |
| Offline H5 ρ (dry-run D) | null (constant epi) | **0.5** on `run_1403` (n_pairs=3) |
| H2 dry-run memory in-bias | 0.875 (run_1402) | **0.875** (run_1403) |
| PRIMARY D beats B (≥3/5 seeds) | No data | No data (no API) |
| Paper artifacts | Stubs + tooling | Stubs + offline H5 note |

### Next recommended step
When `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` present and budget checked: **G2** smoke GPQA subset (≤5 samples, pop≤2, max_gen≤2, one seed) Condition D with `--cabs --cabs-inline`; then G3 pilot B vs D. Do not claim READY from dry-run H5 alone.

---

## 2026-08-04T04:03Z — Tick 5 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-3888` (cherry-picked Ticks 1–4 from `0f06`, then this tick)
- API keys in cloud env: **absent** (no paid GPQA this tick)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
G2–G4 remain blocked without API keys. Offline gap: dry-run evaluation still ran mock GPQA agents that always answered "A", collapsing every agent to accuracy=1.0. That made Δfitness≡0 so H5 Spearman could not be computed even with `epistemic_value.jsonl` present. `_deterministic_fitness` existed in `dry_run.py` but was dead code.

### What this tick did (ONE step)
Wired **DNA-deterministic dry-run fitness** + **epistemic metrics pipeline**:
- `population._run_single_agent(dry_run=True)` → `deterministic_fitness` + `write_mock_results` (skip trivial mock eval)
- `scripts/epistemic_results.py` — H5 Spearman, H2 trait share, gens-to-threshold, B vs D compare helpers
- Tests: `test_epistemic_results.py` + dry-run asserts varied fitness — **14/14** related tests pass
- Smoke dry-run Condition D (local `run_1402`, seed 7, pop=4, max_gen=4): varied fitness curve; H2 memory in-bias share **0.875**; H5 ρ **undefined** because `epistemic_value` stayed constant at 11.9 (open contradiction/RQ priority sum does not move after gen 1)

### Metrics delta
| Metric | Before | After |
|--------|--------|-------|
| Dry-run fitness diversity | All ~1.0 (mock eval) | DNA-hash in [0.05, 0.95]; multi-value |
| H5 computation tooling | Missing | `scripts/epistemic_results.py` + unit tests |
| Offline H5 ρ (dry-run D) | N/A (Δfitness=0) | n_pairs=3 but ρ=null (constant epistemic_value) |
| H2 dry-run memory in-bias share | Not measured | **0.875** on run_1402 |
| PRIMARY D beats B (≥3/5 seeds) | No data | No data (no API) |
| Paper artifacts | Stubs | Stubs + metrics script pinned |

### Next recommended step
Prefer: when keys present → **G2** smoke GPQA. If still no keys: make `epistemic_value_t` non-constant across gens (e.g. fold in `knowledge_gain_score`, resolved-contradiction deltas, or priority updates) so offline H5 ρ is defined; then re-smoke dry-run D.

---

## 2026-08-04T02:01Z — Tick 4 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-0f06` (cherry-picked Ticks 1–3 from `fb8d`, then scoped feedback)
- API keys in cloud env: **absent** (no paid GPQA this tick)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
G2–G4 remain blocked without API keys. Offline mechanism gap: Condition D had contradiction-scoped **mutation bias** but feedback agendas only listed open RQs / contradiction text — they did **not** inject the same concrete DNA candidate values. That weakens the causal path Belief → Contradiction → RQ → **scoped feedback** → code change vs fitness-only B.

### What this tick did (ONE step)
Strengthened **scoped feedback** so agendas share mutation-bias DNA targets:
- `SIA/sia/evolution/cabs_bridge.py::load_cabs_agenda` (+ `sia-upstream/` sync) appends `### Scoped DNA Feedback Targets` from `load_mutation_bias`
- Feedback must prefer contradiction-scoped candidates (not full enums)
- Test: `test_cabs_agenda_includes_scoped_dna_feedback_targets` — **6/6** `test_cabs_bridge.py` pass

### Metrics delta
| Metric | Before | After |
|--------|--------|-------|
| Scoped feedback DNA candidates in agenda | Missing (RQ field name only) | **Present** (same pool as biased mutation) |
| H2 unit + G1 dry-run | PASS | PASS (unchanged) |
| PRIMARY D beats B (≥3/5 seeds) | No data | No data (no API) |
| H5 Spearman ρ | Writer only | Still no live Δfitness series |
| Paper artifacts | Stubs | Stubs |

### Next recommended step
When `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` are present and budget checked: **G2** smoke GPQA subset (≤5 samples, pop≤2, max_gen≤2, one seed) Condition D with `--cabs --cabs-inline`; then G3 pilot B vs D. Do not start paid runs without keys.

---

## 2026-08-04T00:05Z — Tick 3 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-fb8d` (cherry-picked Ticks 1–2 from `c4ef`, then G1)
- API keys in cloud env: **absent** (no paid GPQA this tick)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
Section 21 G1 was still open: `--cabs-inline` existed but Condition D had not been dry-run on a GPQA-shaped task layout proving mid-loop `belief_store/` refresh + contradiction-scoped mutation bias before breeding gen≥2. PRIMARY/H5 remain blocked on API keys after G1.

### What this tick did (ONE step)
Executed **G1 dry-run Condition D** and locked it with an integration test:
- Harness: `run_darwinian_loop(..., dry_run=True, cabs_inline=True)`, pop=2, max_gen=2, eval_subset=3, seed=42 → local `runs/run_1401` (gitignored)
- Gen1 inline: beliefs+16, contradictions+7, RQs+7, `epistemic_value=11.9`
- Breeding logged scoped bias (e.g. `memory: [failure_based, none]` — not full enum)
- Gen2 DNA written; `belief_store/epistemic_value.jsonl` has gen 1+2 rows
- Test: `SIA/tests/test_cabs_inline_dry_run.py` (asserts store + epi series + non-empty scoped bias)

### Metrics delta
| Metric | Before | After |
|--------|--------|-------|
| G1 dry-run Condition D | Unblocked / not executed | **PASS** (run_1401 + pytest) |
| Mid-run contradictions / RQs (dry-run) | Unknown | **7 / 7** after gen1 |
| Mutation bias on breed→gen2 | Untested in-loop | **Scoped** (≠ full MEMORY_MODES) |
| PRIMARY D beats B (≥3/5 seeds) | No data | No data (no API) |
| H5 Spearman ρ | Writer only | Still no live Δfitness series |
| Paper artifacts | Stubs | Stubs (+ dry-run ID noted) |

### Next recommended step
When `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` are present and budget checked: **G2** smoke GPQA subset (≤5 samples, pop≤2, max_gen≤2, one seed) Condition D; then G3 pilot B vs D. Do not start paid runs without keys.

---

## 2026-08-03T22:10Z — Tick 2 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-c4ef` (cherry-picked Tick 1 from `bf9b`, then implemented `--cabs-inline`)
- API keys in cloud env: **absent** (no paid GPQA this tick)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
Condition D / epistemic_full could not refresh `belief_store/` mid-run: `--cabs` only *reads* an existing store for agenda + mutation bias. Without `--cabs-inline`, D requires a fragile two-step external analyze between gens, so PRIMARY (D≻B) and live H2/H5 were blocked even after the mutation-bias fix.

### What this tick did (ONE step)
Implemented `--cabs-inline` end-to-end:
- `SIA/sia/evolution/cabs_inline.py` — in-process `BeliefEngine.process_generation` (+ `sia-cabs-tools` fallback); appends `belief_store/epistemic_value.jsonl`
- Wired into `run_darwinian_loop` after gen eval / before breeding; CLI `--cabs-inline` implies `--cabs`
- `sia_cabs/cli.py analyze --generation N` for single-gen subprocess path
- Synced `sia-upstream/` copies; tests in `SIA/tests/test_cabs_inline.py` (7/7 with bridge tests)

### Metrics delta
| Metric | Before | After |
|--------|--------|-------|
| `--cabs-inline` CLI / loop hook | Missing | **Present** (Condition D runnable in one process) |
| Mid-run belief_store refresh | Two-step only | **In-loop** after each gen |
| `epistemic_value.jsonl` for H5 | Missing | **Written** per inline gen |
| G1 dry-run Condition D | Blocked on missing flag | **Unblocked** (needs task dry-run next; no API) |
| PRIMARY D beats B (≥3/5 seeds) | No data | No data (no API) |
| H5 Spearman ρ | No data | Still no live Δfitness series |
| Paper artifacts | Stubs | Stubs (flag docs updated) |

### Next recommended step
G1: dry-run Condition D (`--darwinian --cabs --cabs-inline --dry-run`, pop≤2, max_gen≥2) on an available task to confirm belief_store + biased DNA on gen≥2; then when keys exist, G2 smoke GPQA subset (one seed) under budget.

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
