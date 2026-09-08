## Summary
- Tick 380: **direct gate ledger-stage skip** — Tick 379 stamps `stages_complete` after successful direct G2/G3/G4 `--live`, but only the pipeline consulted `ledger_stage_complete` (Tick 285). Direct runners still treated missing local `runs/` as free IDs and would re-launch a ledger-complete stage on the next cross-VM cron (double-burn despite the stamp). New helper `direct_gate_ledger_skip` + wired skip-before-sia on direct G2/G3/G4 `--live`. Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_icml_env_checks.py::test_direct_gate_ledger_skip_true_when_stage_complete`
- [x] `pytest tests/test_icml_env_checks.py::test_direct_gate_ledger_skip_false_on_id_mismatch`
- [x] `pytest tests/test_run_g2_smoke.py::test_g2_live_skips_when_ledger_stage_complete`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
