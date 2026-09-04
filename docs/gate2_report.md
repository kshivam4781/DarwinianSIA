# Gate 2 report — GPQA smoke (Condition D)

**Timestamp:** 2026-09-04T10:04:21Z
**Mode:** `preflight`
**Run ID:** `1300`

## Preflight checks

| Check | OK | Detail |
|-------|----|--------|
| `gpqa_layout` | yes | ok |
| `gpqa_not_synthetic` | NO | synthetic smoke fixture detected — replace with real GPQA diamond before paid G2 |
| `gpqa_smoke_or_real` | yes | synthetic smoke OK for dry-run/preflight |
| `anthropic_key` | yes | optional (Nebius meta; ANTHROPIC unused) |
| `nebius_key` | NO | NEBIUS_API_KEY missing |
| `hf_token` | NO | HF_TOKEN / HUGGINGFACE_HUB_TOKEN missing (required for --fetch-diamond) |
| `budget` | yes | spent=$0.00 ceiling=$20.00 |
| `run_id_free` | yes | run_1300 unused |
| `per_run_venv` | yes | uv available at /home/ubuntu/.local/bin/uv (SIA per-run venv path) |
| `runtime_deps` | yes | uv available at /home/ubuntu/.local/bin/uv; sia importable via PYTHONPATH=/workspace/SIA; huggingface_hub + pydantic_ai already importable; user site on PYTHONPATH (/home/ubuntu/.local/lib/python3.12/site-packages) |
| `nebius_meta_profile` | yes | kimi-nebius-pydantic-meta → nebius / pydantic-ai (moonshotai/Kimi-K2.6) |
| `nebius_target_profile` | yes | kimi-nebius-target → nebius (moonshotai/Kimi-K2.6) |
| `tip_ok_for_live` | yes | local Tick 333 matches remote tip refs/remotes/origin/cursor/icml-epistemic-results-cd84 |

**Ready for dry-run:** yes
**Ready for live G2:** no

## Planned command

```bash
/usr/bin/python3 -m sia run --task gpqa --darwinian --cabs --cabs-inline --population_size 2 --elite_count 1 --max_gen 2 --run_id 1300 --eval_subset 5 --no-web --seed 42 --dry-run --meta-agent-profile kimi-nebius-pydantic-meta --target-agent-profile kimi-nebius-target
```

## Blockers

- gpqa_not_synthetic: synthetic smoke fixture detected — replace with real GPQA diamond before paid G2
- nebius_key: NEBIUS_API_KEY missing
- hf_token: HF_TOKEN / HUGGINGFACE_HUB_TOKEN missing (required for --fetch-diamond)

## Notes

- materialized synthetic GPQA smoke fixture under SIA/
- runtime deps before diamond: uv available at /home/ubuntu/.local/bin/uv; sia importable via PYTHONPATH=/workspace/SIA; huggingface_hub + pydantic_ai already importable; user site on PYTHONPATH (/home/ubuntu/.local/lib/python3.12/site-packages)
- diamond fetch failed: HF_TOKEN / HUGGINGFACE_HUB_TOKEN required to download gated Idavidrein/gpqa. Accept dataset terms on HuggingFace, then set the token.

**G2 live status:** NOT RUN this tick

## Next

1. Add `NEBIUS_API_KEY (ANTHROPIC_API_KEY optional — Tick 289 Nebius pydantic-ai meta) + (HF_TOKEN or local gpqa_diamond.csv)` to the cloud environment (see `docs/ICML_HUMAN_UNBLOCK.md`).
2. Accept HF access for `Idavidrein/gpqa` (or drop local `gpqa_diamond.csv`), then either:
   `python3 scripts/prepare_gpqa_diamond.py --from-hf --n 5 --force`
   or `python3 scripts/run_g2_smoke.py --live --run-id <unused> --fetch-diamond`
3. Re-run live G2 after budget check (unused integer run_id).
4. Only then start live G3 B vs D pilot (Section 21.5).

