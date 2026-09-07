## Summary
- Tick 376: **partial-stage spend reconcile** — after Tick 375, mid-stack complete G3/G4 pairs were still invisible to `SIA_BUDGET_SPENT_USD` until the whole stage finished, and pipeline `project_budget` still billed full N× pairs. Sync now reconciles complete-but-partial runs; preflight/live stack projects remaining pairs; post-G3/G4 uses absolute re-sync (no double-count). Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_run_icml_live_pipeline.py::test_sync_spent_bills_partial_g4_pairs`
- [x] `pytest tests/test_run_icml_live_pipeline.py::test_project_budget_uses_remaining_pairs_after_partial`
- [x] `pytest tests/test_run_icml_live_pipeline.py::test_remaining_seed_pairs_counts_incomplete`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass

