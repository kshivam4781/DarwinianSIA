# Gate 3 report — Pilot B vs D

**Timestamp:** 2026-08-30T02:23:14Z
**Mode:** `preflight`
**Live G3 ready:** no

<!-- OFFLINE_G3_PILOT_START -->
## Offline synthetic pilot (Tick 23 — not a live G3 substitute)

| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Run IDs |
|------|-------|-----|-------|---------|-------------|---------|
| B | 11,22,33,44,55 | 4 | 2 | 6 | 3 | `1830–1834` |
| D | 11,22,33,44,55 | 4 | 2 | 6 | 3 | `1840–1844` |

Harness: `scripts/offline_bvd_case_study.py` (compressed additive latent dry-run fitness [0.02, 0.34] + delay-all mutation bias until gen≥2 + directed ε-explore outside disputed pools + latest-gen bias harvest + delayed soft bias-aware crossover). H5 via `scripts/epistemic_results.compute_h5(min_generation=2, fitness_key="mean", delta_horizon=2)`. Cost via `cost_to_threshold` (eval-call proxy offline; tokens/USD preferred when present). Case study measures preferred DNA share at **gen≥3** (first steered generation).

| Metric | Result |
|--------|--------|
| D final-fitness wins (>1pp) | **5/5** |
| B final-fitness wins (>1pp) | **0/5** |
| Mean final (B / D) | ~0.253 / ~0.314 (~**6.15pp**) |
| D gens-to-30% wins | **4/5** (B: 0) — offline PRIMARY gens30; seed 44 tie |
| D cost-to-30% wins (≥15% / reach-vs-never) | **4/5** (B: 0) — offline PRIMARY cost30 (Tick 22 metric) |
| Gens-to-25% | Both hit gen1 (still saturated at 25%) |
| Gen-1 ≥30% | **0/5** seeds (saturation still fixed) |
| H5 ρ>0.3 (D seeds) | **5/5** (0.4 / 0.8 / 0.8 / 1.0 / 0.4) — mean forward Δ; gen≥2; horizon=2 |
| Case study | `docs/case_study_offline.md` (`run_1840`) — gen3 steered preferred share **0.75** (gen1/2/3 = 0.25→0.5→0.75); lift +0.0436 |
| Figures | `docs/figures/fig1_learning_curves.png`, `fig2_mechanism.png` |
| Summary JSON | `docs/offline_bvd_summary.json` |

**Finding:** Tick 22 left case-study H2 measured at fair-bred gen2 (~0.25 share). Tick 23 aligns the case study with delay-all: first steered generation is gen3. On `run_1840`, contradiction `selective` vs `aggressive` → preferred `selective` share rises **0.25→0.5→0.75** with fitness lift **+0.0436**. Offline PRIMARY/H5 rates unchanged (gens30/cost30 **4/5**, H5 **5/5**, mean gap ~**6.15pp**).

Prior Tick-22 pilot `1810–1814` / `1820–1824` remains the first offline cost30 **4/5** snapshot. Tick-20 `1780–1784` / `1790–1794` remains the first offline gens30 **4/5** snapshot. Tick-19 `1750–1754` / `1760–1764` remains the first offline H5 **5/5** snapshot. Tick-8 hash-fitness “D final 4/5” remains **withdrawn** (non-causal).
<!-- OFFLINE_G3_PILOT_END -->

## Live G3 preflight

| Check | OK | Detail |
|-------|----|--------|
| `gpqa_layout` | yes | ok |
| `gpqa_not_synthetic` | NO | synthetic smoke fixture detected — fetch real GPQA diamond before paid G3 |
| `anthropic_key` | NO | ANTHROPIC_API_KEY missing |
| `nebius_key` | NO | NEBIUS_API_KEY missing |
| `hf_token_optional` | yes | missing (optional; needed for HF gpqa download) |
| `budget` | yes | spent=$0.00 ceiling=$20.00 estimate=$4.00/pair × 1 → projected=$4.00 |
| `run_ids_free` | yes | all planned run IDs unused |
| `sequential_only` | yes | 1 seed pair(s); runner executes B then D serially (no parallel GPQA) |
| `seed_count` | yes | 1 seed(s) (G3 pilot shape) |
| `per_run_venv` | yes | uv available at /home/ubuntu/.local/bin/uv (SIA per-run venv path) |
| `runtime_deps` | yes | uv available at /home/ubuntu/.local/bin/uv; sia importable via PYTHONPATH=/workspace/SIA; huggingface_hub already importable |

### Planned seed pairs

| Seed | Condition B | Condition D |
|------|-------------|-------------|
| 1 | B `1201` | D `1301` |

### Planned commands (sequential: B then D per seed; never parallel)

1. `/usr/bin/python3 -m sia run --task gpqa --darwinian --population_size 4 --elite_count 2 --max_gen 5 --run_id 1201 --eval_subset 15 --no-web --seed 1`
2. `/usr/bin/python3 -m sia run --task gpqa --darwinian --population_size 4 --elite_count 2 --max_gen 5 --run_id 1301 --eval_subset 15 --no-web --seed 1 --cabs --cabs-inline`

## Blockers (live G3)

- gpqa_not_synthetic: synthetic smoke fixture detected — fetch real GPQA diamond before paid G3
- anthropic_key: ANTHROPIC_API_KEY missing
- nebius_key: NEBIUS_API_KEY missing

**Live G3 status:** NOT RUN this tick

## Next

1. Ensure live G2 smoke passed (`scripts/run_g2_smoke.py --live ...`).
2. Add `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` (+ `HF_TOKEN` for `--fetch-diamond`).
3. Budget-check, then:
   `python scripts/run_g3_pilot.py --live --seeds 1 --b-run-ids 1201 --d-run-ids 1301 --fetch-diamond`
4. If pilot looks promising, G4 5-seed under remaining budget (never parallel full GPQA).
5. Do **not** set `ICML_READY` STATUS: READY from offline / preflight alone.

