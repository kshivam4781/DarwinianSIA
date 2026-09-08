## Summary
- Tick 385: **pipeline G3→G4 prior_live_metrics preserve** — after Tick 384, cron `--preflight-only` still wiped live gate3 `comparison`/H2/H5 (mode=preflight, executed=False), so `load_g3_metrics_for_g4` / direct G3 ledger-skip could not trust paid G3 evidence cross-VM. New `prior_live_metrics` preserved in `write_gate3_report`; `_live_metrics_from_gate3_sidecar` + `load_g3_metrics_for_g4` / `refresh_g3_metrics_on_ledger_skip` trust it (Tick 384 gate2 `prior_live_post` parity). Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_run_g3_pilot.py::test_write_gate3_preflight_preserves_prior_live_metrics`
- [x] `pytest tests/test_run_g3_pilot.py::test_refresh_g3_metrics_on_ledger_skip_trusts_prior_live_metrics`
- [x] `pytest tests/test_run_icml_live_pipeline.py::test_load_g3_metrics_for_g4_trusts_prior_live_metrics`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
