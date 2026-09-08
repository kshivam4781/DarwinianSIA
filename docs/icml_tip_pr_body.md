## Summary
- Tick 381: **direct G4 ledger-skip paper-pack refresh** — Tick 380 skips paid direct G4 `--live` when the ledger marks G4 complete, but early-returned without `apply_paper_pack` / sidecar trust (pipeline Tick 374 already refreshed on resume). Cross-VM or same-VM ledger skip could leave `ICML_READY` stuck IN_PROGRESS after paid G4 evidence existed. New helper `refresh_paper_pack_on_ledger_skip` re-scores local B/D or trusts a live-executed gate4 sidecar. Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_run_g4_multiseed.py::test_refresh_paper_pack_on_ledger_skip_local_dirs`
- [x] `pytest tests/test_run_g4_multiseed.py::test_refresh_paper_pack_on_ledger_skip_trusts_sidecar`
- [x] `pytest tests/test_run_g4_multiseed.py::test_g4_live_ledger_skip_refreshes_paper_pack`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
