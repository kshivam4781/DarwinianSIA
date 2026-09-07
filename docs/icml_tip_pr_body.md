## Summary
- Tick 372: **G2 resume post-run re-validation** — after Tick 371, a 0%-fitness G2 still writes `results.json` (`darwinian_run_complete` true), so the next cron would resume-skip G2 and auto-burn ~$19 on G3+G4. `sync_spent_from_completed_stages` now re-runs `validate_g2_artifacts` on local G2 artifacts and refuses resume-complete until gates pass (pick a new `--g2-run-id`; never overwrite). Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_run_icml_live_pipeline.py::test_g2_resume_refuses_zero_fitness_local_artifacts`
- [x] `pytest tests/test_run_g2_smoke.py::test_validate_g2_artifacts_nonzero_fitness_gate`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
