# ICML live pipeline report — G2 → G3 → G4

**Timestamp:** 2026-08-31T06:03:43Z
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
| G2 | yes | yes | 0 | preflight invoked (+fetch-diamond) |
| G3 | yes | yes | 0 | preflight invoked (+fetch-diamond) |
| G4 | yes | yes | 0 | preflight invoked (+fetch-diamond) |

## G3→G4 gate

G3 promising: n/a (G3 not scored this run)

## Blockers

- G2: gpqa_not_synthetic: synthetic smoke fixture detected — replace with real GPQA diamond before paid G2
- G2: anthropic_key: ANTHROPIC_API_KEY missing
- G2: nebius_key: NEBIUS_API_KEY missing
- G2: hf_token: HF_TOKEN / HUGGINGFACE_HUB_TOKEN missing (required for --fetch-diamond)
- G3: gpqa_not_synthetic: synthetic smoke fixture detected — fetch real GPQA diamond before paid G3
- G3: anthropic_key: ANTHROPIC_API_KEY missing
- G3: nebius_key: NEBIUS_API_KEY missing
- G3: hf_token: HF_TOKEN / HUGGINGFACE_HUB_TOKEN missing (required for --fetch-diamond)
- G4: gpqa_not_synthetic: synthetic smoke fixture detected — fetch real GPQA diamond before paid G4
- G4: anthropic_key: ANTHROPIC_API_KEY missing
- G4: nebius_key: NEBIUS_API_KEY missing
- G4: hf_token: HF_TOKEN / HUGGINGFACE_HUB_TOKEN missing (required for --fetch-diamond)
- HF_TOKEN / HUGGINGFACE_HUB_TOKEN missing (required for --fetch-diamond / cron auto-live)

## Notes

- diamond fetch failed (preflight continues): HF_TOKEN / HUGGINGFACE_HUB_TOKEN required to download gated Idavidrein/gpqa. Accept dataset terms on HuggingFace, then set the token.

## Next

1. Add `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` + (`HF_TOKEN` **or** local `gpqa_diamond.csv`) to automation https://cursor.com/automations/bf73dff3-8f7a-11f1-a7d1-d6b4613131ce (or linked env dashboard). Accept HF `Idavidrein/gpqa` if using HF. See `docs/ICML_HUMAN_UNBLOCK.md`.
2. Next cron (or now): `bash scripts/icml_cron_entry.sh` — auto-recovers tip and runs live when `fetch_diamond_ok` (else preflight only).
3. Portal Save of `docs/icml_portal_save_target.json` is **optional** (Tick 265–267: uv + runtime deps bootstrap in preflight).
4. Do **not** set STATUS: READY from offline / preflight alone.
