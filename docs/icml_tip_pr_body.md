## Summary
- Tick 370: **G3→G4 PRIMARY-only promising gate** — after Tick 369 surfaced H2 + `mean_final_gap` in the live pipeline report, `g3_pilot_promising` could still auto-spend ~$14 on 5-seed G4 when the pilot had **only** H5 ρ>0.3 (no PRIMARY-shaped D win). Now the gate requires gens/cost/final wins or mean_final_gap>1pp; H5/H2 stay in the report; use `--force-g4` to override. Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_run_icml_live_pipeline.py::test_g3_pilot_promising_on_d_win`
- [x] `pytest tests/test_run_icml_live_pipeline.py::test_write_pipeline_report_surfaces_g3_h2_and_mean_gap`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
