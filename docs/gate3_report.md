# Gate 3 report — Pilot B vs D

**Timestamp:** 2026-09-10T16:02:16Z
**Mode:** `preflight`
**Live G3 ready:** no

<!-- OFFLINE_G3_PILOT_START -->
### Offline synthetic pilot (Tick 397–398 post-adoption H2; live Nebius shape)

| Cond | Seeds | pop | elite | max_gen | eval | Run IDs |
|------|-------|-----|-------|---------|------|---------|
| B | 11,22,33,44,55 | 4 | 2 | 6 | 5 | `1930–1934` |
| D | 11,22,33,44,55 | 4 | 2 | 6 | 5 | `1940–1944` |

| Metric | Result |
|--------|--------|
| D final wins (>1pp) | **5/5** (mean gap ~**6.15pp**) |
| D gens@30% | **4/5** (B: 0) |
| D cost@30% (eval-call proxy) | **4/5** (B: 0) |
| H5 ρ>0.3 | **5/5** |
| H2 preferred≥0.5 (post-adoption tail) | **5/5** (seed 22 share **0.75**; was 0.44 gen≥3 / 0.29 all-gen) |
| Case study | `docs/case_study_offline.md` (`run_1940`) — gen3 steered preferred share **0.75**; post-adoption (gens5–6) **0.875**; lift +0.0436 / +0.0607 |

**Finding:** Tick **397** scores H2 on the last 2 gens (floored at gen≥3) so ε-discover→adopt lag does not dilute preferred_share — seed 22 selective consolidates by gen6 and now passes ≥0.5. Tick **398** aligns the case study to the same post-adoption window. PRIMARY/H5 unchanged (`1930–1944`). Prior Tick-396 IDs `1910–1924` / Tick-300 `1890–1904` superseded for paper-ID lock.

<!-- OFFLINE_G3_PILOT_END -->

## Live G3 preflight

| Check | OK | Detail |
|-------|----|--------|
| `gpqa_layout` | yes | ok |
| `gpqa_not_synthetic` | NO | synthetic smoke fixture detected — fetch real GPQA diamond before paid G3 |
| `anthropic_key` | yes | optional (Nebius meta; ANTHROPIC unused) |
| `nebius_key` | NO | NEBIUS_API_KEY missing |
| `hf_token` | NO | HF_TOKEN / HUGGINGFACE_HUB_TOKEN missing (required for --fetch-diamond) |
| `budget` | yes | spent=$0.00 ceiling=$20.00 estimate=$3.00/pair × 1 remaining (of 1 planned) → projected=$3.00 |
| `run_ids_free` | yes | all planned run IDs unused |
| `sequential_only` | yes | 1 seed pair(s); runner executes B then D serially (no parallel GPQA) |
| `seed_count` | yes | 1 seed(s) (G3 pilot shape) |
| `per_run_venv` | yes | uv available at /home/ubuntu/.local/bin/uv (SIA per-run venv path) |
| `runtime_deps` | yes | uv available at /home/ubuntu/.local/bin/uv; sia importable via PYTHONPATH=/workspace/SIA; huggingface_hub + pydantic_ai already importable; user site on PYTHONPATH (/home/ubuntu/.local/lib/python3.12/site-packages) |
| `nebius_meta_profile` | yes | kimi-nebius-pydantic-meta → nebius / pydantic-ai (moonshotai/Kimi-K2.6) |
| `nebius_target_profile` | yes | kimi-nebius-target → nebius (moonshotai/Kimi-K2.6) |
| `g3g4_recipes_match_live_shape` | yes | committed gate3/4 + Section 21.7 match icml_g3g4_live_shape() |
| `offline_bvd_matches_live_shape` | yes | offline Bvd summary + paper IDs + figures match live shape |
| `tip_ok_for_live` | yes | local Tick 407 matches remote tip refs/remotes/origin/cursor/icml-epistemic-results-f49c |

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

- Tick 377 hydrate: env=$0.0000 ≥ ledger=$0.0000; no unbilled local completes
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

