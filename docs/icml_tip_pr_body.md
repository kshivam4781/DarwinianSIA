## Summary
- Tick 473: HTML SVG `<desc>` STATUS peel (`<svg…><title>Badge</title><desc>STATUS: READY</desc>…`); live G2→G4 **PRIMARY** still blocked on NEBIUS + (HF_TOKEN or `gpqa_diamond.csv`). Offline PRIMARY/H5 green at `1930–1934` / `1940–1944` (D final **5/5**, gens30/cost30 **4/5**, H5 **5/5**, H2 preferred **5/5**; floor gen≥3 + tail=2). STATUS remains IN_PROGRESS (not READY).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Tip recover / chicken-egg + prior_live stack (see `docs/ICML_PROGRESS.md`); tip PR anti-churn on this PR (`cursor/icml-epistemic-results-f49c`). Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`). See `docs/ICML_PROGRESS.md` for Tick 473 detail.

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_icml_env_checks.py::test_icml_ready_status_header_accepts_html_svg_desc_status`
- [x] `pytest tests/test_icml_env_checks.py::test_icml_ready_status_header_accepts_html_svg_aria_title_attr_status`
- [x] `pytest tests/test_run_g4_multiseed.py::test_demote_and_update_icml_ready_header_only_status`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
