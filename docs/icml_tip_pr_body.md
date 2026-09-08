## Summary
- Tick 382: **direct G3 ledger-skip pilot-metrics refresh** — Tick 380 skips paid direct G3 `--live` when the ledger marks G3 complete, but wrote `executed=False` with null comparison and could clobber a live-executed gate3 sidecar (pipeline Tick 373 needs that sidecar for G4 advance when local `runs/` are absent). New helper `refresh_g3_metrics_on_ledger_skip` re-scores local B/D or trusts a live-executed gate3 sidecar. Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_run_g3_pilot.py::test_refresh_g3_metrics_on_ledger_skip_local_dirs`
- [x] `pytest tests/test_run_g3_pilot.py::test_refresh_g3_metrics_on_ledger_skip_trusts_sidecar`
- [x] `pytest tests/test_run_g3_pilot.py::test_g3_live_ledger_skip_refreshes_metrics`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
