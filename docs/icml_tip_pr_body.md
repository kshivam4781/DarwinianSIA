## Summary
- Tick 371: **G2 nonzero-fitness post-run gate** — after Tick 370 PRIMARY-only G3→G4, G2 could still PASS on CABS artifacts alone with **0% / missing** fitness (silent parse/eval failure) and the live pipeline would auto-burn ~$19 on G3+G4. `validate_g2_artifacts` now requires best fitness > `SIA_G2_MIN_BEST_FITNESS` (default 0). Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); H2 preferred **4/5**; STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_run_g2_smoke.py::test_validate_g2_artifacts_nonzero_fitness_gate`
- [x] `pytest tests/test_run_g2_smoke.py::test_validate_g2_artifacts_reads_belief_store`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
