## Summary
- Tick 392: **chicken-egg tip-apply without tip module** — Tick 391 filtered gitignore-lag durables only when `scripts/icml_env_checks.py` was already present; greenfield/main boots pipe `icml_boot_recover.sh` from tip but still refused `--apply` on `?? docs/icml_cloud_boot_branch.txt` because the Python filter never ran. Tick 392 inlines the same IGNORE set in `icml_boot_recover.sh` / `icml_cron_entry.sh` when the tip module is absent (evidence still blocks — Tick 390). Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_icml_env_checks.py::test_tip_apply_ignores_gitignore_lag_boot_and_call`
- [x] `pytest tests/test_icml_env_checks.py::test_discard_ephemeral_gitignore_lag_boot_ok`
- [x] `pytest tests/test_icml_env_checks.py::test_tip_apply_blocks_dirty_prior_live_evidence` (Tick 390)
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
