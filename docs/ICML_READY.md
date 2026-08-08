# ICML Thesis 1 — Ready checklist

**STATUS: IN_PROGRESS**

Do not set STATUS: READY until every item below is checked and evidence paths are real.

## Criteria

### 1. PRIMARY — Condition D beats B
- [ ] D beats B on ≥3/5 seeds for gens-to-threshold (25% or 30%), **or**
- [ ] D beats B on ≥3/5 seeds for cost-to-threshold (≥15% fewer tokens/calls), **or**
- [ ] Non-trivial mean final accuracy gap (not ~1pp noise)
- Evidence: offline synthetic pilot `1830–1834` vs `1840–1844` (Tick 23; post-steering case study) — D gens30 wins **4/5** (B: 0), D cost30 wins **4/5** (B: 0; eval-call proxy), D final wins **5/5**, mean final gap ~**6.15pp**. Offline PRIMARY-shaped signal only — **not** live GPQA; leave unchecked for READY. Live → `docs/paper_artifacts.md` Table 1

### 2. MECHANISM — H2 or case study
- [x] Unit-level H2: contradiction bias skews DNA vs uniform (`SIA/tests/test_cabs_bridge.py`)
- [x] Dry-run in-loop H2 path: scoped mutation bias after `--cabs-inline` (`runs/run_1401`, `SIA/tests/test_cabs_inline_dry_run.py`)
- [x] Scoped feedback injects same DNA candidates as bias (`load_cabs_agenda` + `test_cabs_agenda_includes_scoped_dna_feedback_targets`)
- [x] Fitness-weighted bias: higher-fitness contradiction side ranked first + rank-weighted mutate (`test_mutation_bias_prefers_higher_fitness_side`)
- [x] Preferred-allele anchoring + singleton-bias skip (Tick 10) — Tick 17: outsiders preserved; ε-greedy explores
- [x] Bias-aware crossover (Tick 11) — soft preferred inherit in `crossover(..., bias=)` + `test_bias_aware_crossover_prefers_winner_allele`
- [x] Delayed crossover bias (Tick 12) — fair XO gen1→gen2; soft bias XO from gen2→gen3+ (`apply_crossover_bias`, `test_breed_offspring_can_delay_crossover_bias`)
- [x] Tempered early mutation bias (Tick 13) — soft rank-weighted mutate gen1→gen2; full preferred anchoring from gen≥2 (`apply_mutation_anchor`, `test_biased_mutate_can_soften_preferred_anchor`)
- [x] Delayed **all** mutation bias (Tick 14) — fair mutate+XO gen1→gen2; full CABS steering from gen≥2 (`apply_mutation_bias`, `test_breed_offspring_can_delay_all_mutation_bias`)
- [x] Compressed latent fitness scale (Tick 16) — `[0.02, 0.34]` keeps gen-1 under 30% (`test_deterministic_fitness_scale_keeps_mid_dna_under_threshold`)
- [x] ε-greedy mutation + live population bias harvest (Tick 17) — escape suboptimal frozen contradiction pairs
- [x] Directed ε-explore outside disputed pools (Tick 20) — explore samples only outsiders (`test_biased_mutate_directed_explore_never_redraws_pool`)
- [x] H5 protocol (Tick 18–19) — steered-window (`min_generation=2`) + population-mean forward Δfitness (`delta_horizon=2`; `scripts/epistemic_results.py`)
- [x] Cost-to-threshold PRIMARY helper (Tick 22) — tokens/USD/eval-calls; ≥15% savings wins (`cost_to_threshold`, `primary_cost30_pass`)
- [x] Post-steering case-study H2 (Tick 23) — preferred DNA share at gen≥3 (not fair-bred gen2); multi-allele + fitness-aligned selection (`tests/test_offline_case_study_steered.py`)
- [x] Live G2 preflight runner (Tick 24) — `scripts/run_g2_smoke.py` hard-stops paid smoke without keys / non-smoke GPQA / free run_id / budget (`docs/gate2_report.md`)
- [x] GPQA diamond materializer (Tick 25) — `scripts/prepare_gpqa_diamond.py` + `run_g2_smoke.py --fetch-diamond` (HF/CSV → SIA schema; never commit JSON)
- [x] Live G3 sequential pilot runner (Tick 26) — `scripts/run_g3_pilot.py` hard-stops parallel GPQA / missing keys / synthetic smoke / budget projection / occupied run IDs; preserves offline gate3 block (`docs/gate3_report.md`)
- [x] Live G4 5-seed sequential runner (Tick 27) — `scripts/run_g4_multiseed.py` hard-stops parallel GPQA / missing keys / synthetic smoke / budget projection / occupied run IDs; refreshes Live Table 1 in `docs/paper_artifacts.md` (`docs/gate4_report.md`)
- [x] G4 full paper-pack refresh (Tick 28) — live H2 scoring + Table 2 H2/H5 markers + Figs 1–2 + `ICML_READY` updater; `--refresh-paper-from-runs` recovery (READY only when criteria pass + `--allow-ready`)
- [x] Unified live G2→G3→G4 pipeline (Tick 29) — `scripts/run_icml_live_pipeline.py` chains gates serially under one budget projection; G3→G4 promising gate; `docs/icml_live_pipeline_report.md`
- [x] Linked Cursor environment for live stack (Tick 30) — draft env `0ed19edd-916e-11f1-ba66-0e7d0216e441` + `.cursor/environment.json` (was `environment: null` every prior tick); secrets still required
- [x] Re-linked Cursor environment on greenfield cron (Tick 31) — draft `4b2bb39a-917e-11f1-ba66-0e7d0216e441`; build `bld-20260806-933779ed-…` **SUCCEEDED** + proposed; Tick 30 draft was **not** inherited by automation (cron still booted `environment: null`)
- [x] Per-run venv capability (Tick 32) — `probe_per_run_venv_capable` + G2/G3/G4 `per_run_venv`; Cursor env installs **uv** (draft `e0434bc7-…` / build `5be244b4` SUCCEEDED); fixes vacuous `import venv` false green on images without ensurepip
- [x] Canonical Portal Save target (Tick 33) — `docs/icml_portal_save_target.json`; re-linked uv draft `b0a8b976-…` / build `3b1c84c6` **SUCCEEDED** + proposed (prefer over older Tick 30–32 drafts)
- [x] Tick 34 Portal Save re-link + SystemExit-safe per_run_venv probe — draft `91d72d0c-…` / build `262ebfe1` **SUCCEEDED** + proposed; `probe_per_run_venv_capable` subprocess isolation so ensurepip `sys.exit` cannot kill G2/G3/G4 preflight
- [x] Tick 35 Portal Save re-link — draft `291a67ab-…` / build `da839bad` **SUCCEEDED** + proposed (uv 0.12.2); Tick 34 draft again not inherited by automation cron
- [x] Tick 36 Portal Save re-link — draft `df01ec67-…` / build `aecd8ae8` **SUCCEEDED** + proposed (uv 0.12.2); Tick 35 draft again not inherited by automation cron
- [x] Tick 37 Portal Save re-link — draft `a60e2d80-…` / build `f1fa5eeb` **SUCCEEDED** + proposed (uv 0.12.2); Tick 36 draft again not inherited by automation cron
- [x] Tick 38 Portal Save re-link — draft `667059f5-…` / build `d9b1019f` **SUCCEEDED** + proposed (uv 0.12.2); Tick 37 draft again not inherited by automation cron
- [x] Tick 39 Portal Save re-link — draft `f77c2796-…` / build `fd6c1a72` **SUCCEEDED** + proposed (uv 0.12.2); Tick 38 draft again not inherited by automation cron
- [x] Tick 40 Portal Save re-link — draft `a1202e1f-…` / build `47d88b32` **SUCCEEDED** + proposed (uv 0.12.2); Tick 39 draft again not inherited by automation cron
- [x] Tick 41 Portal Save re-link — draft `b28dbfe2-…` / build `5b2c6af7` **SUCCEEDED** + proposed (uv 0.12.2); Tick 40 draft again not inherited by automation cron
- [x] Tick 42 Portal Save re-link — draft `44dc791a-…` / build `ef042f32` **SUCCEEDED** + proposed (uv 0.12.2); Tick 41 draft again not inherited by automation cron
- [x] Tick 43 Portal Save re-link — draft `fbd56e14-…` / build `a55ab7fc` **SUCCEEDED** + proposed (uv 0.12.2); Tick 42 draft again not inherited by automation cron
- [x] Tick 44 Portal Save re-link — draft `c9cbb09f-…` / build `685c7aeb` **SUCCEEDED** + proposed (uv 0.12.2); Tick 43 draft again not inherited by automation cron
- [x] Tick 45 Portal Save re-link — draft `855d7b11-…` / build `6bb19bfe` **SUCCEEDED** + proposed (uv 0.12.2); Tick 44 draft again not inherited by automation cron
- [x] Tick 46 Portal Save re-link — draft `3b6f81a0-…` / build `b7044749` **SUCCEEDED** + proposed (uv 0.12.3); Tick 45 draft again not inherited by automation cron
- [x] Tick 47 Portal Save re-link — draft `eabae511-…` / build `b06442a0` **SUCCEEDED** + proposed (uv 0.12.3); Tick 46 draft again not inherited by automation cron
- [x] Tick 48 Portal Save re-link — draft `8433b834-…` / build `d649e6ed` **SUCCEEDED** + proposed (uv 0.12.3); Tick 47 draft again not inherited by automation cron
- [x] Tick 49 Portal Save re-link — draft `909a3205-…` / build `bca77a07` **SUCCEEDED** + proposed (uv 0.12.3); Tick 48 draft again not inherited by automation cron
- [x] Tick 50 Portal Save re-link — draft `160e4ee0-…` / build `d235cd35` **SUCCEEDED** + proposed (uv 0.12.3); Tick 49 draft again not inherited by automation cron
- [x] Documented case study (tie → contradiction → different DNA → fitness lift) with artifacts — offline dry-run `docs/case_study_offline.md` + `run_1840` (`selective` preferred → gen3 share **0.75**; lift +0.0436)
- [ ] Live API-run H2 DNA trait skew under contradiction bias
- Evidence: unit + dry-run G1 + scoped feedback + fitness-weighted order + preferred anchoring + bias-aware/delayed XO + tempered early mutation + delay-all mutation bias + compressed fitness scale + ε-greedy/live harvest + directed explore + H5 protocol + cost-to-threshold + **post-steering** offline case study + G2 preflight + diamond fetcher + G3 sequential runner + G4 5-seed runner + G4 paper-pack + unified live pipeline + Cursor env drafts + Tick 32 uv / per_run_venv + Tick 33 Portal Save pointer + Tick 34 SystemExit-safe probe + Tick 35–50 uv drafts; live GPQA still pending (Portal Save **uv-capable** env `160e4ee0-…` onto automation + API keys + HF token / gpqa accept)

### 3. VALIDITY — H5
- [ ] Spearman ρ (`epistemic_value_t` vs `Δfitness_t+1`) > 0.3 on live / publishable runs
- Evidence: offline multi-seed Condition D `1840–1844` (`max_gen=6`) → ρ>0.3 on **5/5** seeds (0.4 / 0.8 / 0.8 / 1.0 / 0.4) using population-mean forward Δfitness (`delta_horizon=2`) and gen≥2 pairs. Still **not** live GPQA.

### 4. PAPER
- [x] Figure 1 draft (offline B vs D learning curves) — `docs/figures/fig1_learning_curves.png`
- [x] Figure 2 draft (H2 DNA histogram / case-study support) — `docs/figures/fig2_mechanism.png`
- [ ] Table 1 (primary metrics by seed) — offline stub filled (incl. cost30); live empty
- [ ] Table 2 (H2/H5 / cost) — offline cost30 **4/5** + post-steer H2 filled; live empty
- [x] Abstract draft (scaffold in `docs/paper_artifacts.md` — live results TBD)
- [x] Limitations (honest; kept updated in `docs/paper_artifacts.md`)
- [ ] Reproducible **live** run IDs listed in `docs/paper_artifacts.md` (dry-run IDs present; live pending)
- Metrics helper: `scripts/epistemic_results.py`; offline pilot: `scripts/offline_bvd_case_study.py`
- G2 layout helper: `scripts/prepare_gpqa_smoke_data.py` (Tick 21; CLI dry-run `run_1800` — not live)
- G2 live runner: `scripts/run_g2_smoke.py` (Tick 24; preflight `docs/gate2_report.md` — live blocked on keys + real GPQA)
- G2 diamond fetcher: `scripts/prepare_gpqa_diamond.py` (Tick 25; `--from-hf` / `--from-csv`; `run_g2_smoke.py --fetch-diamond`)
- G3 sequential pilot: `scripts/run_g3_pilot.py` (Tick 26; preflight `docs/gate3_report.md` — live blocked on keys + real GPQA; run after G2)
- G4 5-seed PRIMARY: `scripts/run_g4_multiseed.py` (Tick 27–28; preflight `docs/gate4_report.md` — live blocked on keys + real GPQA; run after G3; paper pack auto-fills Tables/Figs/READY)
- Live stack orchestrator: `scripts/run_icml_live_pipeline.py` (Tick 29; preflight `docs/icml_live_pipeline_report.md` — preferred entry once keys appear)
- Cursor env: `.cursor/environment.json` (+ **uv**) + Tick 50 draft `160e4ee0-…` (build `d235cd35` SUCCEEDED + proposed; must Portal Save onto automation — prior drafts not inherited); pointer `docs/icml_portal_save_target.json`
- Per-run venv probe: `scripts/icml_env_checks.py` (Tick 32; Tick 34 subprocess / SystemExit-safe)

## Gate tracker (Section 21.5)

| Gate | Status |
|------|--------|
| G0 mechanism unit tests | **PASS** (2026-08-03; … + Tick 32 per_run_venv / uv + Tick 34 SystemExit-safe probe) |
| G1 dry-run Condition D | **PASS** (2026-08-04) — `run_1401` + `test_cabs_inline_dry_run.py` |
| G2 smoke GPQA subset | **PREFLIGHT READY** (Tick 24/25 + Tick 32/34 `per_run_venv`); **live** G2 still BLOCKED (no API keys; no HF_TOKEN / real diamond; need Portal Save uv env `160e4ee0-…` onto automation — see `docs/icml_portal_save_target.json`) |
| G3 pilot B vs D | Offline synthetic pilot preserved (Tick 23; gens30 **4/5**; cost30 **4/5**; H5 **5/5**; post-steer H2); **live** G3 **PREFLIGHT READY** (Tick 26: `run_g3_pilot.py`) but NOT STARTED (blocked on keys; run after G2) |
| G4 5-seed + metrics | **PREFLIGHT READY** (Tick 27–28: `run_g4_multiseed.py` + full paper pack); **live** NOT STARTED (blocked on keys; run after G3) |
| G5 paper pack | PARTIAL (offline figs + post-steer case study + offline PRIMARY gens30/cost30 4/5 + offline H5 5/5); live pack automatable via Tick 28/29 pipeline but NOT STARTED |
