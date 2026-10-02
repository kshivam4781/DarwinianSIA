# Gate 2 report — GPQA smoke (Condition D)

**Timestamp:** 2026-10-02T22:06:48Z
**Mode:** `dry-run`
**Run ID:** `1956`

## Preflight checks

| Check | OK | Detail |
|-------|----|--------|

**Ready for dry-run:** yes
**Ready for live G2:** no

## Planned command

```bash

```

## Notes

- Tick 512: refreshed durable gate2_steering_lift_proof.json from dry-run run_1956 after fixing foreign CheckResult drop

## Post-run artifact validation

| Check | OK | Detail |
|-------|----|--------|
| `run_dir` | yes | /workspace/SIA/runs/run_1956 |
| `belief_store` | yes | /workspace/SIA/runs/run_1956/belief_store |
| `epistemic_value_jsonl` | yes | present |
| `cabs_json` | yes | contradictions/beliefs present |
| `scoped_mutation_bias` | yes | fields=['memory', 'planning_style', 'tool_strategy'] |
| `delay_all_feedback_skip` | yes | gen2 n=2 feedback prompts lack 'Contradiction-Aware Research Agenda' (delay-all) |
| `delay_all_technique_seeds_skip` | yes | gen2 n=2 DNA technique_seeds empty (delay-all) |
| `steering_applied_run_1956` | yes | gen3 n=2 agenda in ['agent_0', 'agent_1'] (delay-all lifted) |
| `steering_applied_gen3` | yes | Condition D n=1 gen≥3 steering evidenced |
| `nonzero_fitness` | yes | best=0.2440 > min=0 |

**G2 dry-run harness status:** PASS (not live G2)

## Next

1. Add `NEBIUS_API_KEY (ANTHROPIC_API_KEY optional — Tick 289 Nebius pydantic-ai meta) + (HF_TOKEN or local gpqa_diamond.csv or public OpenAI mirror auto-fetch — Tick 497)` to the cloud environment (see `docs/ICML_HUMAN_UNBLOCK.md`).
2. Materialize diamond (prefer public mirror — no HF):
   `python3 scripts/prepare_gpqa_diamond.py --from-public-mirror --n 5 --force`
   or HF (optional): `python3 scripts/prepare_gpqa_diamond.py --from-hf --n 5 --force`
   or let the runner autowire: `python3 scripts/run_g2_smoke.py --live --run-id <unused> --fetch-diamond`
3. Re-run live G2 after budget check (unused integer run_id).
4. Only then start live G3 B vs D pilot (Section 21.5).

