## Summary
- Tick 378: **direct G2 budget hydrate** — Tick 377 wired `hydrate_direct_gate_budget_spent` into G3/G4, but direct `run_g2_smoke.py --live` still read `SIA_BUDGET_SPENT_USD` from env only (often 0). After prior G3/G4 spend in the ledger, G2 could green-light over the ~$20 ceiling. G2 preflight now hydrates via `run_estimate_usd` (single-run fallback; G3/G4 keep `pair_estimate_usd`). Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_icml_env_checks.py::test_hydrate_direct_gate_run_estimate_usd`
- [x] `pytest tests/test_run_g2_smoke.py::test_g2_preflight_hydrates_budget_from_ledger`
- [x] `pytest tests/test_run_g2_smoke.py::test_g2_preflight_hydrates_budget_from_unbilled_local`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
