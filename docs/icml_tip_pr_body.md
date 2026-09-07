## Summary
- Tick 369: **live pipeline G3 H2 + mean_final_gap surfacing** — after Tick 368 wrote preferred-share H2 + `mean_final_gap` into gate3 live metrics/sidecar, `run_icml_live_pipeline` still showed only a binary `g3_promising` flag (ignored `h2_by_d_run`). Now `_load_gate3_sidecar` returns H2; `write_pipeline_report` surfaces mean_final_gap / primary_final_pass / d_wins_h2 / preferred_share in the G3→G4 gate (operators reading `icml_live_pipeline_report.md` see MECHANISM + PRIMARY (c) before 5-seed spend). Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_run_icml_live_pipeline.py::test_write_pipeline_report_surfaces_g3_h2_and_mean_gap`
- [x] `pytest tests/test_run_icml_live_pipeline.py::test_load_gate3_sidecar_returns_h2`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
