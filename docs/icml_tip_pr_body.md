## Summary
- Tick 375: **partial G3/G4 pair resume** — after Tick 374, a mid-stack crash that left only *some* B/D pairs complete still bricked the next cron (`run_ids_free` occupied + full N× pair budget). `classify_plan_run_occupancy` + `run_sequential_live` now resume-skip complete Darwinian runs; incomplete dirs still block (never overwrite); G3/G4/pipeline budget projects remaining pairs only. Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_run_g3_pilot.py::test_classify_plan_run_occupancy_resume_vs_incomplete`
- [x] `pytest tests/test_run_g3_pilot.py::test_g3_preflight_resume_skips_complete_run_ids`
- [x] `pytest tests/test_run_g3_pilot.py::test_run_sequential_live_resume_skips_complete`
- [x] `pytest tests/test_run_g4_multiseed.py::test_g4_preflight_resume_skips_complete_run_ids`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
