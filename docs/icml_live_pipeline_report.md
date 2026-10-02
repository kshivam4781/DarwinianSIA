# ICML live pipeline report — G2 → G3 → G4

**Timestamp:** 2026-10-02T04:09:21Z
**Mode:** `live`
**Ready for live stack:** no
**ICML_READY:** IN_PROGRESS

## Budget projection

| Item | USD |
|------|-----|
| spent (env) | 0.00 |
| G2 estimate | 2.00 |
| G3 estimate | 3.00 |
| G4 estimate | 14.00 |
| stack estimate | 19.00 |
| projected total | 19.00 |
| ceiling | 20.00 |
| within ceiling | yes |

## Stages

| Stage | Attempted | OK | Exit | Detail |
|-------|-----------|----|------|--------|

## G3→G4 gate

G3 promising: n/a (G3 not scored this run)

## Blockers

- secrets: NEBIUS_API_KEY missing

## Notes

- Tick 278: auto-wired --diamond-csv from /tmp/gpqa_diamond.csv
- Add NEBIUS_API_KEY per docs/ICML_HUMAN_UNBLOCK.md (diamond already ready; HF optional — Tick 497/501/503).

## Next

1. Add `NEBIUS_API_KEY` (ANTHROPIC_API_KEY optional — Tick 289 Nebius pydantic-ai meta) to automation https://cursor.com/automations/bf73dff3-8f7a-11f1-a7d1-d6b4613131ce (or linked env dashboard). Diamond already ready (CSV / public mirror / non-synthetic on disk) — HF optional (Tick 497/501). See `docs/ICML_HUMAN_UNBLOCK.md`.
2. Next cron (or now): `bash scripts/icml_cron_entry.sh` — auto-recovers tip and runs live when `fetch_diamond_ok` (else preflight only).
3. Portal Save of `docs/icml_portal_save_target.json` is **optional** (Tick 265–267: uv + runtime deps bootstrap in preflight).
4. Do **not** set STATUS: READY from offline / preflight alone.
5. Optional interim (easier than full tip): merge main-only AGENTS chicken-egg bootstrap PR #338 https://github.com/kshivam4781/DarwinianSIA/pull/338 — GitHub MERGEABLE/CLEAN: undraft & merge now (no conflicts) (branch `cursor/icml-main-agents-bootstrap`; Tick 341–342; 1-file — **not** a tip PR; does not replace merging the tip). Copy-paste: `gh pr ready 338 --repo kshivam4781/DarwinianSIA && gh pr merge 338 --repo kshivam4781/DarwinianSIA --merge`. Agents: tip anti-churn tip PR is unchanged — still commit/`open_git_pr` on `tip_pr_commit_branch` only.
6. Merge the latest ICML tip PR into `main` so cron inherits `docs/ICML_*` + `scripts/icml_cron_entry.sh` (Tick 327–340 dual unblock; `main` still has hackathon-era AGENTS without tip files). See `docs/ICML_HUMAN_UNBLOCK.md` Dual human unblock. Concrete tip PR: #337 https://github.com/kshivam4781/DarwinianSIA/pull/337 — GitHub MERGEABLE/CLEAN: undraft & merge now (no conflicts). Copy-paste: `gh pr ready 337 --repo kshivam4781/DarwinianSIA && gh pr merge 337 --repo kshivam4781/DarwinianSIA --merge`. Agents/cron: do NOT open a new tip PR — checkout `cursor/icml-epistemic-results-f49c` (tip_pr_commit_branch; Tick 338–339 cron + tip recover --apply auto-checkout via icml_cron_entry / icml_boot_recover / icml_recover_tip) and push here so PR #337 updates (bash scripts/icml_checkout_tip_pr_branch.sh; open_git_pr branch=`cursor/icml-epistemic-results-f49c` — Tick 340: NEVER omit branch=; open_git_pr defaults to the greenfield boot branch and would open a new tip PR; see docs/icml_open_git_pr.json; Tick 344: also pass title=`suggested_open_git_pr_title` from that JSON when tip_pr_title_stale — stale titles look superseded among 300+ drafts; secrets-first title when fetch_diamond_ok is false; Tick 348–349: also pass description= from `open_git_pr_description` in `docs/icml_open_git_pr.json` (or `docs/icml_tip_pr_body.md`) when tip_pr_body_stale; Tick 350: prefer verbatim `docs/icml_open_git_pr_call.json` (branch/title/description); Tick 352: call JSON records ``cloud_boot_branch`` / ``omit_branch_opens_pr_on``; Tick 352: this run's cloud_boot_branch=`cursor/bc-2735462b-b736-489f-919f-71cff202b562-433f` — omitting branch= opens a NEW tip PR on `cursor/bc-2735462b-b736-489f-919f-71cff202b562-433f` (not `cursor/icml-epistemic-results-f49c`); Cloud Agent 'correct working branch' does NOT override tip anti-churn. Tick 345–347: if GitHub title/body stays stale, copy-paste `tip_pr_title_edit_commands` (`gh pr edit --title [--body-file docs/icml_tip_pr_body.md]`) — open_git_pr MCP does not rewrite title or body). Merge before next cron (~2h). Older tip PRs are superseded; merge only #337.
