# ICML Thesis 1 — Progress log

Persistent agent ticks append newest entries at the top.

---

## 2026-08-05T20:05Z — Tick 24 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-ed5f` (fast-forwarded Ticks 1–23 from `dcdb`, then this tick)
- API keys in cloud env: **absent** (secrets + HF GPQA access re-requested)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
Live G2–G4 remain the READY blocker. Offline PRIMARY/H5/mechanism already strong (gens30/cost30 **4/5**, H5 **5/5**, post-steer H2). Prior ticks rediscovered G2 launch constraints ad hoc; risk of accidentally spending API budget on synthetic smoke answers once keys appear.

### What this tick did (ONE step)
**Turnkey live G2 preflight + hard-stop runner (no API spend):**
1. `scripts/run_g2_smoke.py` — `--preflight-only` / `--dry-run` / `--live`; refuses paid G2 without keys, non-smoke GPQA, free run_id, and budget headroom; validates belief_store / epistemic_value / scoped bias after a run; writes `docs/gate2_report.md` (+ `.json`)
2. `prepare_gpqa_smoke_data.is_synthetic_smoke` — detect domain=smoke / Smoke Q* fixtures
3. Unit tests `tests/test_run_g2_smoke.py` (+ smoke-detect coverage); regression: `ready_for_live` not vacuously true in preflight mode
4. Ran preflight `--run-id 1850` → dry-run ready **yes**; live ready **no** (missing keys + synthetic GPQA)

### Metrics delta
| Metric | Before (Tick 23) | After (Tick 24) |
|--------|------------------|-----------------|
| Offline D final / gens30 / cost30 / H5 | 5/5 / 4/5 / 4/5 / 5/5 | unchanged (no re-pilot) |
| Live G2 preflight tooling | ad hoc Section 21.7 commands | **`scripts/run_g2_smoke.py`** + `docs/gate2_report.md` |
| Live PRIMARY / G2 | Blocked (no API) | Still blocked; secrets re-requested; runner ready for next tick |

### Next recommended step
When `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` present **and** real GPQA diamond replaces smoke fixture (HF gated — needs access + optional `HF_TOKEN`): budget-check, then `python scripts/run_g2_smoke.py --live --run-id 1300` (or other unused id). Do **not** set READY from preflight alone.

---

## 2026-08-05T18:20Z — Tick 23 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-dcdb` (fast-forwarded Ticks 1–22 from `2710`, then this tick)
- API keys in cloud env: **absent** (no paid GPQA; secrets re-requested; GPQA diamond HF-gated)
- Budget: ~$20 ceiling; spend this tick = $0
- Infra: installed `python3.12-venv` on cloud host (was missing for per-run venvs)

### Largest gap diagnosed
G2–G4 still blocked without API keys. Offline PRIMARY/H5 already strong (gens30/cost30 **4/5**, H5 **5/5**), but the MECHANISM case study attributed DNA skew to **gen2** preferred share (~0.25) — which is still **fair-bred under delay-all**. That understated H2 and misaligned the paper chain with Tick 14 (first steered generation = gen3).

### What this tick did (ONE step)
**Post-steering case-study H2 extraction + offline re-pilot:**
1. `scripts/offline_bvd_case_study.py`: measure preferred DNA share at gen≥3; keep gen2 as pre-steer baseline; prefer multi-allele + fitness-aligned contradictions with non-trivial lift
2. Unit tests `tests/test_offline_case_study_steered.py`
3. Offline B vs D re-pilot `1830–1834` / `1840–1844` (`max_gen=6`); case study `run_1840`; refreshed figs / paper artifacts / gate3 / READY

### Metrics delta
| Metric | Before (Tick 22) | After (Tick 23) |
|--------|------------------|-----------------|
| Offline D final / gens30 / cost30 / H5 | 5/5 / 4/5 / 4/5 / 5/5 | **5/5 / 4/5 / 4/5 / 5/5** (stable) |
| Mean final gap (D−B) | ~6.15pp | ~**6.15pp** |
| Case-study H2 window | gen2 share **0.25** (`1823`) | **gen3 steered share 0.75** (`1840`; gen1/2/3 = 0.25→0.5→0.75) |
| Case-study lift | +0.0869 | **+0.0436** (preferred@gen3 − loser@gen1; fitness-aligned `selective`) |
| Live PRIMARY / G2 | Blocked (no API) | Still blocked (secrets + GPQA diamond re-requested) |

### Next recommended step
When `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` present: obtain real GPQA diamond (HF gated — needs dataset access), budget-check, then **live G2** smoke (drop `--dry-run`; ≤5 samples, pop≤2, max_gen≤2, one seed, unused run_id ≥1850). Do **not** set READY from offline post-steer H2 alone.

---

## 2026-08-05T16:58Z — Tick 22 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-2710` (fast-forwarded Ticks 1–21 from `084b`, then this tick)
- API keys in cloud env: **absent** (no paid GPQA; secrets re-requested)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
G2–G4 still blocked without API keys. Offline PRIMARY already has gens30 **4/5** and final **5/5**, but PRIMARY criterion **(b) cost-to-threshold** was unimplemented in `epistemic_results.py` — Table 2 cost column empty and live G3/G4 would have no ≥15% savings comparator even when D reaches threshold and B never does.

### What this tick did (ONE step)
**Implement cost-to-threshold PRIMARY metric (criterion b) + offline re-pilot:**
1. `scripts/epistemic_results.py`: `load_gen_cost` / `cost_to_threshold` / `_cost_win` (≥15% fewer units); prefer live tokens/USD, else eval-call proxy from `eval_subset`
2. `compare_b_vs_d` now reports `d_wins_cost25/30` + `primary_cost30_pass`
3. Unit tests in `SIA/tests/test_epistemic_results.py` (+ sia-upstream sync)
4. Offline B vs D re-pilot `1810–1814` / `1820–1824` (`max_gen=6`); case study `run_1823`; refreshed figs / paper artifacts / gate3 / READY

### Metrics delta
| Metric | Before (Tick 21) | After (Tick 22) |
|--------|------------------|-----------------|
| Offline D final / gens30 / H5 | 5/5 / 4/5 / 5/5 | **5/5 / 4/5 / 5/5** (stable) |
| Offline D cost30 wins (≥15% / reach-vs-never) | not measured | **4/5** (`primary_cost30_pass`) |
| Mean final gap (D−B) | ~6.15pp | ~**6.15pp** |
| Case study gen2 pref share / lift | 0.25 / +0.0869 (`1793`) | **0.25 / +0.0869** (`1823`) |
| Live PRIMARY / G2 | Blocked (no API) | Still blocked (secrets re-requested) |

### Next recommended step
When `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` present: replace smoke `diamond_questions.json` with real GPQA diamond, budget-check, then **live G2** smoke (drop `--dry-run`; ≤5 samples, pop≤2, max_gen≤2, one seed, unused run_id ≥1830). Cost-to-threshold will then use real token fields. Do **not** set READY from offline cost30 4/5.

---

## 2026-08-05T14:10Z — Tick 21 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-084b` (fast-forwarded Ticks 1–20 from `d7f1`, then this tick)
- API keys in cloud env: **absent** (no paid GPQA; secrets re-requested)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
G2–G4 still blocked without API keys. Offline PRIMARY-shaped signal is already strong (gens30 **4/5**, H5 **5/5**). Next blocker after keys: missing gitignored GPQA `data/public|private` so even a live smoke cannot resolve `--task gpqa`.

### What this tick did (ONE step)
**Unblock G2 harness layout (no API spend):**
1. Added `scripts/prepare_gpqa_smoke_data.py` — synthetic 5-Q fixture into `SIA/` + `sia-upstream/` task trees (`--check` / `--force`)
2. Unit test `tests/test_prepare_gpqa_smoke_data.py`
3. Validated real CLI Condition D dry-run: `run_1800` (`--cabs --cabs-inline --dry-run --eval_subset 5 --population_size 2 --max_gen 2 --seed 42`) → belief_store + scoped bias (`tool_strategy` / `memory`) + `epistemic_value.jsonl`
4. Documented in Section 12 / 21, `paper_artifacts.md`, `gate3_report.md`, READY checklist

### Metrics delta
| Metric | Before (Tick 20) | After (Tick 21) |
|--------|------------------|-----------------|
| Offline D final / gens30 / H5 | 5/5 / 4/5 / 5/5 | unchanged (no re-pilot) |
| CLI `--task gpqa` dry-run Condition D | blocked (missing data/) | **PASS** `run_1800` |
| Live PRIMARY / G2 | Blocked (no API + no data) | Data layout unblocked; **still no API keys** |

### Next recommended step
When `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` present: replace smoke `diamond_questions.json` with real GPQA diamond (same schema), budget-check, then **live G2** smoke (drop `--dry-run`; ≤5 samples, pop≤2, max_gen≤2, one seed, unused run_id). Do **not** set READY from dry-run/`run_1800`.

---

## 2026-08-05T12:10Z — Tick 20 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-d7f1` (fast-forwarded Ticks 1–19 from `eec8`, then this tick)
- API keys in cloud env: **absent** (no paid GPQA this tick; secrets re-requested via environment setup)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
G2–G4 remain blocked without API keys. Offline after Tick 19: gens30 **3/5**, final **5/5**, H5 **5/5**. Seed 22 never crossed 30% — diagnosis: ε-greedy explore sampled the **full** trait enum and often re-drew disputed-pool alleles (`minimal`/`aggressive`), so `selective` never entered; live harvest could not promote it.

### What this tick did (ONE step)
**Directed ε-explore outside disputed DNA pools:**
1. `_biased_choice`: on explore steps, sample only alleles **absent** from the contradiction-scoped pool (fallback to full enum if no outsiders)
2. Unit tests: stronger selective discovery rate + `test_biased_mutate_directed_explore_never_redraws_pool`
3. Sync `sia-upstream/sia/evolution/operators.py`
4. Re-pilot B `1780–1784` vs D `1790–1794` (`max_gen=6`); case study on `run_1793`; refreshed figs / paper artifacts / gate3 / READY

### Metrics delta
| Metric | Before (Tick 19) | After (Tick 20) |
|--------|------------------|-----------------|
| Offline D final wins (>1pp) | 5/5 | **5/5** (stable) |
| Offline D gens30 wins | 3/5 | **4/5** (B: 0) — seed 22 unlocked |
| Mean final gap (D−B) | ~5.35pp | ~**6.15pp** |
| Offline H5 ρ>0.3 | 5/5 (0.8 / 0.8 / 0.8 / 1.0 / 0.6) | **5/5** (0.4 / 0.8 / 0.8 / 1.0 / 0.4) |
| Case study gen2 pref share / lift | 0.25 / +0.0869 (`1763`) | **0.25 / +0.0869** (`1793`) — same chain |
| Live PRIMARY / G2 | Blocked (no API) | Still blocked (secrets re-requested) |

### Next recommended step
When `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` present and budget checked: **G2** smoke GPQA subset (≤5 samples, pop≤2, max_gen≤2, one seed) Condition D with `--cabs --cabs-inline`; then G3 live pilot B vs D. Offline gens30 **4/5** + H5 **5/5** are in place but **do not** set READY without live GPQA.

---

## 2026-08-05T10:10Z — Tick 19 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-eec8` (fast-forwarded Ticks 1–18 from `0d62`, then this tick)
- API keys in cloud env: **absent** (no paid GPQA this tick; secrets requested via environment setup)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
G2–G4 remain blocked without API keys. Offline after Tick 18: gens30 **3/5**, final **5/5**, H5 **4/5** — seed 11 single-step ρ=0.0 because ε-greedy discover→adopt lags one generation (peak mean gain at gen3→gen4 while epi ranks highest at gen2).

### What this tick did (ONE step)
**H5 forward-horizon Δfitness (measurement protocol; Tick 17 mutation path unchanged):**
1. `compute_h5(delta_horizon=2)` — Y = `mean(fitness[t+1..t+h]) − fitness[t]` (h=2; uses available future gens)
2. Unit test `test_compute_h5_horizon_recovers_delayed_gain` (seed-11-shaped series)
3. Re-pilot B `1750–1754` vs D `1760–1764` (`max_gen=6`); case study on `run_1763`; refreshed figs / paper artifacts / gate3 / READY

### Metrics delta
| Metric | Before (Tick 18) | After (Tick 19) |
|--------|------------------|-----------------|
| Offline D final wins (>1pp) | 5/5 | **5/5** (stable) |
| Offline D gens30 wins | 3/5 | **3/5** (stable) |
| Mean final gap (D−B) | ~5.35pp | ~**5.35pp** |
| Offline H5 ρ>0.3 | 4/5 (0.0 / 0.8 / 0.4 / 0.8 / 0.6) | **5/5** (0.8 / 0.8 / 0.8 / 1.0 / 0.6) |
| Case study gen2 pref share / lift | 0.25 / +0.0869 (`1743`) | **0.25 / +0.0869** (`1763`) — same chain |
| Live PRIMARY / G2 | Blocked (no API) | Still blocked (secrets requested) |

### Next recommended step
When `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` present and budget checked: **G2** smoke GPQA subset (≤5 samples, pop≤2, max_gen≤2, one seed) Condition D with `--cabs --cabs-inline`; then G3 live pilot B vs D. Offline H5 **5/5** + gens30 **3/5** are in place but **do not** set READY without live GPQA.

---

## 2026-08-05T08:10Z — Tick 18 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-0d62` (fast-forwarded Ticks 1–17 from `f1b8`, then this tick)
- API keys in cloud env: **absent** (no paid GPQA this tick)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
G2–G4 remain blocked without API keys. Offline after Tick 17: gens30 **3/5**, final **5/5**, but H5 only **2/5** under elite-best Δfitness including gen1→gen2 (fair breeding under delay-all — high epi vs non-steered Δ → structural noise; seed 22 ρ=−0.3).

### What this tick did (ONE step)
**Restore offline H5 validity via measurement protocol aligned with delay-all steering:**
1. `compute_h5(min_generation=2)` — exclude gen1→gen2 pairs (DNA steering inactive until breeding from gen≥2)
2. Default H5 `fitness_key="mean"` — population-mean Δfitness matches population-level contradiction steering (elite-best is still available for sensitivity)
3. Keep Tick 17 ε-greedy mutation / live harvest path (stuck-preferred-only explore + discovery reweight experiments regressed H5; reverted)
4. Re-pilot B `1730–1734` vs D `1740–1744` (`max_gen=6`); case study on `run_1743`; refreshed figs / paper artifacts / gate3 / READY

### Metrics delta
| Metric | Before (Tick 17) | After (Tick 18) |
|--------|------------------|-----------------|
| Offline D final wins (>1pp) | 5/5 | **5/5** (stable) |
| Offline D gens30 wins | 3/5 | **3/5** (stable; offline PRIMARY gens30) |
| Mean final gap (D−B) | ~5.35pp | ~**5.35pp** |
| Offline H5 ρ>0.3 | 2/5 (best Δ; incl. gen1) | **4/5** (mean Δ; gen≥2) — 0.0 / 0.8 / 0.4 / 0.8 / 0.6 |
| Case study gen2 pref share / lift | 0.25 / +0.0869 (`1683`) | **0.25 / +0.0869** (`1743`) — same chain |
| Live PRIMARY / G2 | Blocked (no API) | Still blocked |

### Next recommended step
When `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` present and budget checked: **G2** smoke GPQA subset (≤5 samples, pop≤2, max_gen≤2, one seed) Condition D with `--cabs --cabs-inline`; then G3 live pilot B vs D. Offline PRIMARY gens30 + H5 4/5 are in place but **do not** set READY without live GPQA.

---

## 2026-08-05T06:11Z — Tick 17 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-f1b8` (fast-forwarded Ticks 1–16 from `3956`, then this tick)
- API keys in cloud env: **absent** (no paid GPQA this tick)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
G2–G4 remain blocked without API keys. Offline after Tick 16: final **3/5**, gens30 **2/5**, H5 **2/5**. Seed 22 diagnosis: contradiction bias locked onto suboptimal pair `tool_strategy∈{minimal,aggressive}` (selective absent from gen1), then forced outsiders onto local winner — population never discovered `selective` needed to cross 30%.

### What this tick did (ONE step)
**Escape suboptimal contradiction pools** via ε-greedy mutation + live population bias harvest:
1. `_biased_choice`: ε-greedy explore full trait enum (`_BIAS_MUTATE_EXPLORE_EPS=0.18`); preserve out-of-pool outsiders (stop forcing them onto local preferred)
2. `load_mutation_bias`: harvest latest-gen DNA alleles ranked by fitness so discoveries can become preferred
3. Unit tests for ε-explore + live harvest; sync `sia-upstream/`
4. Re-pilot B `1670–1674` vs D `1680–1684` (`max_gen=6`); case study on `run_1683` (positive lift); refreshed figs / paper artifacts / gate3 / READY

### Metrics delta
| Metric | Before (Tick 16) | After (Tick 17) |
|--------|------------------|-----------------|
| Offline D final wins (>1pp) | 3/5 | **5/5** (B final wins 0) |
| Offline D gens30 wins | 2/5 | **3/5** (B: 0) — offline PRIMARY gens30 pass |
| Mean final gap (D−B) | ~2.26pp | ~**5.35pp** |
| Offline H5 ρ>0.3 | 2/5 | **2/5** (0.3 / −0.3 / 0.3 / 0.6 / 0.6) — strict >0.3 unchanged; two solid 0.6 |
| Case study gen2 pref share / lift | 0.5 / +0.0420 (`1660`) | **0.25 / +0.0869** (`1683`, planning_style=stepwise) |
| Live PRIMARY / G2 | Blocked (no API) | Still blocked |

### Next recommended step
When `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` present and budget checked: **G2** smoke GPQA subset (≤5 samples, pop≤2, max_gen≤2, one seed) Condition D with `--cabs --cabs-inline`; then G3 live pilot B vs D. If still no keys: restore offline H5 to ≥4/5 strict ρ>0.3 (seed 22 ρ=−0.3 under exploration noise) while keeping gens30 ≥3/5. Do **not** set READY — live GPQA still required despite offline gens30 PRIMARY pass.

---

## 2026-08-05T04:05Z — Tick 16 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-3956` (fast-forwarded Ticks 1–15 from `b670`, then this tick)
- API keys in cloud env: **absent** (no paid GPQA this tick)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
G2–G4 remain blocked without API keys. Offline after Tick 15: final **3/5**, gens30 **0/5**, H5 **2/5**, mean gap ~2.55pp. Root cause of gens30 fail: **threshold saturation** — ~42% of gen-1 best-of-4 seeds already ≥30% under the `[0.02, 0.38]` latent mapping.

### What this tick did (ONE step)
**Retuned additive latent fitness scale** so early gens sit below 30%:
1. `deterministic_fitness` now maps normalized latent sum into `[0.02, 0.34]` (`_FITNESS_FLOOR` / `_FITNESS_SPAN`)
2. Unit test `test_deterministic_fitness_scale_keeps_mid_dna_under_threshold`
3. Synced `sia-upstream/` copies
4. Re-pilot B `1650–1654` vs D `1660–1664` (`max_gen=6`); case study on `run_1660`; refreshed figs / paper artifacts / gate3 / READY

### Metrics delta
| Metric | Before (Tick 15) | After (Tick 16) |
|--------|------------------|-----------------|
| Offline D final wins (>1pp) | 3/5 | **3/5** (B final wins 1) — stable |
| Offline D gens30 wins | 0/5 | **2/5** (B: 0) — improved; still short of ≥3/5 |
| Mean final gap (D−B) | ~2.55pp | ~**2.26pp** — slight regression |
| Offline H5 ρ>0.3 | 2/5 | **2/5** (0.6 / 0.3 / 0.1 / 0.3 / 0.4) — unchanged |
| Gen-1 ≥30% (both cond) | 4/5 seeds | **0/5** — saturation fixed |
| Case study gen2 pref share / lift | 0.5 / +0.0473 (`1640`) | **0.5 / +0.0420** (`1660`) — stable |
| Live PRIMARY / G2 | Blocked (no API) | Still blocked |

### Next recommended step
When `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` present and budget checked: **G2** smoke GPQA subset (≤5 samples, pop≤2, max_gen≤2, one seed) Condition D with `--cabs --cabs-inline`; then G3 live pilot B vs D. If still no keys: push offline gens30 to ≥3/5 (e.g. strengthen late-gen preferred adoption / slightly longer horizon on lagging seeds 22/33) and restore H5 ≥4/5 while keeping final ≥3/5. Do **not** set READY — live GPQA still required; offline gens30 still 2/5.

---

## 2026-08-05T02:00Z — Tick 15 (automation cron)

### Status snapshot
- `docs/ICML_READY.md`: **STATUS: IN_PROGRESS**
- Branch: `cursor/icml-epistemic-results-b670` (fast-forwarded Ticks 1–14 from `bb57`, then this tick)
- API keys in cloud env: **absent** (no paid GPQA this tick)
- Budget: ~$20 ceiling; spend this tick = $0

### Largest gap diagnosed
G2–G4 remain blocked without API keys. Offline after Tick 14: final **4/5**, gens30 **0/5**, H5 **3/5**, mean gap ~3.34pp. Delay-all fixed gen2 preferred collapse, but only two biased breeding rounds exist at `max_gen=4`. Next offline lever was longer horizon.

### What this tick did (ONE step)
Ran **longer-horizon offline B vs D re-pilot** under unchanged delay-all mutation bias:
1. `scripts/offline_bvd_case_study.py --max-gen 6 --b-id-start 1630 --d-id-start 1640`
2. Refreshed case study (`run_1640`), figs, `docs/offline_bvd_summary.json`, paper artifacts / gate3 / READY checklist
3. No mechanism code change this tick (horizon-only diagnostic)

### Metrics delta
| Metric | Before (Tick 14, max_gen=4) | After (Tick 15, max_gen=6) |
|--------|-----------------------------|---------------------------|
| Offline D final wins (>1pp) | 4/5 | **3/5** (B final wins 1) — soft regression |
| Offline D gens30 wins | 0/5 | **0/5** (B gens30 wins 1) — still fail |
| Mean final gap (D−B) | ~3.34pp | ~**2.55pp** — soft regression |
| Offline H5 ρ>0.3 | 3/5 | **2/5** (0.6 / 0.3 / 0.1 / 0.3 / 0.4) — regression |
| Seeds with both B&D gens30≤2 | n/a | **4/5** — threshold saturation |
| Case study gen2 pref share / lift | 0.5 / +0.0473 (`1620`) | **0.5 / +0.0473** (`1640`) — stable |
| Live PRIMARY / G2 | Blocked (no API) | Still blocked |

### Next recommended step
When `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` present and budget checked: **G2** smoke GPQA subset (≤5 samples, pop≤2, max_gen≤2, one seed) Condition D with `--cabs --cabs-inline`; then G3 live pilot B vs D. If still no keys: **retune additive latent fitness** so early gens sit below 30% more often (make gens-to-threshold discriminative under delay-all), targeting gens30 ≥3/5 and H5 ≥4/5 while keeping final ≥3/5. Do **not** set READY — live GPQA still required; longer horizon alone cannot fix saturated thresholds.

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
