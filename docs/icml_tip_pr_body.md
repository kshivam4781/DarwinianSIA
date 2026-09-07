## Summary
- Tick 373: **G3 resume re-score for G4 gate** — after Tick 372, a resume-skipped G3 still trusted `gate3_report.json`, often still `mode=preflight` with `comparison=null` (mid-stack crash / sidecar never written). That either stalls G4 despite a PRIMARY-shaped local pilot or (if comparison were filled from offline) risks a false ~$14 G4 burn. `load_g3_metrics_for_g4` now re-scores from local B/D run dirs when present; ledger-only fallback accepts the sidecar **only** when `mode=="live"` + `executed` + non-null comparison. Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_run_icml_live_pipeline.py::test_g3_resume_rescores_local_when_sidecar_preflight`
- [x] `pytest tests/test_run_icml_live_pipeline.py::test_g3_resume_refuses_preflight_sidecar_without_local`
- [x] `pytest tests/test_run_icml_live_pipeline.py::test_g3_resume_trusts_live_executed_sidecar_ledger_only`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
