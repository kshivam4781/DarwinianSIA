## Summary
- Tick 386: **gate4 prior_live_metrics preserve** — after Tick 385, cron `--preflight-only` still wiped live gate4 `comparison` / `paper_refreshed` (mode=preflight, executed=False), so `refresh_g4_paper_pack_on_resume` / direct G4 ledger-skip could not trust paid G4 paper-pack evidence cross-VM. New `prior_live_metrics` preserved in `write_gate4_report`; `_live_paper_from_gate4_sidecar` + resume / `refresh_paper_pack_on_ledger_skip` trust it (Tick 385 gate3 parity). Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_run_g4_multiseed.py::test_write_gate4_preflight_preserves_prior_live_metrics`
- [x] `pytest tests/test_run_g4_multiseed.py::test_refresh_paper_pack_on_ledger_skip_trusts_prior_live_metrics`
- [x] `pytest tests/test_run_icml_live_pipeline.py::test_refresh_g4_paper_pack_on_resume_trusts_prior_live_metrics`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
