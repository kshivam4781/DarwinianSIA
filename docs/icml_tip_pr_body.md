## Summary
- Tick 416: live G2→G4 **PRIMARY** still blocked on NEBIUS + (HF_TOKEN or `gpqa_diamond.csv`). Offline PRIMARY/H5 green at `1930–1934` / `1940–1944` (D final **5/5**, gens30/cost30 **4/5**, H5 **5/5**, H2 preferred **5/5**; floor gen≥3 + tail=2). STATUS remains IN_PROGRESS (not READY).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Tick 416: direct G4 ledger-skip exit 4 includes Tick 413–415 refuse checks (`h5_planned` / `primary_recomputed` / `h2_planned`) + clear `comparison` on refuse — closes false-green exit 0 after thin H2/H5/false PRIMARY refuse.
- Tip recover / chicken-egg + prior_live stack (see `docs/ICML_PROGRESS.md`); tip PR anti-churn on this PR (`cursor/icml-epistemic-results-f49c`). Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`). See `docs/ICML_PROGRESS.md` for Tick 416 detail.

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_run_g4_multiseed.py::test_g4_live_ledger_skip_exits_4_on_thin_h2_refuse`
- [x] `pytest tests/test_run_g4_multiseed.py::test_refresh_paper_pack_refuses_thin_h2_sidecar` (+ H5/PRIMARY refuse)
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
