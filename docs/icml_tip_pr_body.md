## Summary
- Tick 374: **G4 resume paper-pack refresh** — after Tick 373, a resume-skipped G4 still returned without rebuilding the paper pack. When B/D `results.json` exist but `gate4_report.json` stayed `mode=preflight` (crash after pairs / pack never ran), the next cron would skip G4 forever and leave `ICML_READY` stuck IN_PROGRESS despite PRIMARY-shaped live evidence. `refresh_g4_paper_pack_on_resume` now re-scores from local B/D via `apply_paper_pack` when present; ledger-only fallback accepts the sidecar **only** when `mode in {live,refresh-paper}` + `executed` + `paper_refreshed` + non-null comparison. Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_run_icml_live_pipeline.py::test_g4_resume_refreshes_paper_pack_when_sidecar_preflight`
- [x] `pytest tests/test_run_icml_live_pipeline.py::test_g4_resume_refuses_preflight_sidecar_without_local`
- [x] `pytest tests/test_run_icml_live_pipeline.py::test_g4_resume_trusts_live_executed_sidecar_ledger_only`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
