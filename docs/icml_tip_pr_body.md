## Summary
- Tick 498: Gate 2 `## Next` is **NEBIUS-first** when non-synthetic diamond is already present (drops hard-coded HF-accept step). Live G2→G4 **PRIMARY** still blocked on **NEBIUS_API_KEY** (HF optional via Tick 497 public mirror). Offline PRIMARY/H5 green at `1930–1934` / `1940–1944` (D final **5/5**, gens30/cost30 **4/5**, H5 **5/5**, H2 preferred **5/5**; floor gen≥3 + tail=2). STATUS remains IN_PROGRESS (not READY).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` (HF optional — Tick 497 public diamond mirror / local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Tip recover / chicken-egg + prior_live stack (see `docs/ICML_PROGRESS.md`); tip PR anti-churn on this PR (`cursor/icml-epistemic-results-f49c`). Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`). See `docs/ICML_PROGRESS.md` for Tick 498 detail.

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv` / rely on Tick 497 public mirror)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_run_g2_smoke.py::test_gate2_next_nebius_first_when_diamond_ready`
- [x] `pytest tests/test_run_g2_smoke.py::test_write_gate2_report`
- [x] Cold-boot G3 `--fetch-diamond` → `gpqa_not_synthetic=yes`; blockers = NEBIUS only
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
