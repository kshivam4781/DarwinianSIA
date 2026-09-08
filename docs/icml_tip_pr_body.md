## Summary
- Tick 383: **direct G2 ledger-skip post-validation refresh** — Tick 380 skips paid direct G2 `--live` when the ledger marks G2 complete, but wrote gate2 without `post=` and could wipe live-executed nonzero-fitness / belief_store evidence. New helper `refresh_g2_post_on_ledger_skip` re-validates local G2 or trusts a live-executed gate2 sidecar (never invents post from preflight). Closes G2 half of the G3 Tick 382 / G4 Tick 381 ledger-skip refresh triad. Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_run_g2_smoke.py::test_refresh_g2_post_on_ledger_skip_local_dirs`
- [x] `pytest tests/test_run_g2_smoke.py::test_refresh_g2_post_on_ledger_skip_trusts_sidecar`
- [x] `pytest tests/test_run_g2_smoke.py::test_g2_live_ledger_skip_refreshes_post`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
