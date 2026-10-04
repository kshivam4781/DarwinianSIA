## Summary
- Tick 536: check secrets status / human unblock. Offline PRIMARY/H5 green at `1930–1934` / `1940–1944`. STATUS remains IN_PROGRESS (not READY).
- Check `docs/icml_secrets_status.json` / `docs/ICML_HUMAN_UNBLOCK.md` for NEBIUS (+ optional HF/CSV / Tick 497 mirror) gates.
- Tip recover / chicken-egg + prior_live stack (see `docs/ICML_PROGRESS.md`); tip PR anti-churn on this PR (`cursor/icml-epistemic-results-9e39`). Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`). See `docs/ICML_PROGRESS.md` for Tick 536 detail.

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #N and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_icml_env_checks.py::test_suggested_open_git_pr_body_secrets_first_generic`
- [x] `pytest tests/test_icml_env_checks.py::test_detect_gpqa_is_synthetic_and_secrets_auto_probe`
- [x] `pytest tests/test_icml_env_checks.py::test_cron_refreshes_secrets_after_preflight`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
