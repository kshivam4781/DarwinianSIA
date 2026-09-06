## Summary
- Tick 364: **H2 preferred-allele share** — live MECHANISM previously treated contradiction-pool membership (`in_bias_share`) as skew, so a population dominated by the *loser* allele still scored `in_bias_share=1.0` and would false-pass. `compute_h2` now emits `preferred_value` / `preferred_share` (first bias allele); `h2_skew_pass` requires preferred share ≥0.5; Live Table 2 H2 rows surface preferred share; default `compute_h2(field=None)` auto-resolves. Builds on Tick 361–363 field/paper-pack alignment.
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Offline PRIMARY/H5 unchanged (`1890–1904`); STATUS remains IN_PROGRESS (not READY).

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Optional: undraft+merge tip PR #337 and/or bootstrap PR #338

## Test plan
- [x] `pytest tests/test_run_g4_multiseed.py::test_h2_h5_pass_helpers`
- [x] `pytest tests/test_run_g4_multiseed.py::test_score_live_h2_auto_resolves_tool_strategy`
- [x] `pytest tests/test_run_g4_multiseed.py::test_refresh_paper_artifacts_live_table`
- [x] `pytest SIA/tests/test_epistemic_results.py::test_resolve_h2_bias_field_prefers_tool_strategy`
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
