# Gate 3 report — Pilot B vs D

**Timestamp:** 2026-09-06T22:04:37Z
**Mode:** `preflight`
**Live G3 ready:** no

<!-- OFFLINE_G3_PILOT_START -->
## Offline synthetic pilot (Tick 300 live-shape — not a live G3 substitute)

| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Run IDs |
|------|-------|-----|-------|---------|-------------|---------|
| B | 11,22,33,44,55 | 4 | 2 | 6 | 5 | `1890–1894` |
| D | 11,22,33,44,55 | 4 | 2 | 6 | 5 | `1900–1904` |

Harness: `scripts/offline_bvd_case_study.py` at **Nebius live G3/G4 shape** (`icml_g3g4_live_shape`: pop4 × eval5 × elite2 × max_gen6). Compressed additive latent dry-run fitness [0.02, 0.34] + delay-all mutation bias until gen≥2 + directed ε-explore outside disputed pools + latest-gen bias harvest + delayed soft bias-aware crossover. H5 via `scripts/epistemic_results.compute_h5(min_generation=2, fitness_key="mean", delta_horizon=2)`. Cost via `cost_to_threshold` (eval-call proxy offline; tokens/USD preferred when present). Case study measures preferred DNA share at **gen≥3** (first steered generation).

| Metric | Result |
|--------|--------|
| D final-fitness wins (>1pp) | **5/5** |
| B final-fitness wins (>1pp) | **0/5** |
| Mean final (B / D) | ~0.253 / ~0.314 (~**6.15pp**) |
| D gens-to-30% wins | **4/5** (B: 0) — offline PRIMARY gens30; seed 44 tie |
| D cost-to-30% wins (≥15% / reach-vs-never) | **4/5** (B: 0) — offline PRIMARY cost30 (eval=5 call proxy) |
| Gens-to-25% | Both hit gen1 (still saturated at 25%) |
| Gen-1 ≥30% | **0/5** seeds (saturation still fixed) |
| H5 ρ>0.3 (D seeds) | **5/5** (0.4 / 0.8 / 0.8 / 1.0 / 0.4) — mean forward Δ; gen≥2; horizon=2 |
| H2 preferred ≥0.5 (D seeds) | **4/5** (Tick 366; shares ≈0.71/0.29/0.83/0.67/0.75; seed **22** fails) — MECHANISM still OK via case study |
| Case study | `docs/case_study_offline.md` (`run_1900`) — gen3 steered preferred share **0.75** (gen1/2/3 = 0.25→0.5→0.75); lift +0.0436 |
| Figures | `docs/figures/fig1_learning_curves.png`, `fig2_mechanism.png` |
| Summary JSON | `docs/offline_bvd_summary.json` (`shape` locked to live; Tick 366 `d_wins_h2` / `h2_preferred_pass`) |

**Finding:** Tick 300 re-pilots offline B vs D at the **exact live Nebius shape** (eval5, not Tick-23 eval3). Fitness/gens/H5 identical to Tick 23; cost@30% scales with eval_subset (e.g. seed 11: 80 calls vs prior 48). Confirms PRIMARY-shaped offline signal before paid G2→G3→G4. Case study on `run_1900`: contradiction `selective` vs `aggressive` → preferred `selective` share **0.25→0.5→0.75** with lift **+0.0436**. Tick **366** aggregates preferred-allele H2: **4/5** seeds pass (≥0.5); seed 22 preferred≈0.29 is an honest MECHANISM miss covered by the case study (not pool `in_bias_share=1.0`).

Prior Tick-23 pilot `1830–1834` / `1840–1844` remains the first post-steering H2 snapshot (eval3). Tick-22 `1810–1814` / `1820–1824` remains the first offline cost30 **4/5** snapshot. Tick-20 `1780–1784` / `1790–1794` remains the first offline gens30 **4/5** snapshot. Tick-8 hash-fitness “D final 4/5” remains **withdrawn** (non-causal).
<!-- OFFLINE_G3_PILOT_END -->

## Live G3 preflight

| Check | OK | Detail |
|-------|----|--------|
| `gpqa_layout` | yes | ok |
| `gpqa_not_synthetic` | NO | synthetic smoke fixture detected — fetch real GPQA diamond before paid G3 |
| `anthropic_key` | yes | optional (Nebius meta; ANTHROPIC unused) |
| `nebius_key` | NO | NEBIUS_API_KEY missing |
| `hf_token` | NO | HF_TOKEN / HUGGINGFACE_HUB_TOKEN missing (required for --fetch-diamond) |
| `budget` | yes | spent=$0.00 ceiling=$20.00 estimate=$3.00/pair × 1 → projected=$3.00 |
| `run_ids_free` | yes | all planned run IDs unused |
| `sequential_only` | yes | 1 seed pair(s); runner executes B then D serially (no parallel GPQA) |
| `seed_count` | yes | 1 seed(s) (G3 pilot shape) |
| `per_run_venv` | yes | uv available at /home/ubuntu/.local/bin/uv (SIA per-run venv path) |
| `runtime_deps` | yes | uv available at /home/ubuntu/.local/bin/uv; sia importable via PYTHONPATH=/workspace/SIA; huggingface_hub + pydantic_ai already importable; user site on PYTHONPATH (/home/ubuntu/.local/lib/python3.12/site-packages) |
| `nebius_meta_profile` | yes | kimi-nebius-pydantic-meta → nebius / pydantic-ai (moonshotai/Kimi-K2.6) |
| `nebius_target_profile` | yes | kimi-nebius-target → nebius (moonshotai/Kimi-K2.6) |
| `g3g4_recipes_match_live_shape` | yes | committed gate3/4 + Section 21.7 match icml_g3g4_live_shape() |
| `offline_bvd_matches_live_shape` | yes | offline Bvd summary + paper IDs + figures match live shape |
| `tip_ok_for_live` | yes | local Tick 364 matches remote tip refs/remotes/origin/cursor/icml-epistemic-results-f49c |

### Planned seed pairs

| Seed | Condition B | Condition D |
|------|-------------|-------------|
| 1 | B `1201` | D `1301` |

### Planned commands (sequential: B then D per seed; never parallel)

1. `/usr/bin/python3 -m sia run --task gpqa --darwinian --population_size 4 --elite_count 2 --max_gen 6 --run_id 1201 --eval_subset 5 --no-web --seed 1 --meta-agent-profile kimi-nebius-pydantic-meta --target-agent-profile kimi-nebius-target`
2. `/usr/bin/python3 -m sia run --task gpqa --darwinian --population_size 4 --elite_count 2 --max_gen 6 --run_id 1301 --eval_subset 5 --no-web --seed 1 --cabs --cabs-inline --meta-agent-profile kimi-nebius-pydantic-meta --target-agent-profile kimi-nebius-target`

## Blockers (live G3)

- gpqa_not_synthetic: synthetic smoke fixture detected — fetch real GPQA diamond before paid G3
- nebius_key: NEBIUS_API_KEY missing
- hf_token: HF_TOKEN / HUGGINGFACE_HUB_TOKEN missing (required for --fetch-diamond)

## Notes

- runtime deps before diamond: uv available at /home/ubuntu/.local/bin/uv; sia importable via PYTHONPATH=/workspace/SIA; huggingface_hub + pydantic_ai already importable; user site on PYTHONPATH (/home/ubuntu/.local/lib/python3.12/site-packages)
- diamond fetch failed: HF_TOKEN / HUGGINGFACE_HUB_TOKEN required to download gated Idavidrein/gpqa. Accept dataset terms on HuggingFace, then set the token.

**Live G3 status:** NOT RUN this tick

## Next

1. Ensure live G2 smoke passed (`scripts/run_g2_smoke.py --live ...`).
2. Add `NEBIUS_API_KEY (ANTHROPIC_API_KEY optional — Tick 289 Nebius pydantic-ai meta) + (HF_TOKEN or local gpqa_diamond.csv)` (see `docs/ICML_HUMAN_UNBLOCK.md`).
3. Budget-check, then:
   `python3 scripts/run_g3_pilot.py --live --seeds 1 --b-run-ids 1201 --d-run-ids 1301 --fetch-diamond`
4. If pilot looks promising, G4 5-seed under remaining budget (never parallel full GPQA).
5. Do **not** set `ICML_READY` STATUS: READY from offline / preflight alone.

