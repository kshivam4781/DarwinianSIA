## Summary
- Tick 384: **pipeline G2→G3 post-gate + prior_live_post preserve** — after Tick 383, pipeline resume-skip still advanced to paid G3 when the ledger marked G2 complete without re-checking gate2 post (cron preflight also wiped live `post=`). New `load_g2_post_for_g3` requires local validate or live/`prior_live_post` sidecar; direct G2 ledger-skip returns exit 4 without proven post; preflight preserves `prior_live_post`. Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_run_g2_smoke.py::test_write_gate2_preflight_preserves_prior_live_post`
- [x] `pytest tests/test_run_g2_smoke.py::test_g2_live_ledger_skip_refuses_without_post`
- [x] `pytest tests/test_run_icml_live_pipeline.py::test_load_g2_post_for_g3_trusts_prior_live_post`
- [x] `pytest tests/test_run_icml_live_pipeline.py::test_live_stack_refuses_g3_without_g2_post`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
