## Summary
- Tick 368: **live G3 H2 preferred-share + mean_final_gap** — after Tick 367 wired G4 paper/gate4 `d_wins_h2` / `h2_preferred_pass`, live G3 still scored only compare+H5 (no preferred-share H2 or `mean_final_gap` in gate3 live metrics). Now `score_pilot` returns H2 via `score_live_h2`; `write_gate3_report` surfaces mean_final_gap / primary_final_pass / d_wins_h2 / h2_preferred_pass + per-run preferred_share (G4 Tick 360/367 parity before 5-seed spend). Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_run_g3_pilot.py::test_write_gate3_report_surfaces_h2_and_mean_gap`
- [x] `pytest tests/test_run_g3_pilot.py::test_score_pilot_wires_compare`
- [x] `pytest tests/test_run_g4_multiseed.py::test_apply_paper_pack_prefers_compare_h2_preferred_pass`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
