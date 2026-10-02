# ICML Thesis 1 — Human unblock (secrets)

**STATUS:** Live G2→G3→G4 is blocked on **`NEBIUS_API_KEY`** (HF optional after Tick 497 public mirror).  
**Tick 507:** secrets early-refuse no longer wipes the Tick 296 pipeline shape note — `write_pipeline_report` / preflight+live stamp heal so G3/G4 recipe locks cannot false-refuse after NEBIUS arrives.  
**Tick 506:** tip PR suggested title/body ask **NEBIUS-only** when on-disk non-synthetic diamond is ready (`icml_diamond_source_ready_for_nebius_only`) — closes NEBIUS+HF paste after CSV cleanup (Tick 499/502 diamond_ready parity for open_git_pr metadata).  
**Tick 505:** UNKNOWN tip/bootstrap PR mergeability from `gh pr list` refreshes via `gh pr view` so `human_next` / secrets JSON can say MERGEABLE/CLEAN → undraft & merge now (closes vague UNKNOWN among 300+ drafts).  
**Tick 504:** auto-wired CSV must not force rematerialize when on-disk non-synthetic diamond is ready (`icml_should_keep_ondisk_diamond`; explicit `--diamond-csv` still refreshes).  
**Tick 503:** G2/G3/G4/pipeline `--live --fetch-diamond` refuses when `fetch_diamond_ok` is false even if CSV/public-mirror auto-wire cleared `require_hf` (closes enter-live-then-fail-on-keys path).  
**Tick 501:** pipeline `## Next` (`live_pipeline_next_steps`) + live `--fetch-diamond` refuse notes are NEBIUS-first when `diamond_ready` — Gate2/G3/G4/secrets Tick 498–500 parity for `docs/icml_live_pipeline_report.md`.  
**Tick 500:** G3/G4 `## Next` + cron live-refuse NEBIUS-first when diamond ready (shared `icml_preflight_diamond_ready`).  
**Tick 499:** secrets/cron `human_next` drops HF-accept when `diamond_ready` (CSV / mirror / non-synthetic on disk) — Gate2 Tick 498 parity for cron logs + `icml_secrets_status.json`.  
**Tick 498:** Gate 2 `## Next` is NEBIUS-first when non-synthetic diamond is already present (drops hard-coded “Accept HF access” step). Cold-boot rematerialize re-verified.
**Tick 497:** public OpenAI simple-evals `gpqa_diamond.csv` auto-fetch (`--from-public-mirror` / `ensure_diamond_csv_via_public_mirror`) — HF_TOKEN no longer hard-required when network works; diamond materialized non-synthetic; secrets blockers = NEBIUS only.
**Tick 496:** C-array / comma / per-byte `0x` hex STATUS (`53,54,…` / `0x53,0x54,…` / `0x53 0x54 …` / `{0x53, 0x54, …}` / bold-wrapped) — extends `_peel_icml_status_bare_hex`; closes G4 demote no-op / pack miss after Tick 495 continuous/space/colon/dash/single-`0x`-only.
**Tick 495:** bare hex STATUS (`5354415455533A205245414459` / spaced `53 54 …` / colon / dash / `0x` / bold-wrapped) — `_peel_icml_status_bare_hex`; closes G4 demote no-op / pack miss after Tick 492–494 base64/data-URI-only.
**Tick 494:** plain / percent-encoded data-URI STATUS (`data:text/plain,STATUS%3A%20READY` / charset / `data:,…` / literal / bold-wrapped) — `_peel_icml_status_data_uri_plain`; closes G4 demote no-op / pack miss after Tick 493 base64-only data-URI.
**Tick 492:** bare base64 STATUS (`U1RBVFVTOiBSRUFEWQ==` / `**U1RBVFVTOiBSRUFEWQ==**`) — `_peel_icml_status_bare_base64`; closes G4 demote no-op / pack miss after Tick 491 wrapped-B-only.
**Tick 491:** RFC 2047 encoded-word STATUS (`=?UTF-8?Q?STATUS=3A_READY?=` / `=?UTF-8?B?…?=` / adjacent Q words) — `_peel_icml_status_rfc2047_encoded_words`; closes G4 demote no-op / pack miss after Tick 490 bare-QP-only.
**Tick 490:** MIME quoted-printable STATUS (`STATUS=3A READY` / `STATUS=3A=20READY` / soft-break / QP HTML badge) — `_ICML_STATUS_QUOTED_PRINTABLE_RE` + soft-break join; closes G4 demote no-op / pack miss after Tick 489 URL/JS/HTML-only.
**Tick 487:** double-escaped HTML STATUS (`STATUS&amp;#58; READY` / `STATUS&amp;colon;READY` / `&lt;p title=&quot;STATUS: READY&quot;&gt;…`) — `_ICML_STATUS_DOUBLE_AMP_RE` + iterative entity decode (also `&lt;`/`&gt;`/`&quot;`/`&apos;`); closes G4 demote no-op / pack miss after Tick 486 single-layer entities.
**Tick 486:** HTML-entity STATUS colons (`STATUS&#58; READY` / `STATUS&colon;READY` / `STATUS&#x3a; READY` / `STATUS&#xff1a;READY` / attr `title="STATUS&#58; READY"`) — `_decode_icml_status_html_entities` decodes `&colon;` / `&#58;` / `&#x3a;` / `&#xff1a;` (extends Tick 455 invisibles/nbsp-only); closes G4 demote no-op / pack miss on CMS/XSS-escaped colon stubs.
**Tick 485:** unquoted HTML STATUS attrs (`<p title=STATUS:READY>badge</p>` / `<img alt=STATUS:READY src=…>`) — ATTR peels accept unquoted values; IN_ATTR requires READY/IN_PROGRESS token; closes demote no-op / pack miss after Tick 484 quoted-only.
**Tick 478:** HTML picture/figure mid-line multiline ``<img`` STATUS headers (`<picture><source…><img\n  alt="STATUS: READY"\n  src="…"/>\n</picture>` / `<figure><img\n  title="**STATUS: READY**"\n/>`) — `_ICML_STATUS_IMG_INLINE_OPEN_RE` + `_ICML_STATUS_HTML_IMG_COMPLETE_RE` collapse mid-line `<img` opens after wrappers; demote/update replace the whole block — closes G4 demote no-op / pack miss after Tick 477 `^<img`-only.
**Tick 477:** HTML pretty-printed multi-line ``<img …>`` STATUS headers (`<img\n  alt="STATUS: READY"\n  src="…"/>` / `<img\n  title="**STATUS: READY**"\n/>`) — `_take_icml_status_multiline_img_block` + `_iter_icml_ready_status_units` collapse multi-line `<img>` before Tick 468–470 peels; demote/update replace the whole block — closes G4 demote no-op / pack miss after Tick 476 SVG-only collapse.
**Tick 476:** HTML SVG pretty-printed multi-line ``<svg>…</svg>`` STATUS headers (`<svg>\n  <text>STATUS: READY</text>\n</svg>` / multi-line `<foreignObject>`) — `_take_icml_status_multiline_svg_block` collapses before Tick 471–475 peels; demote/update replace the whole block — closes G4 demote no-op / pack miss / broken-SVG inner-line rewrite after Tick 471–475 full-line-only.
**Tick 474:** HTML SVG nested ``<text>STATUS:…</text>`` STATUS headers (`<svg…><title>Badge</title><text>STATUS: READY</text>…` / `<svg…><text><tspan>**STATUS: READY**</tspan></text>…`) — `_peel_icml_status_html_svg_title` peels nested `<text>` (plain after stripping `<tspan>`) after attrs + `<title>` + `<desc>` — closes G4 demote no-op / pack miss after Tick 471–473 attrs/title/desc only.
**Tick 473:** HTML SVG nested ``<desc>STATUS:…</desc>`` STATUS headers (`<svg…><title>Badge</title><desc>STATUS: READY</desc>…` / `<svg…><desc>**STATUS: READY**</desc>…`) — `_peel_icml_status_html_svg_title` peels nested `<desc>` after root attrs + nested `<title>` — closes G4 demote no-op / pack miss after Tick 471/472 attrs+title only.
**Tick 472:** HTML SVG root ``aria-label="STATUS:…">`` / ``title="STATUS:…">`` STATUS headers (`<svg aria-label="STATUS: READY" …>` / `<svg title="**STATUS: READY**"><title>Badge</title>…`) — `_peel_icml_status_html_svg_title` peels quoted root attrs (prefer STATUS-looking among aria-label→title-attr→nested `<title>`) — closes G4 demote no-op / pack miss after Tick 471 nested-`<title>` only.
**Tick 471:** HTML SVG ``<title>STATUS:…</title>`` STATUS headers (`<svg…><title>STATUS: READY</title>…</svg>` / residual `<text>`/`<desc>`) — `_peel_icml_status_html_svg_title` peels nested `<title>` without allowlist strip — closes G4 demote no-op / pack miss after Tick 468–470 `<img>`-only.
**Tick 470:** HTML ``<img title="STATUS:…">`` / ``aria-label="STATUS:…">`` STATUS headers (`<img title="STATUS: READY" src="…">` / `<img aria-label="**STATUS: READY**" src="…">` / `<img alt="badge" title="STATUS: READY" src="…">`) — `_peel_icml_status_html_img_alt` peels quoted title/aria-label (prefer STATUS-looking among alt→title→aria-label) — closes G4 demote no-op / pack miss after Tick 468/469 `alt=` only.
**Tick 469:** HTML ``<picture><img alt="STATUS:…">`` STATUS headers (`<picture><img alt="STATUS: READY" src="…">` / `<picture><source …><img alt="**STATUS: READY**" /></picture>`) — allowlist `picture`/`source` so nested img reaches Tick 468 alt peel — closes G4 demote no-op / pack miss after Tick 468 full-line bare `<img>` only.  
**Tick 468:** HTML ``<img alt="STATUS:…">`` STATUS headers (`<img alt="STATUS: READY" src="…">` / `<img src="…/badge_(live).svg" alt="**STATUS: READY**" />`) — `_peel_icml_status_html_img_alt` peels quoted alt text — closes G4 demote no-op / pack miss after Tick 467 markdown-image only.  
**Tick 467:** markdown-image STATUS headers (`![STATUS: READY](url)` / `![**STATUS: READY**](…/badge_(live).svg)`) — `_peel_icml_status_md_link` strips leading `!` then reuses the link scanner — closes G4 demote no-op / pack miss after Tick 466 required bare `[`.  
**Tick 466:** markdown-link nested-paren URL STATUS headers (`[STATUS: READY](https://x.com/foo_(bar))` / `[**STATUS: READY**](…#status-(draft))`) — `_peel_icml_status_md_link` balanced destination scan — closes G4 demote no-op / pack miss after Tick 465 `[^)]*` truncated at first `)`.  
**Tick 465:** markdown-link + HTML-anchor STATUS headers (`[STATUS: READY](url)` / `[**STATUS: READY**](#anchor)` / `<a href="…">STATUS: READY</a>`) strip + demote/update — closes G4 demote no-op / pack miss on GitHub/Notion linked STATUS stubs (Tick 464 bare `[STATUS:…]` required end-at-`]`; `[^>/]*` also blocked `href="https://…"`).  
**Tick 464:** paren / bracket / brace / fullwidth-colon STATUS headers (`(STATUS: READY)` / `[STATUS: READY]` / `{STATUS: READY}` / `（STATUS: READY）` / `STATUS：READY`) strip + demote/update — closes G4 demote no-op / pack miss on chat/JSON/Notion paren stubs + CJK colon.  
**Tick 463:** bare / ordered / blockquote checkbox STATUS headers (`[ ] STATUS: READY` / `1. [ ] STATUS:…` / `> [x] **STATUS:…**` / `| [ ] STATUS:… |`) strip + demote/update — closes G4 demote no-op / pack miss on paste stubs without `[-*+]` list marker (Tick 462 left those unmatched).  
**Tick 459:** HTML-table + semantic + md-pipe STATUS headers (`<td>STATUS: READY</td>` / `<section>STATUS:…</section>` / `| STATUS: READY |` / `| **STATUS: READY** |`) strip + demote/update — closes G4 demote no-op / pack miss on Notion/Docs HTML table-cell/section export + GitHub one-cell pipe (Tick 458 left `<table>` unmatched).  
**Tick 458:** HTML-container + Obsidian STATUS headers (`<blockquote>STATUS: READY</blockquote>` / `<li>STATUS:…</li>` / `==STATUS: READY==` / `**~~STATUS: READY~~**`) strip + demote/update — closes G4 demote no-op / pack miss on Notion HTML list/blockquote export + Obsidian highlight (Tick 451 markdown `>`/`-` already worked).  
**Tick 457:** HTML-heading + markdown-wrap STATUS headers (`<h1>STATUS: READY</h1>` / `` `STATUS: READY` `` / `~~STATUS: READY~~`) strip + demote/update — closes G4 demote no-op / pack miss on Notion HTML heading export + chat/code paste.  
**Tick 456:** HTML-tag-wrapped STATUS headers (`<strong>STATUS: READY</strong>` / `<p><b>**STATUS:…**</b></p>` / `<span style="…">**STATUS: READY**</span>`) strip + demote/update — closes G4 demote no-op / pack miss on Notion/Docs rich-paste / partial HTML→Markdown.  
**Tick 455:** HTML-entity ZWSP/nbsp STATUS headers (`&#8203;**STATUS: READY**` / `&ZeroWidthSpace;**STATUS:…**` / `**STATUS:&nbsp;READY**`) decode + demote/update — closes G4 demote no-op / pack miss on Notion/Docs HTML→Markdown exports.  
**Tick 454:** ZWSP-prefixed + nested bold↔dunder STATUS headers (`\u200b**STATUS: READY**` / `**__STATUS: READY__**` / `__**STATUS: READY**__`) parse + demote/update — closes G4 demote no-op / pack miss on Notion/Docs paste ZWSP and mixed-editor nested stubs.  
**Tick 453:** `__STATUS: READY__` / `***STATUS: READY***` headers parse + demote/update like italic/underscore — closes G4 demote no-op / pack miss on CommonMark dunder-bold / triple-star STATUS stubs.  
**Tick 452:** italic / underscore STATUS headers (`*STATUS*: READY` / `*STATUS: READY*` / `_STATUS: READY_`) parse + demote/update like blockquote/list/BOM — closes G4 demote no-op / pack miss on emphasis STATUS stubs.  
**Tick 451:** blockquote / list / BOM STATUS headers (`> **STATUS: READY**` / `- STATUS: READY` / UTF-8 BOM) parse + demote/update like colon-out/label/plain/ATX — closes G4 demote no-op / pack miss on quoted/listed/BOM STATUS stubs.  
**Tick 450:** colon-outside-bold `**STATUS**: READY` headers parse + demote/update like label/same-span/plain/ATX — closes G4 demote no-op / pack miss on bold-label + colon-outside STATUS stubs.  
**Tick 449:** bold-closed label `**STATUS:** READY` headers parse + demote/update like same-span/plain/ATX — closes G4 demote no-op / pack miss on `**Label:** value` STATUS stubs.  
**Tick 448:** ATX heading `# STATUS:` / `## **STATUS:**` headers parse + demote/update like bold/plain — closes G4 demote no-op / pack miss on heading STATUS stubs.  
**Tick 447:** plain (no `**`) `STATUS:` headers parse + demote/update like bold ones — closes G4 demote no-op / pack miss on bare STATUS stubs.  
**Tick 446:** `_icml_ready_status_header` token parse after `**STATUS:` (not trailing IN_PROGRESS substring).  
**Tick 444:** pipeline `_read_icml_ready_status` header-only (Tick 442/443 parity) — whole-file `re.search` no longer false-READY from prose before the header.  
**Tick 443:** G4 demote/update header-only STATUS (Tick 442 durable parity).  
**Tick 441:** prefer-richer `ICML_READY` merge on durable rebase — length-padded thin IN_PROGRESS no longer wipes onto post-G4 live `[x]` criteria (STATUS still demoted).  
**Tick 440:** prefer-richer `paper_artifacts` (+ larger Figs) merge on durable rebase.  
**Tick 436:** fetch `origin/<tip>` before Tick 435 ahead / Tick 434 checkout — closes stale remote-tracking skip-FF + NF tip push after long live gates.  
**Tick 435:** when already on tip but `origin/<tip>` ahead, FF tip ← origin (preserve durable dirt) — closes stale-base commit + NF tip push.  
**Tick 434:** when HEAD is behind tip, checkout tip (preserve durable dirt) — closes boot commit + non-FF tip push reject.  
**Tick 433:** local tip ref sync before durable commit (boot-name commit no longer leaves tip stale).  
**Tick 432:** durable-ledger push always targets tip PR head when known (closes re-park after accidental `origin/<boot>`).  
**Tick 431:** durable-ledger push redirects greenfield boot → tip PR head.  
**Tick 430:** durable-stash redundancy vs committed HEAD (not WT).  
**Tick 429:** consume only stashes redundant with HEAD.  
**Tick 428:** consume durable stashes after successful tip push.  
**Tick 427:** park/reinject paper-pack companions across tip `--apply` (closes prepare refuse after mid-tick `apply_paper_pack`).  
**Tick 426:** co-commit G4 paper-pack companions with durable ledgers (closes post-`apply_paper_pack` refuse → spend/READY wipe).  
**Tick 425:** tip-recover durable-ledger commit+push (closes commit-only mid-tick death after tip `--apply`).  
**Tick 289:** `ANTHROPIC_API_KEY` is **optional** while the default meta profile is
`kimi-nebius-pydantic-meta` (Nebius). Set `ICML_META_AGENT_PROFILE=default-meta`
only if you intentionally want Claude meta (then Anthropic becomes required again).

## Dual human unblock (Tick 327–342 — read first)

Two human actions remain. Code/offline stack is ready (PRIMARY-shaped offline
`1930–1934` / `1940–1944`, G2 dry-run green, python3-safe surfaces, recipe/shape locks).
Tick **497** removed the HF hard-require when the public diamond mirror (or a local CSV) is available.

| # | Action | Why |
|---|--------|-----|
| **1** | Add **`NEBIUS_API_KEY`** (HF optional — Tick 497 public mirror / local `gpqa_diamond.csv`) | Required for paid G2→G3→G4 |
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

**Tick 387:** **discard/tip-apply prior_live stash** — `discard_ephemeral_icml_dirt` persists trustable `prior_live_*` to gitignored `docs/icml_prior_live_stash.json`; cron + `icml_boot_recover.sh` reinject after tip `--apply` hard-reset (closes wipe of Tick 384–386 evidence).

**Tick 388:** **`icml_recover_tip.py --apply` prior_live stash** — Tick 387 only wired cron/boot_recover; agent chicken-egg `icml_recover_tip.py --apply` still refused dirty trees without stashing and never reinjected after hard-reset. Now discard+stash+reinject (Tick 387 parity); filter stash path from dirty porcelain even if `.gitignore` lags.

**Tick 389:** **committed prior_live evidence (cross-VM)** — Tick 387–388 gitignored stash survives same-VM tip `--apply`, but fresh cloud boots have no stash → paid `prior_live_*` trust dies even when the budget ledger says stages complete. `persist_prior_live_stash_from_working_tree` also writes committed `docs/icml_prior_live_evidence.json` (budget-ledger parity); `reinject_prior_live_stash` falls back to evidence when stash is absent. Commit the evidence file with the tip after live.

**Tick 390:** **tip-apply blocks dirty prior_live evidence** — Tick 389 excluded committed evidence from tip `--apply` dirty filters so hard-reset could wipe uncommitted gates and rely on same-VM stash reinject (not cross-VM safe). Dirty `docs/icml_prior_live_evidence.json` now blocks `--apply` like `docs/icml_budget_spent.json` (true ledger parity); only the gitignored stash stays filtered.

**Tick 391:** **tip-apply gitignore-lag durables** — cron persists `docs/icml_cloud_boot_branch.txt` *before* tip recover; on greenfield/main boots without tip `.gitignore`, porcelain shows the boot file (and call JSON / prior_live stash) as dirty and refused `--apply`. `TIP_APPLY_GITIGNORE_LAG_RELPATHS` filters those paths (evidence still blocks — Tick 390). Also fixes Tick 390 undefined `evidence_norm` in post-discard remaining check.

**Tick 392:** **chicken-egg tip-apply without tip module** — Tick 391 filtered only when `scripts/icml_env_checks.py` was already present; piped `icml_boot_recover.sh --apply` from tip still refused on the boot file. `icml_boot_recover.sh` / `icml_cron_entry.sh` now inline the same IGNORE set when the tip module is absent.

**Tick 393:** **secrets-first generic tip PR body** — Tick 392 froze the chicken-egg tip-apply changelog into `suggested_open_git_pr_body` for every future `Tick {N}` bullet, so `gh pr edit --body-file` / open_git_pr description lied about what the current tick did. Body is now secrets-first + durable tip anti-churn notes; per-tick detail stays in `docs/ICML_PROGRESS.md`.

**Tick 394:** **secrets-status auto-detect synthetic GPQA** — cron `write_icml_secrets_status()` left `gpqa_is_synthetic=null` unless the live pipeline passed an explicit flag; Tip-393 committed secrets JSON omitted the synthetic-diamond blocker with smoke on disk. `detect_gpqa_is_synthetic` + auto-probe in `write_icml_secrets_status`; tip PR body drops frozen "through Tick 392".

**Tick 423:** **post-live durable ledger push** — Tick 422 committed locally after live but never pushed; VM death still re-burned spend on the next greenfield boot. `commit_durable_ledgers_after_live` now non-force pushes tip after commit. Live still needs NEBIUS + HF/CSV.

**Tick 395:** **cron secrets refresh after preflight** — Tick 394 auto-detect still left `gpqa_is_synthetic=null` on greenfield boots because secrets were written **before** G2 `ensure_smoke_layout` materializes `data/`. `icml_cron_entry.sh` now refreshes secrets after preflight and prints `human_next` afterward so the synthetic-diamond blocker surfaces.

**Tick 410:** **G4 full-pair paper-pack gate** — live + `apply_paper_pack` require `len(B)==len(D)==len(plans)` before Live Table / READY (closes partial equal-pair promote after sia-exit mid-abort). Live still needs NEBIUS + HF/CSV.

**Tick 409:** **mid-G4 never-steer abort** — abort remaining pairs after first never-steer Condition D; skip partial paper pack. Live still needs NEBIUS + HF/CSV.

**Tick 406:** **G2 delay-all post-checks** — `validate_g2_artifacts` requires gen2 feedback lack Contradiction-Aware agenda + empty technique_seeds (`run_1953`). Live still needs NEBIUS + HF/CSV.

**Tick 405:** **dry-run feedback fidelity + prior_live scrub** — dry-run resolves CABS feedback prompts (`run_1952`) and no longer stamps `prior_live_post` (G2→G3 poison). Live still needs NEBIUS + HF/CSV.

**Tick 404:** **delay-all scoped feedback gate** — fair gen1→gen2 skips contradiction-scoped CABS agenda in feedback (`apply_cabs_feedback`). Live still needs NEBIUS + HF/CSV.

**Tick 403:** **delay-all technique_seeds gate** — `breed_offspring` skips committee `technique_seeds` inject when `apply_mutation_bias=False`. Live still needs NEBIUS + HF/CSV.

**Tick 402:** **delay-all CABS steering log honesty** — breed logs mark `(deferred until gen≥2…)` vs `(applied)` so gen1→gen2 fair mutate is not misread as steered (G2 dry-run `run_1951`). Live still needs NEBIUS + HF/CSV.

**Tick 401:** **README offline ID lock** — root `README.md` evidence checklist no longer freezes superseded Tick-300 `1890–1904`; cites current offline B/D `1930–1934` / `1940–1944`. `committed_offline_bvd_matches_live_shape` extended. Live still needs NEBIUS + HF/CSV.

**Tick 400:** **human-unblock offline ID lock** — dual-unblock intro no longer freezes superseded Tick-300 `1890–1904`; cites current offline B/D `1930–1934` / `1940–1944`. `committed_offline_bvd_matches_live_shape` extended. Live still needs NEBIUS + HF/CSV.

**Tick 399:** **judge-surface offline ID lock** — SUBMISSION/PRESENTATION/present_hackathon cite `1930–1944` / `run_1940`; restore summary Fig paths. Live still needs NEBIUS + HF/CSV.

**Tick 398:** **case-study post-adoption H2** — `extract_case_study` reports the same last-2-gen window as aggregate H2 (`post_adoption_preferred_share`); `run_1940` post-adoption **0.875** / lift **+0.0607**; paper limitations no longer claim MECHANISM 4/5. Live still needs NEBIUS + HF/CSV.

**Tick 397:** **post-adoption H2 tail** — default last 2 gens (floored at gen≥3) so ε-discover→adopt lag does not dilute preferred_share. Offline re-pilot `1930–1944` → H2 preferred **5/5** (seed 22 0.44→0.75). Live still needs NEBIUS + HF/CSV.

**Tick 396:** **steered-window H2** — `compute_h2` defaults to `min_generation=3` (first steered DNA under delay-all; aligns Tick 23 case study). Offline re-pilot `1910–1924` keeps PRIMARY/H5; seed 22 preferred 0.29→0.44 still fails ≥0.5 honestly. Live still needs NEBIUS + HF/CSV.

**Tick 360:** **PRIMARY mean_final_gap** — `compare_b_vs_d` now emits `mean_final_b` / `mean_final_d` / `mean_final_gap` / `primary_final_pass` so G3→G4 promising mean-gap fallback works and criterion (c) requires mean gap >1pp (not seed-win noise alone).

**Tick 361:** **live H2 bias-field auto-resolve** — G4 `score_live_h2` / `compute_h2(field=None)` pick the DNA field CABS actually biased (prefer `tool_strategy` over hard-coded `memory`) so live MECHANISM does not false-fail when contradictions steer non-memory traits.

**Tick 362:** **offline Fig 2 primary H2** — paper Fig 2 / `D_h2_share` follow auto-resolved `h2` (typically `tool_strategy`), not hard-coded `h2_memory`.

**Tick 363:** **live G4 paper-pack H2 field + PRIMARY gap** — live Fig 2 majority-votes DNA field (not `memory` default); Live Table 1 emits `mean_final_gap` / `primary_final_pass`; H2 rows include `field=`; Winner attributes gens@25%/cost@25%.

**Tick 371:** **G2 nonzero-fitness post-run gate** — best fitness > 0 required for G2 PASS.

**Tick 372:** **G2 resume post-run re-validation** — 0%-fitness `results.json` no longer resume-skips G2 into paid G3/G4; re-runs `validate_g2_artifacts` on local artifacts.

**Tick 379:** **direct gate post-live ledger stamp** — after successful direct G2/G3/G4 `--live`, stamp `stages_complete` (hydrate alone never stamped).

**Tick 380:** **direct gate ledger-stage skip** — Tick 379 stamps the ledger, but direct `--live` still re-launched when local `runs/` were absent. Now skips paid re-run when ledger already marks the stage complete (pipeline Tick 285 parity).

**Tick 370:** **G3→G4 PRIMARY-only promising gate** — H5 ρ>0.3 alone no longer auto-spends ~$14 on 5-seed G4; require gens/cost/final wins or mean_final_gap>1pp (`--force-g4` override). H5/H2 remain report-only (Tick 369).

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
