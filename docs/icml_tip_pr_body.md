## Summary
- Tick 387: **discard/tip-apply prior_live stash** — after Tick 386 completed the G2/G3/G4 `prior_live_*` write-path triad, tip recover still wiped paid sidecar evidence: `discard_ephemeral_icml_dirt` → `git restore` of gate JSON, then `git reset --hard` on tip `--apply`. New gitignored `docs/icml_prior_live_stash.json` captures prior_live before discard; cron / `icml_boot_recover.sh` reinject after tip apply. Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_icml_env_checks.py::test_discard_ephemeral_preserves_prior_live_via_stash`
- [x] `pytest tests/test_icml_env_checks.py::test_stash_prior_live_from_live_executed_gate3`
- [x] `pytest tests/test_icml_env_checks.py::test_stash_prior_live_from_live_gate2_post`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
