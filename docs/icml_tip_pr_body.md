## Summary
- Tick 355: tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345 title finding; Tick 346 body confirmation; Tick 347 independent ``tip_pr_body_stale``; Tick 348–349 pass ``description=`` from `open_git_pr_description` in `docs/icml_open_git_pr.json` or `docs/icml_tip_pr_body.md`; Tick 350: prefer verbatim args from `docs/icml_open_git_pr_call.json`; Tick 353–355: cron exports `ICML_CLOUD_BOOT_BRANCH` before tip recover; Tick 354 ignores env==tip + persists `docs/icml_cloud_boot_branch.txt`; Tick 355 unsets env==tip and does not clobber the boot file with tip). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_icml_env_checks.py::test_suggested_open_git_pr_title_secrets_first_when_stale`
- [x] `pytest tests/test_icml_env_checks.py::test_tip_pr_body_stale_independent_of_title`
- [x] `pytest tests/test_icml_env_checks.py::test_open_git_pr_pass_description_when_body_stale`
- [x] `pytest tests/test_icml_env_checks.py::test_open_git_pr_description_inline_in_json`
- [x] `pytest tests/test_icml_env_checks.py::test_open_git_pr_call_json_atomic_mcp_args`
- [x] `pytest tests/test_icml_env_checks.py::test_detect_cloud_boot_branch_env_and_mismatch`
- [x] `pytest tests/test_icml_env_checks.py::test_cron_entry_captures_boot_branch_before_tip_recover`
- [x] `pytest tests/test_icml_env_checks.py::test_detect_cloud_boot_branch_ignores_env_eq_tip`
- [x] `pytest tests/test_icml_env_checks.py::test_cron_entry_unsets_env_eq_tip_no_boot_clobber`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
