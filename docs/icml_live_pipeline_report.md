# ICML live pipeline report — G2 → G3 → G4

**Timestamp:** 2026-09-04T14:08:06Z
**Mode:** `preflight`
**Ready for live stack:** no
**ICML_READY:** IN_PROGRESS

## Budget projection

| Item | USD |
|------|-----|
| spent (env) | 0.00 |
| G2 estimate | 2.00 |
| G3 estimate | 3.00 |
| G4 estimate | 14.00 |
| stack estimate | 19.00 |
| projected total | 19.00 |
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
- G2: nebius_key: NEBIUS_API_KEY missing
- G2: hf_token: HF_TOKEN / HUGGINGFACE_HUB_TOKEN missing (required for --fetch-diamond)
- G3: gpqa_not_synthetic: synthetic smoke fixture detected — fetch real GPQA diamond before paid G3
- G3: nebius_key: NEBIUS_API_KEY missing
- G3: hf_token: HF_TOKEN / HUGGINGFACE_HUB_TOKEN missing (required for --fetch-diamond)
- G4: gpqa_not_synthetic: synthetic smoke fixture detected — fetch real GPQA diamond before paid G4
- G4: nebius_key: NEBIUS_API_KEY missing
- G4: hf_token: HF_TOKEN / HUGGINGFACE_HUB_TOKEN missing (required for --fetch-diamond)
- HF_TOKEN / HUGGINGFACE_HUB_TOKEN missing (required for --fetch-diamond / cron auto-live)

## Notes

- diamond fetch failed (preflight continues): HF_TOKEN / HUGGINGFACE_HUB_TOKEN required to download gated Idavidrein/gpqa. Accept dataset terms on HuggingFace, then set the token.
- Tick 296 G3/G4 shape: eval_subset=5 pop=4 elite=2 max_gen=6
- Tick 299: committed G3/G4 recipes match live shape 5/4/2/6
- Tick 300–301: offline Bvd summary matches live shape 5/4/2/6 (paper/READY/Section12 ID citations locked)

## Next

1. Merge the latest ICML tip PR into `main` so cron inherits `docs/ICML_*` + `scripts/icml_cron_entry.sh` (Tick 327–335 dual unblock; `main` still has hackathon-era AGENTS without tip files). See `docs/ICML_HUMAN_UNBLOCK.md` Dual human unblock. Concrete tip PR: #336 https://github.com/kshivam4781/DarwinianSIA/pull/336 — GitHub MERGEABLE/CLEAN: undraft & merge now (no conflicts).
2. Add `NEBIUS_API_KEY` + (`HF_TOKEN` **or** local `gpqa_diamond.csv`) to automation https://cursor.com/automations/bf73dff3-8f7a-11f1-a7d1-d6b4613131ce (or linked env dashboard). `ANTHROPIC_API_KEY` is optional with Tick 289 Nebius pydantic-ai meta (required only if `ICML_META_AGENT_PROFILE=default-meta`). Accept HF `Idavidrein/gpqa` if using HF. See `docs/ICML_HUMAN_UNBLOCK.md`.
3. Next cron (or now): `bash scripts/icml_cron_entry.sh` — auto-recovers tip and runs live when `fetch_diamond_ok` (else preflight only).
4. Portal Save of `docs/icml_portal_save_target.json` is **optional** (Tick 265–267: uv + runtime deps bootstrap in preflight).
5. Do **not** set STATUS: READY from offline / preflight alone.
