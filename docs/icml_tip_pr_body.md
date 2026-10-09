## Summary
- Tick 587: cold-boot rematerialize from greenfield boot `561f` → tip `9e39` (no tip peel); rematerialized offline Bvd `1930–1944` + Figs 1–2 + diamond; tip/secrets `cloud_boot_branch=cursor/icml-epistemic-results-561f`; lift proof `tick=587` / `local_run_present=false`.
- Live G2→G4 **PRIMARY** still blocked on **NEBIUS_API_KEY** (HF optional via Tick 497 public mirror / Tick 502–504 on-disk keep / Tick 557–558 dig DNS fallbacks). Offline PRIMARY/H5 green at `1930–1934` / `1940–1944` (D final **5/5**, gens30/cost30 **4/5**, H5 **5/5**, H2 preferred **5/5**; floor gen≥3 + tail=2). STATUS remains IN_PROGRESS (not READY).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` so cron can run live G2→G3→G4.

## Human unblock
1. Add `NEBIUS_API_KEY` (HF optional when diamond ready via public mirror / local CSV / on-disk keep)
2. Optional: undraft+merge this tip PR #339 and/or bootstrap PR #338
3. Then: `bash scripts/icml_cron_entry.sh` → live G2→G3→G4 + paper pack

## Test plan
- [x] Offline Bvd rematerialize `1930–1944` + Figs 1–2
- [x] G2/G3/G4 `--preflight-only` sole BLOCK `nebius_key`
- [x] Lift proof `tick=587` / `local_run_present=false`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
