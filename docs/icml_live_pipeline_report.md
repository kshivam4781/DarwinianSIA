# ICML live pipeline report — G2 → G3 → G4

**Timestamp:** 2026-08-06T06:03:30Z
**Mode:** `preflight`
**Ready for live stack:** no
**ICML_READY:** IN_PROGRESS

## Budget projection

| Item | USD |
|------|-----|
| spent (env) | 0.00 |
| G2 estimate | 1.00 |
| G3 estimate | 4.00 |
| G4 estimate | 15.00 |
| stack estimate | 20.00 |
| projected total | 20.00 |
| ceiling | 20.00 |
| within ceiling | yes |

## Stages

| Stage | Attempted | OK | Exit | Detail |
|-------|-----------|----|------|--------|
| G2 | yes | yes | 0 | preflight invoked |
| G3 | yes | yes | 0 | preflight invoked |
| G4 | yes | yes | 0 | preflight invoked |

## G3→G4 gate

G3 promising: n/a (G3 not scored this run)

## Blockers

- G2: gpqa_not_synthetic: synthetic smoke fixture detected — replace with real GPQA diamond before paid G2
- G2: anthropic_key: ANTHROPIC_API_KEY missing
- G2: nebius_key: NEBIUS_API_KEY missing
- G3: gpqa_not_synthetic: synthetic smoke fixture detected — fetch real GPQA diamond before paid G3
- G3: anthropic_key: ANTHROPIC_API_KEY missing
- G3: nebius_key: NEBIUS_API_KEY missing
- G4: gpqa_not_synthetic: synthetic smoke fixture detected — fetch real GPQA diamond before paid G4
- G4: anthropic_key: ANTHROPIC_API_KEY missing
- G4: nebius_key: NEBIUS_API_KEY missing

## Next

1. Link a Cursor environment and inject `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` + `HF_TOKEN` (accepted `Idavidrein/gpqa`).
2. Budget-check, then:
   `python scripts/run_icml_live_pipeline.py --live --fetch-diamond`
3. Do **not** set STATUS: READY from offline / preflight alone.
