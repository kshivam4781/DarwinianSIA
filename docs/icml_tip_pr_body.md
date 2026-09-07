## Summary
- Tick 365: **offline/gate4 preferred-share surfacing** — after Tick 364 made `h2_skew_pass` require preferred-allele share, offline `D_h2_share` / Fig 2 / gate4 H2 report still showed pool `in_bias_share` (often 1.0). Now brief rows emit `preferred_share` (+ `D_h2_preferred` / `D_h2_in_bias_share`); Fig 2 titles annotate prefer=/share=; live Fig 2 majority preferred allele; gate4 H2 section mirrors paper-pack fields. Regen `1890–1904` keeps PRIMARY unchanged with honest preferred shares (e.g. seed 22 ≈0.29 vs prior pool 1.0). Builds on Tick 361–364 field/paper-pack/preferred-pass alignment. Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345 title finding; Tick 346 body confirmation; Tick 347 independent ``tip_pr_body_stale``; Tick 348–349 pass ``description=`` from `open_git_pr_description` in `docs/icml_open_git_pr.json` or `docs/icml_tip_pr_body.md`; Tick 350: prefer verbatim args from `docs/icml_open_git_pr_call.json`; Tick 353–359: cron exports `ICML_CLOUD_BOOT_BRANCH` before tip recover; Tick 354 ignores env==tip + persists `docs/icml_cloud_boot_branch.txt`; Tick 355 unsets env==tip and does not clobber the boot file with tip; Tick 356 gitignores the boot file + excludes it from ephemeral discard so tip --apply cannot wipe it; Tick 357 rejects short/non-``cursor/*`` boot poison + ``icml_checkout_tip_pr_branch.sh`` persists boot before tip checkout; Tick 358 checkout also refreshes `docs/icml_open_git_pr_call.json` so ``cloud_boot_branch`` matches the just-persisted boot; Tick 359 gitignores call JSON + excludes it from ephemeral discard so tip --apply cannot ``git restore`` a stale committed boot name). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_offline_case_study_steered.py::test_offline_fig2_uses_primary_h2_field_not_memory`
- [x] `pytest tests/test_offline_case_study_steered.py::test_offline_compare_brief_uses_preferred_share_not_in_bias`
- [x] `pytest tests/test_run_g4_multiseed.py::test_write_gate4_report_h2_surfaces_preferred_share`
- [x] `pytest tests/test_run_g4_multiseed.py::test_write_live_fig2_annotates_preferred_allele`
- [x] `pytest tests/test_run_g4_multiseed.py::test_h2_h5_pass_helpers`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
