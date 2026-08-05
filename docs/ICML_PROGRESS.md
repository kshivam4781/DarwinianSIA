# ICML Thesis 1 — Progress log

Persistent agent ticks append newest entries at the top.

---

## 2026-08-05T00:00Z — Tick 14 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-bb57` (fast-forwarded Ticks 1–13 from `cb6a`, then this tick)
- API keys in cloud env: **absent** (no paid GPQA this tick)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
G2–G4 remain blocked without API keys. Offline after Tick 13: final **3/5**, gens30 **0/5**, H5 **3/5**, mean gap ~1.66pp. Soft early mutate still let preferred DNA share hit **1.0 by gen2** — starving gens-to-threshold and limiting further H5 gains.

### What this tick did (ONE step)
Implemented **delay-all mutation bias until breeding from gen≥2** (fair mutate + fair XO on gen1→gen2; full CABS steering from gen≥2):
1. `breed_offspring(..., apply_mutation_bias=)` — when False, mutate is uniform even if bias dict is set
2. `population.py` sets `apply_mutation_bias = (current_gen >= 2)` (same gate as delayed XO / anchoring)
3. Unit test `test_breed_offspring_can_delay_all_mutation_bias`
4. Synced `sia-upstream/` copies
5. Re-pilot B `1610–1614` vs D `1620–1624`; case study on `run_1620`; refreshed figs

### Metrics delta
| Metric | Before (Tick 13) | After (Tick 14) |
|--------|------------------|-----------------|
| Offline D final wins (>1pp) | 3/5 | **4/5** (B final wins 1) |
| Offline D gens30 wins | 0/5 | **0/5** (B gens30 wins 1) — still fail |
| Mean final gap (D−B) | ~1.66pp | ~**3.34pp** — improved |
| Offline H5 ρ>0.3 | 3/5 | **3/5** (0.5 / −0.5 / −1.0 / 0.5 / 1.0) — no change in pass rate |
| Case study gen2 pref share / lift | 1.0 / +0.0646 (`1600`) | **0.5 / +0.0473** (`1620`) — collapse fixed |
| Delay-all mutation bias | Missing | **Present** (`apply_mutation_bias`) |
| Live PRIMARY / G2 | Blocked (no API) | Still blocked |

### Next recommended step
When `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` present and budget checked: **G2** smoke GPQA subset (≤5 samples, pop≤2, max_gen≤2, one seed) Condition D with `--cabs --cabs-inline`; then G3 live pilot B vs D. If still no keys: **longer horizon** offline re-pilot `max_gen≥6` (now that gen2 no longer collapses, later gens can show gens30 wins) targeting gens30 ≥3/5 and H5 ≥4/5 while keeping final ≥3/5. Do **not** set READY — live GPQA still required; offline gens30 still 0/5.

---

## 2026-08-04T20:05Z — Tick 13 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-cb6a` (fast-forwarded Ticks 1–12 from `e6d1`, then this tick)
- API keys in cloud env: **absent** (no paid GPQA this tick)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
G2–G4 remain blocked without API keys. Offline after Tick 12: final **3/5** but gens30 **0/5**, H5 **2/5**, mean gap ~0.9pp. Root cause: **mutation bias preferred-allele anchoring** collapses preferred DNA share to 1.0 by gen2 even when crossover bias is delayed — starving H5 steering opportunity and gens-to-threshold.

### What this tick did (ONE step)
Implemented **tempered early mutation bias** (soft rank-weighted mutate on gen1→gen2; full preferred-allele anchoring from gen≥2):
1. `_biased_choice(..., anchor_preferred=)` — soft mode samples disputed pool with exponential weights (no hard protect / outsider→preferred)
2. `mutate` / `breed_offspring(..., apply_mutation_anchor=)` forward the flag
3. `population.py` sets `apply_mutation_anchor = (current_gen >= 2)` (same gate as delayed XO bias)
4. Unit test `test_biased_mutate_can_soften_preferred_anchor`
5. Re-pilot B `1590–1594` vs D `1600–1604`; case study on `run_1600`

### Metrics delta
| Metric | Before (Tick 12) | After (Tick 13) |
|--------|------------------|-----------------|
| Offline D final wins (>1pp) | 3/5 | **3/5** (B final wins 2) |
| Offline D gens30 wins | 0/5 | **0/5** (B gens30 wins 2) — no change |
| Mean final gap (D−B) | ~0.9pp | ~**1.66pp** — improved, still soft |
| Offline H5 ρ>0.3 | 2/5 | **3/5** (0.5 / −0.5 / 0.5 / −0.5 / 0.5) — partial restore |
| Case study gen2 pref share / lift | 1.0 / +0.0554 (`1580`) | **1.0 / +0.0646** (`1600`) — case-study field still collapses by gen2 |
| Soft early mutation anchor | Missing | **Present** (`apply_mutation_anchor`) |
| Live PRIMARY / G2 | Blocked (no API) | Still blocked |

### Next recommended step
When `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` present and budget checked: **G2** smoke GPQA subset (≤5 samples, pop≤2, max_gen≤2, one seed) Condition D with `--cabs --cabs-inline`; then G3 live pilot B vs D. If still no keys: **longer horizon** `max_gen≥6` offline re-pilot (gives gen≥2 anchoring room after soft early breed) and/or delay **all** mutation bias until gen≥2 (not only anchoring), targeting gens30 ≥3/5 and H5 ≥4/5 while keeping final ≥3/5. Do **not** set READY — live GPQA still required; offline gens30 still 0/5.

---

## 2026-08-04T18:06Z — Tick 12 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-e6d1` (fast-forwarded Ticks 1–11 from `7466`, then this tick)
- API keys in cloud env: **absent** (no paid GPQA this tick)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
G2–G4 remain blocked without API keys. Offline after Tick 11: final **3/5** but gens30 **0/5** and H5 **2/5** (regressed vs Tick 10). Soft bias-aware XO was suspected of early over-collapse; Tick 11 next-step suggested delaying bias XO until gen≥2.

### What this tick did (ONE step)
Implemented **delayed bias-aware crossover** (fair XO on first breeding, soft bias XO from gen2→gen3+):
1. `breed_offspring(..., apply_crossover_bias=)` — mutation bias always on; crossover bias optional
2. `population.py` sets `apply_crossover_bias = (current_gen >= 2)`
3. Unit test `test_breed_offspring_can_delay_crossover_bias`
4. Re-pilot B `1570–1574` vs D `1580–1584`; case study on `run_1580`

### Metrics delta
| Metric | Before (Tick 11) | After (Tick 12) |
|--------|------------------|-----------------|
| Offline D final wins (>1pp) | 3/5 | **3/5** (B final wins 2) |
| Offline D gens30 wins | 0/5 | **0/5** (B gens30 wins 2) — no change |
| Mean final gap (D−B) | ~2.13pp | ~**0.9pp** — regression |
| Offline H5 ρ>0.3 | 2/5 | **2/5** (0.5 / −0.5 / −0.5 / −1.0 / 0.5) — no change |
| Case study gen2 pref share / lift | 1.0 / +0.0554 (`1560`) | **1.0 / +0.0554** (`1580`) |
| Finding | Soft XO from gen1 | **Mutation bias alone collapses preferred by gen2** — delaying XO is nearly a no-op at max_gen=4 |
| Live PRIMARY / G2 | Blocked (no API) | Still blocked |

### Next recommended step
When `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` present and budget checked: **G2** smoke GPQA subset (≤5 samples, pop≤2, max_gen≤2, one seed) Condition D with `--cabs --cabs-inline`; then G3 live pilot B vs D. If still no keys: **temper early mutation bias** (e.g. delay preferred-allele anchoring / soften `_biased_choice` until gen≥2, or lower early mutation_rate under CABS) and/or **longer horizon** `max_gen≥6`, targeting H5 ≥4/5 and gens30 ≥3/5 while keeping final ≥3/5. Do **not** set READY — live GPQA still required; delay-XO did not restore offline H5/gens30.

---

## 2026-08-04T16:04Z — Tick 11 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-7466` (fast-forwarded Ticks 1–10 from `c34f`, then this tick)
- API keys in cloud env: **absent** (no paid GPQA this tick)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
G2–G4 remain blocked without API keys. Offline PRIMARY after Tick 10: final/gens30 only **2/5**; mean gap ~2.56pp. Diagnosis: mutation bias alone still loses preferred alleles during fair 50/50 crossover between mixed elites, slowing Condition D sample-efficiency vs B.

### What this tick did (ONE step)
Implemented **bias-aware crossover** for Condition D (soft preferred inherit):
1. `operators._crossover_pick` + `crossover(..., bias=)` — when bias present, inherit preferred parental allele with p=0.85 (soft; hard p=1.0 over-collapsed diversity on mid-pilot `1530/1540`)
2. `breed_offspring` forwards bias into both crossover and mutate (Condition B `bias=None` unchanged)
3. Unit test `test_bias_aware_crossover_prefers_winner_allele`
4. Re-pilot B `1550–1554` vs D `1560–1564`; case study on `run_1560`

### Metrics delta
| Metric | Before (Tick 10) | After (Tick 11) |
|--------|------------------|-----------------|
| Offline D final wins (>1pp) | 2/5 | **3/5** (B final wins 1) |
| Offline D gens30 wins | 2/5 | **0/5** (B gens30 wins 2) — regression |
| Mean final gap (D−B) | ~2.56pp | ~**2.13pp** |
| Offline H5 ρ>0.3 | 4/5; pooled ≈0.23 | **2/5** (0.5 / −0.5 / −1.0 / −0.5 / 0.5) — regression |
| Case study gen2 pref share / lift | 1.0 / +0.0866 (`1520`) | **1.0 / +0.0554** (`1560`) |
| Bias-aware crossover | Missing | **Present** (soft p=0.85) |
| Live PRIMARY / G2 | Blocked (no API) | Still blocked |

### Next recommended step
When `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` present and budget checked: **G2** smoke GPQA subset (≤5 samples, pop≤2, max_gen≤2, one seed) Condition D with `--cabs --cabs-inline`; then G3 live pilot B vs D. If still no keys: restore offline H5/gens30 (e.g. longer horizon `max_gen≥6`, or temper XO further / bias only after gen≥2) while keeping final ≥3/5. Do **not** set READY — live GPQA still required; H5 offline regressed.

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
|--------|-----------------|-----------------|
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
Replaced dry-run fitness with DNA-transferable scoring and ran offline B vs D case study (later superseded by Tick 9 additive latent model). See older entries / `docs/case_study_offline.md` history.

### Next recommended step
G2 live smoke when API keys present. Offline: fix H5 causality (Tick 9).

---
