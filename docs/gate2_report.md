# Gate 2 report — GPQA smoke (Condition D)

**Timestamp:** 2026-10-05T10:25:17Z
**Mode:** `preflight`
**Run ID:** `1300`

## Preflight checks

| Check | OK | Detail |
|-------|----|--------|
| `gpqa_layout` | yes | ok |
| `gpqa_not_synthetic` | yes | real/non-smoke diamond_questions.json present |
| `gpqa_smoke_or_real` | yes | non-smoke questions present |
| `anthropic_key` | yes | optional (Nebius meta; ANTHROPIC unused) |
| `nebius_key` | NO | NEBIUS_API_KEY missing |
| `hf_token_optional` | yes | missing (optional; needed for HF gpqa download) |
| `budget` | yes | spent=$0.00 ceiling=$20.00 |
| `run_id_free` | yes | run_1300 unused |
| `per_run_venv` | yes | uv available on PATH (SIA per-run venv path) |
| `runtime_deps` | yes | uv available on PATH; sia importable via PYTHONPATH=SIA; huggingface_hub + pydantic_ai + matplotlib already importable; user site on PYTHONPATH |
| `nebius_meta_profile` | yes | kimi-nebius-pydantic-meta → nebius / pydantic-ai (moonshotai/Kimi-K2.6) |
| `nebius_target_profile` | yes | kimi-nebius-target → nebius (moonshotai/Kimi-K2.6) |
| `tip_ok_for_live` | yes | local Tick 542 matches remote tip refs/remotes/origin/cursor/icml-epistemic-results-9e39 |

**Ready for dry-run:** yes
**Ready for live G2:** no

## Planned command

```bash
python3 -m sia run --task gpqa --darwinian --cabs --cabs-inline --population_size 2 --elite_count 1 --max_gen 2 --run_id 1300 --eval_subset 5 --no-web --seed 42 --dry-run --meta-agent-profile kimi-nebius-pydantic-meta --target-agent-profile kimi-nebius-target
```

## Blockers

- nebius_key: NEBIUS_API_KEY missing

## Notes

- Tick 377 hydrate: env=$0.0000 ≥ ledger=$0.0000; no unbilled local completes
- runtime deps before diamond: uv available on PATH; sia importable via PYTHONPATH=SIA; huggingface_hub + pydantic_ai + matplotlib already importable; user site on PYTHONPATH
- materialized diamond from CSV → ['SIA/sia/tasks/gpqa', 'sia-upstream/sia/tasks/gpqa']

**G2 live status:** NOT RUN this tick

## Next

1. Add **`NEBIUS_API_KEY`** to the cloud environment (HF optional — Tick 497 public mirror / local `gpqa_diamond.csv`; see `docs/ICML_HUMAN_UNBLOCK.md`). Full phrase: `NEBIUS_API_KEY (ANTHROPIC_API_KEY optional — Tick 289 Nebius pydantic-ai meta)`.
2. Budget-check, then live G2 (unused integer run_id):
   `python3 scripts/run_g2_smoke.py --live --run-id <unused> --fetch-diamond`
3. Only then start live G3 B vs D pilot (Section 21.5).
