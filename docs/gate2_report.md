# Gate 2 report — GPQA smoke (Condition D)

**Timestamp:** 2026-08-31T16:03:44Z
**Mode:** `dry-run`
**Run ID:** `1857`

## Preflight checks

| Check | OK | Detail |
|-------|----|--------|
| `gpqa_layout` | yes | ok |
| `gpqa_not_synthetic` | NO | synthetic smoke fixture detected — replace with real GPQA diamond before paid G2 |
| `gpqa_smoke_or_real` | yes | synthetic smoke OK for dry-run/preflight |
| `anthropic_key` | yes | optional (Nebius meta; ANTHROPIC unused) |
| `nebius_key` | NO | NEBIUS_API_KEY missing |
| `hf_token_optional` | yes | missing (optional; needed for HF gpqa download) |
| `budget` | yes | spent=$0.00 ceiling=$20.00 |
| `run_id_free` | yes | run_1857 unused |
| `per_run_venv` | yes | uv available at /home/ubuntu/.local/bin/uv (SIA per-run venv path) |
| `runtime_deps` | yes | uv available at /home/ubuntu/.local/bin/uv; sia importable via PYTHONPATH=/workspace/SIA; huggingface_hub + pydantic_ai already importable; user site on PYTHONPATH (/home/ubuntu/.local/lib/python3.12/site-packages) |
| `nebius_meta_profile` | yes | kimi-nebius-pydantic-meta → nebius / pydantic-ai (moonshotai/Kimi-K2.6) |
| `nebius_target_profile` | yes | kimi-nebius-target → nebius (moonshotai/Kimi-K2.6) |

**Ready for dry-run:** yes
**Ready for live G2:** no

## Planned command

```bash
/usr/bin/python3 -m sia run --task gpqa --darwinian --cabs --cabs-inline --population_size 2 --elite_count 1 --max_gen 2 --run_id 1857 --eval_subset 5 --no-web --seed 42 --dry-run --meta-agent-profile kimi-nebius-pydantic-meta --target-agent-profile kimi-nebius-target
```

## Blockers

- gpqa_not_synthetic: synthetic smoke fixture detected — replace with real GPQA diamond before paid G2
- nebius_key: NEBIUS_API_KEY missing

## Post-run artifact validation

| Check | OK | Detail |
|-------|----|--------|
| `run_dir` | yes | /workspace/SIA/runs/run_1857 |
| `belief_store` | yes | /workspace/SIA/runs/run_1857/belief_store |
| `epistemic_value_jsonl` | yes | present |
| `cabs_json` | yes | contradictions/beliefs present |
| `scoped_mutation_bias` | yes | fields=['memory', 'tool_strategy'] |

**G2 dry-run harness status:** PASS (not live G2)

## Next

1. Add `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` to the cloud environment.
2. Accept HF access for `Idavidrein/gpqa`, set `HF_TOKEN`, then either:
   `python scripts/prepare_gpqa_diamond.py --from-hf --n 5 --force`
   or `python scripts/run_g2_smoke.py --live --run-id <unused> --fetch-diamond`
3. Re-run live G2 after budget check (unused integer run_id).
4. Only then start live G3 B vs D pilot (Section 21.5).

