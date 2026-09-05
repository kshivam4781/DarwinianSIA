# Agent guide — SIA-CABS / DarwinianSIA

## Start here (required)

Before planning, coding, or running commands, read:

**[`docs/HACKATHON_MASTER_PLAN.md`](docs/HACKATHON_MASTER_PLAN.md)**

That document is the single source of truth for CABS architecture, APIs, hardware, blockers, phases, budgets, and run commands. **Section 21** (on the ICML tip tree) is the ICML Thesis 1 epistemic-evolution protocol.

## ICML persistent agent — chicken-egg recover FIRST (Tick 341)

Automation cron often boots a **fresh branch from `main`**. As of Tick 341, `main` still lacks `docs/ICML_*` and `scripts/icml_cron_entry.sh` until the full tip PR merges.

**Do this before any other ICML work** (Tick 272 lineage pick; also scan `cursor/bc-*`):

```bash
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

That entry recovers tip, auto-checkouts the MERGEABLE tip PR commit branch (anti-churn), and runs live G2→G4 when secrets exist (else preflight).

**Dual human unblock** (full tip still unmerged):

1. Merge tip PR **#337** → `main`:  
   `gh pr ready 337 --repo kshivam4781/DarwinianSIA && gh pr merge 337 --repo kshivam4781/DarwinianSIA --merge`
2. Add **`NEBIUS_API_KEY`** + (`**HF_TOKEN**` or local `gpqa_diamond.csv`) on the automation / env.

Agents: do **not** open a new tip PR. After recover, push/`open_git_pr` with `branch=<tip_pr_commit_branch>` from `docs/icml_open_git_pr.json` (**never omit** `branch=`). See tip docs: `docs/ICML_HUMAN_UNBLOCK.md`.

If `docs/ICML_READY.md` says **STATUS: READY** → stop.

## Two-repo layout (this monorepo)

| Area | Path | Build |
|------|------|-------|
| **CABS** | `cabs/`, `sia_cabs/` | Beliefs, contradictions, Tavily, committee |
| **Darwinian** | `SIA/` | Population evolution, DNA, `civilization.json` |

## Quick rules

1. **Phase order:** hackathon 0→1→2→3; ICML G0→G5 per Section 21.5 (on tip).
2. **Money:** No GPQA/LawBench without keys + budget. Never full LawBench without approval. ~$20 ICML ceiling.
3. **Hardware:** Local GPU unused. Inference via Nebius API.
4. **Run IDs:** Integers only; never overwrite runs.
5. **Scope:** No `--focus weights`. Prefer `--no-web`. No parallel full GPQA.
6. **Status:** After work on tip: Section 12 + `docs/ICML_PROGRESS.md` + `docs/ICML_READY.md`.

## Project summary

- **What:** SIA-CABS — Contradiction-Aware Belief System + Darwinian merge
- **Track:** Track 3 (Novel Self-Improvement Methodology) / ICML Thesis 1 epistemic evolution
- **CLI:** `sia-cabs` (CABS), `sia` (baseline / `--darwinian`), `sia-cabs-tools`
- **Python:** 3.13 preferred (`.venv`)
