# Gate 2 report — GPQA smoke (Condition D)

**Timestamp:** 2026-08-05T22:04:44Z
**Mode:** `preflight`
**Run ID:** `1850`

## Preflight checks

| Check | OK | Detail |
|-------|----|--------|
| `gpqa_layout` | yes | ok |
| `gpqa_not_synthetic` | NO | synthetic smoke fixture detected — replace with real GPQA diamond before paid G2 |
| `gpqa_smoke_or_real` | yes | synthetic smoke OK for dry-run/preflight |
| `anthropic_key` | NO | ANTHROPIC_API_KEY missing |
| `nebius_key` | NO | NEBIUS_API_KEY missing |
| `hf_token_optional` | yes | missing (optional; needed for HF gpqa download) |
| `budget` | yes | spent=$0.00 ceiling=$20.00 |
| `run_id_free` | yes | run_1850 unused |
| `python_venv_module` | yes | /usr/bin/python3 has venv |

**Ready for dry-run:** yes
**Ready for live G2:** no

## Planned command

```bash
/usr/bin/python3 -m sia run --task gpqa --darwinian --cabs --cabs-inline --population_size 2 --elite_count 1 --max_gen 2 --run_id 1850 --eval_subset 5 --no-web --seed 42 --dry-run
```

## Blockers

- gpqa_not_synthetic: synthetic smoke fixture detected — replace with real GPQA diamond before paid G2
- anthropic_key: ANTHROPIC_API_KEY missing
- nebius_key: NEBIUS_API_KEY missing

## Notes

- materialized synthetic GPQA smoke fixture under SIA/

**G2 live status:** NOT RUN this tick

## Next

1. Add `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` to the cloud environment.
2. Accept HF access for `Idavidrein/gpqa`, set `HF_TOKEN`, then either:
   `python scripts/prepare_gpqa_diamond.py --from-hf --n 5 --force`
   or `python scripts/run_g2_smoke.py --live --run-id <unused> --fetch-diamond`
3. Re-run live G2 after budget check (unused integer run_id).
4. Only then start live G3 B vs D pilot (Section 21.5).

