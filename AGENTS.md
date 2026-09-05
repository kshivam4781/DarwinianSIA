# Agent guide — SIA-CABS / DarwinianSIA

## Start here (required)

Before planning, coding, or running commands, read:

**[`docs/HACKATHON_MASTER_PLAN.md`](docs/HACKATHON_MASTER_PLAN.md)**

That document is the single source of truth for CABS architecture, APIs, hardware, blockers, phases, budgets, and run commands. **Section 21** is the ICML Thesis 1 epistemic-evolution protocol (persistent agent). Sections 18–20 cover Darwinian merge contracts.

## ICML persistent agent (cron / cloud)

Automation ticks often boot a **fresh branch from `main`** without `docs/ICML_*` or live runners.
**Tick 327:** `main` still has hackathon-era AGENTS (no ICML tip files) until the tip PR is merged — recover tip every boot; ask human to merge tip → `main` + add secrets (`docs/ICML_HUMAN_UNBLOCK.md`).
**Tick 328:** machine-readable `docs/icml_secrets_status.json` / tip status / pipeline Next also surface merge tip→main via `main_has_icml_tip` (does not gate paid live).
**Tick 330:** `human_next` includes the concrete tip PR URL (`tip_pr_url`) so operators do not guess among 300+ draft tip PRs.
**Tick 331:** tip pickers also scan `cursor/bc-*` cloud cron branches (not only `icml-epistemic-results-*`).
**Tick 332:** `ICML_HUMAN_UNBLOCK.md` chicken-egg recipe (+ script-header recipes) also fetch/scan `cursor/bc-*` (Tick 331 fixed pickers/AGENTS only).
**Tick 333:** `resolve_icml_tip_pr` same-SHA sibling tip PR fallback (tip head mid-tick / greenfield branch without its own PR yet still surfaces concrete `tip_pr_url`).
**Tick 334:** same-SHA tip PR resolve also falls back to **HEAD / local branch SHA** when `tip_ref` is an unpushed `refs/remotes/origin/<greenfield>` (common after tip recover before `git push`).
**Tick 335:** tip PR resolve / `human_next` / tip+secrets JSON also surface GitHub **mergeability** (`MERGEABLE`/`CLEAN` vs `CONFLICTING`) so operators know when undraft+merge is safe among 300+ draft tip PRs.
**Tick 336:** `human_next` / tip+secrets JSON also expose **`tip_pr_merge_commands`** (copy-paste `gh pr ready` + `gh pr merge`) and a **churn warning** — merge before next cron (~2h) or a new tip PR supersedes; ignore older drafts.
**Tick 337:** tip PR **anti-churn** — when MERGEABLE, use `tip_pr_commit_branch` (`bash scripts/icml_checkout_tip_pr_branch.sh`) and **do not open a new tip PR**; push/`open_git_pr` on that branch so the existing tip PR updates.
**Tick 338:** `icml_cron_entry.sh` **auto-checkouts** `tip_pr_commit_branch` after tip/secrets status write (Tick 337 left this manual; without it, greenfield boot branch names still opened a new tip PR every cron).
**Tick 339:** `icml_boot_recover.sh --apply` + `icml_recover_tip.py --apply` also auto-checkout `tip_pr_commit_branch` (Tick 338 only covered cron_entry; chicken-egg recover alone still left greenfield branch names).
**Tick 340:** `open_git_pr` MCP defaults to the greenfield *boot* branch when `branch=` is omitted — **never omit**; pass `branch=<tip_pr_commit_branch>` (see `docs/icml_open_git_pr.json`). Checkout alone is not enough.
**Tick 341:** `main` still injects hackathon-era `AGENTS.md` into cron cloud instructions. A **minimal main-only bootstrap PR** (`cursor/icml-main-agents-bootstrap`) adds this chicken-egg recover block to `main` without requiring review of the full tip PR first — merge it **or** tip #337. Not a new tip PR (anti-churn tip remains #337 / `f49c`).
**Tick 342:** secrets/tip JSON + cron `human_next` surface that bootstrap PR (`agents_bootstrap_pr_url` / `agents_bootstrap_merge_commands`) when open — easier 1-file merge before full tip.
**Tick 343:** **PRIMARY-first `human_next`** — when `fetch_diamond_ok` is false, secrets (+ HF/CSV) lead; tip/bootstrap merge follow (tip merge does not gate live). When secrets already OK, Tick 342 bootstrap-first order unchanged.
**Live secrets (Tick 289+):** `NEBIUS_API_KEY` + (`HF_TOKEN` **or** local `gpqa_diamond.csv`). `ANTHROPIC_API_KEY` is **optional** under default Nebius pydantic-ai meta. See `docs/ICML_HUMAN_UNBLOCK.md`. Load local `.env` with `source scripts/load_env.sh` (Linux/cloud) or `. .\scripts\load_env.ps1` (Windows).

1. If `docs/ICML_READY.md` says **STATUS: READY** → stop (already complete).
2. Run the **single cron entry** (Tick 271/272) — tip recover + secrets gate + live or preflight:

```bash
# Preferred once tip tree exists:
bash scripts/icml_cron_entry.sh

# Chicken-egg from main (entry script absent) — Tick 272 lineage pick
# (never committerdate-only: greenfield main branches can be newer than tip).
# Tick 331: also scan cursor/bc-* cloud cron boots.
git fetch origin \
  '+refs/heads/cursor/icml-epistemic-results-*:refs/remotes/origin/cursor/icml-epistemic-results-*' \
  '+refs/heads/cursor/bc-*:refs/remotes/origin/cursor/bc-*'
TIP_REF=""
BEST_TICK=-1
TMP=$(mktemp -d)
while IFS= read -r ref; do
  git cat-file -e "${ref}:scripts/icml_cron_entry.sh" 2>/dev/null || continue
  git show "${ref}:docs/ICML_PROGRESS.md" >"$TMP/p" 2>/dev/null || continue
  tick=$(grep -oE 'Tick[[:space:]]+[0-9]+' "$TMP/p" | head -1 | grep -oE '[0-9]+' || true)
  [[ -z "$tick" ]] && continue
  if [[ "$tick" -gt "$BEST_TICK" ]]; then BEST_TICK=$tick; TIP_REF=$ref; fi
done < <(git for-each-ref --format='%(refname)' \
  'refs/remotes/origin/cursor/icml-epistemic-results-*' \
  'refs/remotes/origin/cursor/bc-*')
rm -rf "$TMP"
git show "${TIP_REF}:scripts/icml_cron_entry.sh" | bash -s --
```

`icml_cron_entry.sh` recovers tip (lineage-aware; `scripts/icml_pick_remote_tip.sh`), writes `docs/icml_tip_status.json` + `docs/icml_secrets_status.json`, then either runs `run_icml_live_pipeline.py --live --fetch-diamond` (when secrets present) or preflight-only.

3. Follow Section 21 + `docs/ICML_PROGRESS.md` / `docs/ICML_HUMAN_UNBLOCK.md` for diagnosis if entry exits without READY.
4. Never set READY from offline / preflight alone. Do not re-trigger Portal Save every tick.

## Two-repo layout (this monorepo)

| Area | Path | Build |
|------|------|-------|
| **CABS** | `cabs/`, `sia_cabs/` | Beliefs, contradictions, Tavily, committee |
| **Darwinian** | `SIA/` | Population evolution, DNA, `civilization.json` |

## Quick rules

1. **Phase order is mandatory:** 0 → 1 → 2 → 3 (hackathon). ICML: G0 → G5 per Section 21.5.
2. **Money:** Do not run GPQA/LawBench without checking API keys and budget (Section 8 / 21.6). Never run full LawBench without user approval. ~$20 ICML ceiling unless docs raise it.
3. **Hardware:** Local GPU unused. Inference via Nebius API; orchestration on CPU.
4. **Run IDs:** Must be **integers**; never overwrite existing runs.
5. **Scope:** No `--focus weights` / RL mode. Prefer `--no-web` for long runs. No parallel full GPQA jobs.
6. **Status:** After work, update Section 12 + `docs/ICML_PROGRESS.md` + `docs/ICML_READY.md`.

## Project summary

- **What:** SIA-CABS — Contradiction-Aware Belief System + Darwinian epistemic steering (Condition D)
- **Winning thesis:** Belief → Contradiction → Research question → Biased mutation / scoped feedback → Better sample efficiency than fitness-only Darwinian
- **CLI:** `sia` / `sia-cabs` / `sia-cabs-tools`; live: `scripts/run_icml_live_pipeline.py`
