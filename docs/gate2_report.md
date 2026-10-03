# Gate 2 report — GPQA smoke (Condition D)

**Timestamp:** 2026-10-03T00:04:13Z
**Mode:** `dry-run`
**Run ID:** `1957`

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
| `run_id_free` | yes | run_1957 unused |
| `per_run_venv` | yes | uv available at /home/ubuntu/.local/bin/uv (SIA per-run venv path) |
| `runtime_deps` | yes | uv available at /home/ubuntu/.local/bin/uv; sia importable via PYTHONPATH=/workspace/SIA; huggingface_hub + pydantic_ai already importable; user site on PYTHONPATH (/home/ubuntu/.local/lib/python3.12/site-packages) |
| `nebius_meta_profile` | yes | kimi-nebius-pydantic-meta → nebius / pydantic-ai (moonshotai/Kimi-K2.6) |
| `nebius_target_profile` | yes | kimi-nebius-target → nebius (moonshotai/Kimi-K2.6) |
| `tip_ok_for_live` | yes | local Tick 512 matches remote tip refs/remotes/origin/cursor/icml-epistemic-results-f49c |

**Ready for dry-run:** yes
**Ready for live G2:** no

## Planned command

```bash
/usr/bin/python3 -m sia run --task gpqa --darwinian --cabs --cabs-inline --population_size 2 --elite_count 1 --max_gen 3 --run_id 1957 --eval_subset 5 --no-web --seed 42 --dry-run --meta-agent-profile kimi-nebius-pydantic-meta --target-agent-profile kimi-nebius-target
```

## Blockers

- nebius_key: NEBIUS_API_KEY missing

## Notes

- Tick 377 hydrate: env=$0.0000 ≥ ledger=$0.0000; no unbilled local completes
- Tick 509: dry-run max_gen=3 — post-checks require gen≥3 Contradiction-Aware agenda (delay-all lift positive control)

## Post-run artifact validation

| Check | OK | Detail |
|-------|----|--------|
| `run_dir` | yes | SIA/runs/run_1957 |
| `belief_store` | yes | SIA/runs/run_1957/belief_store |
| `epistemic_value_jsonl` | yes | present |
| `cabs_json` | yes | contradictions/beliefs present |
| `scoped_mutation_bias` | yes | fields=['memory', 'planning_style', 'tool_strategy'] |
| `delay_all_feedback_skip` | yes | gen2 n=2 feedback prompts lack 'Contradiction-Aware Research Agenda' (delay-all) |
| `delay_all_technique_seeds_skip` | yes | gen2 n=2 DNA technique_seeds empty (delay-all) |
| `steering_applied_run_1957` | yes | gen3 n=2 agenda in ['agent_0', 'agent_1'] (delay-all lifted) |
| `steering_applied_gen3` | yes | Condition D n=1 gen≥3 steering evidenced |
| `nonzero_fitness` | yes | best=0.2440 > min=0 |

**G2 dry-run harness status:** PASS (not live G2)

## Next

1. Add **`NEBIUS_API_KEY`** to the cloud environment (HF optional — Tick 497 public mirror / local `gpqa_diamond.csv`; see `docs/ICML_HUMAN_UNBLOCK.md`). Full phrase: `NEBIUS_API_KEY (ANTHROPIC_API_KEY optional — Tick 289 Nebius pydantic-ai meta)`.
2. Budget-check, then live G2 (unused integer run_id):
   `python3 scripts/run_g2_smoke.py --live --run-id <unused> --fetch-diamond`
3. Only then start live G3 B vs D pilot (Section 21.5).

