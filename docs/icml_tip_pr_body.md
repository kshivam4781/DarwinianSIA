## Summary
- Tick 379: **direct gate post-live ledger stamp** — Tick 377/378 hydrate bills unbilled completes *before* live but never marked `stages_complete`. Pipeline `bump_spent_reconciled` stamps stages; direct `run_g2_smoke.py` / `run_g3_pilot.py` / `run_g4_multiseed.py` `--live` previously left the ledger unstamped after success, so cross-VM cron (`runs/` gitignored) could re-launch a completed direct-gate stage and double-burn the ~$20 ceiling. New helper `persist_direct_gate_stage_spend` bills remaining unbilled completes and stamps G2/G3/G4 only when every planned run_id is complete. Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_icml_env_checks.py::test_persist_direct_gate_stamps_stage_and_bills`
- [x] `pytest tests/test_icml_env_checks.py::test_persist_direct_gate_incomplete_does_not_stamp`
- [x] `pytest tests/test_icml_env_checks.py::test_persist_direct_gate_no_double_bill`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
