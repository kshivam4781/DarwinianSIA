# Gate 4 report — 5-seed B vs D

**Timestamp:** 2026-08-30T04:13:02Z
**Mode:** `preflight`
**Live G4 ready:** no
**PRIMARY pass (≥3/5):** no

## Live G4 preflight

| Check | OK | Detail |
|-------|----|--------|
| `gpqa_layout` | yes | ok |
| `gpqa_not_synthetic` | NO | synthetic smoke fixture detected — fetch real GPQA diamond before paid G4 |
| `anthropic_key` | NO | ANTHROPIC_API_KEY missing |
| `nebius_key` | NO | NEBIUS_API_KEY missing |
| `hf_token_optional` | yes | missing (optional; needed for HF gpqa download) |
| `budget` | yes | spent=$0.00 ceiling=$20.00 estimate=$3.00/pair × 5 → projected=$15.00 |
| `run_ids_free` | yes | all planned run IDs unused |
| `sequential_only` | yes | 5 seed pair(s); runner executes B then D serially (no parallel GPQA) |
| `seed_count` | yes | 5 seeds (G4 full multi-seed shape) |
| `per_run_venv` | yes | uv available at /home/ubuntu/.local/bin/uv (SIA per-run venv path) |
| `runtime_deps` | yes | uv available at /home/ubuntu/.local/bin/uv; sia importable via PYTHONPATH=/workspace/SIA; huggingface_hub already importable |

### Planned seed pairs

| Seed | Condition B | Condition D |
|------|-------------|-------------|
| 1 | B `1211` | D `1311` |
| 2 | B `1212` | D `1312` |
| 3 | B `1213` | D `1313` |
| 4 | B `1214` | D `1314` |
| 5 | B `1215` | D `1315` |

### Planned commands (sequential: B then D per seed; never parallel)

1. `/usr/bin/python3 -m sia run --task gpqa --darwinian --population_size 4 --elite_count 2 --max_gen 5 --run_id 1211 --eval_subset 15 --no-web --seed 1`
2. `/usr/bin/python3 -m sia run --task gpqa --darwinian --population_size 4 --elite_count 2 --max_gen 5 --run_id 1311 --eval_subset 15 --no-web --seed 1 --cabs --cabs-inline`
3. `/usr/bin/python3 -m sia run --task gpqa --darwinian --population_size 4 --elite_count 2 --max_gen 5 --run_id 1212 --eval_subset 15 --no-web --seed 2`
4. `/usr/bin/python3 -m sia run --task gpqa --darwinian --population_size 4 --elite_count 2 --max_gen 5 --run_id 1312 --eval_subset 15 --no-web --seed 2 --cabs --cabs-inline`
5. `/usr/bin/python3 -m sia run --task gpqa --darwinian --population_size 4 --elite_count 2 --max_gen 5 --run_id 1213 --eval_subset 15 --no-web --seed 3`
6. `/usr/bin/python3 -m sia run --task gpqa --darwinian --population_size 4 --elite_count 2 --max_gen 5 --run_id 1313 --eval_subset 15 --no-web --seed 3 --cabs --cabs-inline`
7. `/usr/bin/python3 -m sia run --task gpqa --darwinian --population_size 4 --elite_count 2 --max_gen 5 --run_id 1214 --eval_subset 15 --no-web --seed 4`
8. `/usr/bin/python3 -m sia run --task gpqa --darwinian --population_size 4 --elite_count 2 --max_gen 5 --run_id 1314 --eval_subset 15 --no-web --seed 4 --cabs --cabs-inline`
9. `/usr/bin/python3 -m sia run --task gpqa --darwinian --population_size 4 --elite_count 2 --max_gen 5 --run_id 1215 --eval_subset 15 --no-web --seed 5`
10. `/usr/bin/python3 -m sia run --task gpqa --darwinian --population_size 4 --elite_count 2 --max_gen 5 --run_id 1315 --eval_subset 15 --no-web --seed 5 --cabs --cabs-inline`

## Blockers (live G4)

- gpqa_not_synthetic: synthetic smoke fixture detected — fetch real GPQA diamond before paid G4
- anthropic_key: ANTHROPIC_API_KEY missing
- nebius_key: NEBIUS_API_KEY missing

**Live G4 status:** NOT RUN this tick

## Next

1. Ensure live G2 smoke + G3 pilot passed before spending on G4.
2. Add `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` (+ `HF_TOKEN` for `--fetch-diamond`).
3. Budget-check (`SIA_BUDGET_*` + `SIA_G4_PAIR_ESTIMATE_USD`), then:
   `python scripts/run_g4_multiseed.py --live --seeds 1,2,3,4,5 --b-run-ids 1211,1212,1213,1214,1215 --d-run-ids 1311,1312,1313,1314,1315 --fetch-diamond`
4. After paid pairs, paper pack auto-refreshes Table 1/2 + Figs 1–2 + ICML_READY (or recover via `--refresh-paper-from-runs`).
5. Do **not** set STATUS: READY from offline / G4 preflight alone.

