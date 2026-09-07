## Summary
- Tick 366: **offline H2 preferred-pass aggregate** — after Tick 365 surfaced honest preferred shares (seed 22 ≈0.29), compare/paper still lacked a MECHANISM seed-win count. Now `compare_b_vs_d` emits `d_wins_h2` / `h2_preferred_pass` (≥3/5 preferred_share≥0.5); offline brief adds `D_h2_pass`; gate3 + Table 2 report **4/5** (seed 22 fail; case study still covers MECHANISM). Builds on Tick 364–365 preferred-share alignment. Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_offline_case_study_steered.py::test_offline_compare_brief_emits_h2_pass`
- [x] `pytest tests/test_run_g4_multiseed.py::test_compare_b_vs_d_h2_preferred_aggregate`
- [x] `pytest tests/test_run_g4_multiseed.py::test_h2_h5_pass_helpers`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
