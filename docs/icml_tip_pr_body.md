## Summary
- Tick 377: **direct G3/G4 budget hydrate** — after Tick 376, pipeline sync billed mid-stack partials, but direct `run_g3_pilot.py --live` / `run_g4_multiseed.py --live` still read `SIA_BUDGET_SPENT_USD` from env only (often 0). Mid-stack resume after a crash could green-light remaining pairs over the ~$20 ceiling. `hydrate_direct_gate_budget_spent` now loads the ledger and bills unbilled local complete runs before the gate budget check (no `stages_complete` stamp). Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_icml_env_checks.py::test_hydrate_direct_gate_bills_unbilled_local`
- [x] `pytest tests/test_icml_env_checks.py::test_hydrate_direct_gate_skips_ledger_ids`
- [x] `pytest tests/test_run_g4_multiseed.py::test_g4_preflight_hydrates_budget_from_unbilled_local`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
