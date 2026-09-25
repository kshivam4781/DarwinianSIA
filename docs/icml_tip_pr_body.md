## Summary
- Tick 419: fix discard/tip-apply **prior_live evidence race** — fresh stash capture no longer dead-ends tip recover when persist writes `docs/icml_prior_live_evidence.json`; Tick 390 pre-existing dirty evidence still blocks. Live G2→G4 **PRIMARY** still blocked on NEBIUS + (HF_TOKEN or `gpqa_diamond.csv`). Offline PRIMARY/H5 green at `1930–1934` / `1940–1944` (D final **5/5**, gens30/cost30 **4/5**, H5 **5/5**, H2 preferred **5/5**; floor gen≥3 + tail=2). STATUS remains IN_PROGRESS (not READY).
- **PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`) so cron can run live G2→G3→G4.
- Tip recover / chicken-egg + prior_live stack (see `docs/ICML_PROGRESS.md`); tip PR anti-churn on this PR (`cursor/icml-epistemic-results-f49c`). Tip PR GitHub **title and body** stay frozen when using `open_git_pr` MCP (does **not** rewrite either on existing PRs — Tick 345–350; prefer verbatim args from `docs/icml_open_git_pr_call.json`). Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … --body-file docs/icml_tip_pr_body.md`). See `docs/ICML_PROGRESS.md` for Tick 419 detail.

## Human unblock
1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)
2. Optional: copy-paste `tip_pr_title_edit_commands` from `docs/icml_open_git_pr.json` to refresh this PR's title+body
3. Tip PR #337 is MERGEABLE/CLEAN — undraft+merge: `gh pr ready 337 --repo kshivam4781/DarwinianSIA && gh pr merge 337 --repo kshivam4781/DarwinianSIA --merge` (and/or bootstrap PR #338)

## Test plan
- [x] `pytest tests/test_icml_env_checks.py::test_discard_ephemeral_ok_when_persist_writes_evidence`
- [x] `pytest tests/test_icml_env_checks.py::test_recover_tip_apply_wires_prior_live_stash`
- [x] `pytest tests/test_icml_env_checks.py` → 103 passed
- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass
