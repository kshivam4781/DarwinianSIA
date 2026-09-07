## Summary
- Tick 367: **live G4 H2 preferred-pass aggregate** — Tick 366 added `d_wins_h2` / `h2_preferred_pass` for offline, but live G4 paper pack / gate4 metrics still showed only binary `skew_pass`. Now Live Table 1/2 + gate4 report surface `d_wins_h2=N/5` + `h2_preferred_pass`, and `apply_paper_pack` prefers the compare aggregate when n≥5 (same MECHANISM key as offline). Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_run_g4_multiseed.py::test_refresh_paper_artifacts_live_table`
- [x] `pytest tests/test_run_g4_multiseed.py::test_write_gate4_report_h2_surfaces_preferred_share`
- [x] `pytest tests/test_run_g4_multiseed.py::test_apply_paper_pack_prefers_compare_h2_preferred_pass`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
