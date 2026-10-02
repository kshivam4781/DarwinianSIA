## Summary
- Tick 502: G2/G3/G4/pipeline `--live --fetch-diamond` keeps on-disk non-synthetic diamond and skips force HF rematerialize (`icml_fetch_diamond_needs_hf`) — Tick 499 `diamond_ready` parity on the fetch path. Live **PRIMARY** still blocked on **NEBIUS_API_KEY** (HF optional). Offline PRIMARY/H5 green at `1930–1934` / `1940–1944` (D final **5/5**, gens30/cost30 **4/5**, H5 **5/5**, H2 preferred **5/5**). STATUS remains IN_PROGRESS (not READY).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` so cron can run live G2→G3→G4.
- Tip PR anti-churn on `cursor/icml-epistemic-results-f49c` (#337). Prefer `docs/icml_open_git_pr_call.json` for `open_git_pr` (never omit branch=).

## Human unblock
1. Add `NEBIUS_API_KEY` (HF optional when diamond ready — Tick 497/502)
2. Optional: `gh pr edit 337 --title 'ICML Tick 502: add NEBIUS_API_KEY — live G2→G4 still blocked' --body-file docs/icml_tip_pr_body.md`
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_icml_env_checks.py::test_icml_fetch_diamond_needs_hf_skips_ondisk_nonsynthetic`
- [x] `pytest tests/test_run_g2_smoke.py::test_main_live_fetch_diamond_skips_hf_when_ondisk_nonsynthetic`
- [x] `pytest tests/test_run_g2_smoke.py::test_main_live_fetch_diamond_refuses_without_hf`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
