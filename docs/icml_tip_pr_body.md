## Summary
- Tick 363: live G4 paper-pack **H2 field + PRIMARY gap** — `write_live_bvd_figures` titles Fig 2 from majority auto-resolved DNA field (not hard-coded `memory`); Live Table 1 summary emits `primary_final_pass` / `mean_final_gap` (Tick 360); H2 rows include `field=`; Winner attributes gens@25%/cost@25% as well as @30%. Tick 362 aligned offline Fig 2; Tick 361 live `resolve_h2_bias_field`. Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345 title finding; Tick 346 body confirmation; Tick 347 independent ``tip_pr_body_stale``; Tick 348–349 pass ``description=`` from `open_git_pr_description` in `docs/icml_open_git_pr.json` or `docs/icml_tip_pr_body.md`; Tick 350: prefer verbatim args from `docs/icml_open_git_pr_call.json`; Tick 353–359: cron exports `ICML_CLOUD_BOOT_BRANCH` before tip recover; Tick 354 ignores env==tip + persists `docs/icml_cloud_boot_branch.txt`; Tick 355 unsets env==tip and does not clobber the boot file with tip; Tick 356 gitignores the boot file + excludes it from ephemeral discard so tip --apply cannot wipe it; Tick 357 rejects short/non-``cursor/*`` boot poison + ``icml_checkout_tip_pr_branch.sh`` persists boot before tip checkout; Tick 358 checkout also refreshes `docs/icml_open_git_pr_call.json` so ``cloud_boot_branch`` matches the just-persisted boot; Tick 359 gitignores call JSON + excludes it from ephemeral discard so tip --apply cannot ``git restore`` a stale committed boot name). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_run_g4_multiseed.py::test_refresh_paper_artifacts_live_table`
- [x] `pytest tests/test_run_g4_multiseed.py::test_write_live_fig2_uses_majority_h2_field_not_memory_default`
- [x] `pytest tests/test_run_g4_multiseed.py::test_score_live_h2_auto_resolves_tool_strategy`
- [x] `pytest SIA/tests/test_epistemic_results.py::test_compare_b_vs_d_emits_mean_final_gap`
- [x] `pytest tests/test_run_g4_multiseed.py::test_primary_criteria_pass_and_h5_count`
- [x] `pytest tests/test_icml_env_checks.py::test_suggested_open_git_pr_title_secrets_first_when_stale`
- [x] `pytest tests/test_icml_env_checks.py::test_tip_pr_body_stale_independent_of_title`
- [x] `pytest tests/test_icml_env_checks.py::test_open_git_pr_pass_description_when_body_stale`
- [x] `pytest tests/test_icml_env_checks.py::test_open_git_pr_description_inline_in_json`
- [x] `pytest tests/test_icml_env_checks.py::test_open_git_pr_call_json_atomic_mcp_args`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
