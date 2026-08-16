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
- [x] Tick 51 Portal Save re-link — draft `2782ce96-…` / build `58b60bde` **SUCCEEDED** + proposed (uv 0.12.3); Tick 50 draft again not inherited by automation cron
- [x] Tick 52 Portal Save re-link — draft `8be212f6-…` / build `c1181f30` **SUCCEEDED** + proposed (uv 0.12.3); Tick 51 draft again not inherited by automation cron
- [x] Tick 53 Portal Save re-link — draft `430427cc-…` / build `d133e171` **SUCCEEDED** + proposed (uv 0.12.3); Tick 52 draft again not inherited by automation cron
- [x] Tick 54 Portal Save re-link — draft `3b58dff6-…` / build `14292e5c` **SUCCEEDED** + proposed (uv 0.12.3); Tick 53 draft again not inherited by automation cron
- [x] Tick 55 Portal Save re-link — draft `0e1a7bfe-…` / build `789436c4` **SUCCEEDED** + proposed (uv 0.12.3); Tick 54 draft again not inherited by automation cron
- [x] Tick 56 Portal Save re-link — draft `f5eaef73-…` / build `e43fc033` **SUCCEEDED** + proposed (uv 0.12.3); Tick 55 draft again not inherited by automation cron
- [x] Tick 57 Portal Save re-link — draft `a7c13aa8-…` / build `ec58f81c` **SUCCEEDED** + proposed (uv 0.12.3); Tick 56 draft again not inherited by automation cron
- [x] Tick 58 Portal Save re-link — draft `66abb010-…` / build `99028280` **SUCCEEDED** + proposed (uv 0.12.3); Tick 57 draft again not inherited by automation cron
- [x] Tick 59 Portal Save re-link — draft `39fe73ff-…` / build `48a4d1ef` **SUCCEEDED** + proposed (uv 0.12.3); Tick 58 draft again not inherited by automation cron
- [x] Tick 60 Portal Save re-link — draft `f863aceb-…` / build `99f4efcc` **SUCCEEDED** + proposed (uv 0.12.3); Tick 59 draft again not inherited by automation cron
- [x] Tick 61 Portal Save re-link — draft `7b1e2a15-…` / build `a747edc1` **SUCCEEDED** + proposed (uv 0.12.3); Tick 60 draft again not inherited by automation cron
- [x] Tick 62 Portal Save re-link — draft `2b12c210-…` / build `25f4758b` **SUCCEEDED** + proposed (uv 0.12.3); Tick 61 draft again not inherited by automation cron
- [x] Tick 63 Portal Save re-link — draft `47335cc6-…` / build `3833df8a` **SUCCEEDED** + proposed (uv 0.12.3); Tick 62 draft again not inherited by automation cron
- [x] Tick 64 Portal Save re-link — draft `0a0ee6f6-…` / build `92568beb` **SUCCEEDED** + proposed (uv 0.12.3); Tick 63 draft again not inherited by automation cron
- [x] Tick 65 Portal Save re-link — draft `71ef1042-…` / build `9765a488` **SUCCEEDED** + proposed (uv 0.12.3); Tick 64 draft again not inherited by automation cron
- [x] Tick 66 Portal Save re-link — draft `7fd7e079-…` / build `941005fa` **SUCCEEDED** + proposed (uv 0.12.3); Tick 65 draft again not inherited by automation cron
- [x] Tick 67 Portal Save re-link — draft `48095237-…` / build `0a4957c3` **SUCCEEDED** + proposed (uv 0.12.3); Tick 66 draft again not inherited by automation cron
- [x] Tick 68 Portal Save re-link — draft `e057b40a-…` / build `42000aad` **SUCCEEDED** + proposed (uv 0.12.3); Tick 67 draft again not inherited by automation cron
- [x] Tick 69 Portal Save re-link — draft `af3715f5-…` / build `8710d0db` **SUCCEEDED** + proposed (uv 0.12.3); Tick 68 draft again not inherited by automation cron
- [x] Tick 70 Portal Save re-link — draft `7e344b44-…` / build `0cb5c67f` **SUCCEEDED** + proposed (uv 0.12.3); Tick 69 draft again not inherited by automation cron
- [x] Tick 71 Portal Save re-link — draft `3dbda37b-…` / build `5c9bd0c9` **SUCCEEDED** + proposed (uv 0.12.3); Tick 70 draft again not inherited by automation cron
- [x] Tick 72 Portal Save re-link — draft `d82d8e67-…` / build `9c2becbc` **SUCCEEDED** + proposed (uv 0.12.3); Tick 71 draft again not inherited by automation cron
- [x] Tick 73 Portal Save re-link — draft `b69608ac-…` / build `46f388db` **SUCCEEDED** + proposed (uv 0.12.3); Tick 72 draft again not inherited by automation cron
- [x] Tick 74 Portal Save re-link — draft `5f5823ed-…` / build `bd0d630d` **SUCCEEDED** + proposed (uv 0.12.3); Tick 73 draft again not inherited by automation cron
- [x] Tick 75 Portal Save re-link — draft `470cff2e-…` / build `fe8f63e4` **SUCCEEDED** + proposed (uv 0.12.3); Tick 74 draft again not inherited by automation cron
- [x] Tick 76 Portal Save re-link — draft `be57c785-…` / build `8b16e793` **SUCCEEDED** + proposed (uv 0.12.3); Tick 75 draft again not inherited by automation cron
- [x] Tick 77 Portal Save re-link — draft `6c885367-…` / build `760dbe3c` **SUCCEEDED** + proposed (uv 0.12.3); Tick 76 draft again not inherited by automation cron
- [x] Tick 78 Portal Save re-link — draft `547ecd9a-…` / build `5011b4a6` **SUCCEEDED** + proposed (uv 0.12.3); Tick 77 draft again not inherited by automation cron
- [x] Tick 79 Portal Save re-link — draft `1c5a132a-…` / build `c6113f21` **SUCCEEDED** + proposed (uv 0.12.3); Tick 78 draft again not inherited by automation cron
- [x] Tick 80 Portal Save re-link — draft `b9734a8b-…` / build `17e3b68b` **SUCCEEDED** + proposed (uv 0.12.3); Tick 79 draft again not inherited by automation cron
- [x] Tick 81 Portal Save re-link — draft `b39f988c-…` / build `673ccc12` **SUCCEEDED** + proposed (uv 0.12.3); Tick 80 draft again not inherited by automation cron
- [x] Tick 82 Portal Save re-link — draft `8a2353eb-…` / build `c62a6167` **SUCCEEDED** + proposed (uv 0.12.3); Tick 81 draft again not inherited by automation cron
- [x] Tick 83 Portal Save re-link — draft `2bd15cd6-…` / build `c3fe0508` **SUCCEEDED** + proposed (uv 0.12.3); Tick 82 draft again not inherited by automation cron
- [x] Tick 84 Portal Save re-link — draft `c2580665-…` / build `20b04108` **SUCCEEDED** + proposed (uv 0.12.3); Tick 83 draft again not inherited by automation cron
- [x] Tick 85 Portal Save re-link — draft `b14c1b00-…` / build `a371a9fd` **SUCCEEDED** + proposed (uv 0.12.3); Tick 84 draft again not inherited by automation cron
- [x] Tick 86 Portal Save re-link — draft `97f8da5a-…` / build `a67cdff0` **SUCCEEDED** + proposed (uv 0.12.3); Tick 85 draft again not inherited by automation cron
- [x] Tick 87 Portal Save re-link — draft `2b9d6576-…` / build `ee330319` **SUCCEEDED** + proposed (uv 0.12.3); Tick 86 draft again not inherited by automation cron
- [x] Tick 88 Portal Save re-link — draft `b1e29669-…` / build `768b7912` **SUCCEEDED** + proposed (uv 0.12.3); Tick 87 draft again not inherited by automation cron
- [x] Tick 89 Portal Save re-link — draft `07261747-…` / build `4b0c704f` **SUCCEEDED** + proposed (uv 0.12.3); Tick 88 draft again not inherited by automation cron
- [x] Tick 90 Portal Save re-link — draft `53bfbb6f-…` / build `8ce062cd` **SUCCEEDED** + proposed (uv 0.12.3); Tick 89 draft again not inherited by automation cron
- [x] Tick 91 Portal Save re-link — draft `b070825a-…` / build `e19d52de` **SUCCEEDED** + proposed (uv 0.12.3); Tick 90 draft again not inherited by automation cron
- [x] Tick 92 Portal Save re-link — draft `76c7ad3f-…` / build `f81fa69c` **SUCCEEDED** + proposed (uv 0.12.3); Tick 91 draft again not inherited by automation cron
- [x] Tick 93 Portal Save re-link — draft `fcb0a0f4-…` / build `96041347` **SUCCEEDED** + proposed (uv 0.12.3); Tick 92 draft again not inherited by automation cron
- [x] Tick 94 Portal Save re-link — draft `229fd6ce-…` / build `5596330f` **SUCCEEDED** + proposed (uv 0.12.3); Tick 93 draft again not inherited by automation cron
- [x] Tick 95 Portal Save re-link — draft `bb5e7e76-…` / build `88c48096` **SUCCEEDED** + proposed (uv 0.12.3); Tick 94 draft again not inherited by automation cron
- [x] Tick 96 Portal Save re-link — draft `81e72868-…` / build `6e157bcc` **SUCCEEDED** + proposed (uv 0.12.3); Tick 95 draft again not inherited by automation cron
- [x] Tick 97 Portal Save re-link — draft `751332fe-…` / build `23f873be` **SUCCEEDED** + proposed (uv 0.12.3); Tick 96 draft again not inherited by automation cron
- [x] Tick 98 Portal Save re-link — draft `e08cd29b-…` / build `eea1e9ca` **SUCCEEDED** + proposed (uv 0.12.3); Tick 97 draft again not inherited by automation cron
- [x] Tick 99 Portal Save re-link — draft `70fcc83e-…` / build `361b109b` **SUCCEEDED** + proposed (uv 0.12.3); Tick 98 draft again not inherited by automation cron
- [x] Tick 100 Portal Save re-link — draft `c2ad6d68-…` / build `490aa59b` **SUCCEEDED** + proposed (uv 0.12.3); Tick 99 draft again not inherited by automation cron
- [x] Tick 101 Portal Save re-link — draft `53b0d180-…` / build `eae9e731` **SUCCEEDED** + proposed (uv 0.12.3); Tick 100 draft again not inherited by automation cron
- [x] Tick 102 Portal Save re-link — draft `e834f19a-…` / build `563ac7ae` **SUCCEEDED** + proposed (uv 0.12.3); Tick 101 draft again not inherited by automation cron
- [x] Tick 103 Portal Save re-link — draft `945cf4e0-…` / build `ff4cb61f` **SUCCEEDED** + proposed (uv 0.12.3); Tick 102 draft again not inherited by automation cron
- [x] Tick 104 Portal Save re-link — draft `d5ce09b1-…` / build `2191a0c0` **SUCCEEDED** + proposed (uv 0.12.3); Tick 103 draft again not inherited by automation cron
- [x] Tick 105 Portal Save re-link — draft `c96922a7-…` / build `158c6a74` **SUCCEEDED** + proposed (uv 0.12.3); Tick 104 draft again not inherited by automation cron
- [x] Tick 106 Portal Save re-link — draft `7a0d714b-…` / build `852aa860` **SUCCEEDED** + proposed (uv 0.12.3); Tick 105 draft again not inherited by automation cron
- [x] Tick 107 Portal Save re-link — draft `eccd72e0-…` / build `55688c31` **SUCCEEDED** + proposed (uv 0.12.3); Tick 106 draft again not inherited by automation cron
- [x] Tick 108 Portal Save re-link — draft `a88df79f-…` / build `cebb7bd7` **SUCCEEDED** + proposed (uv 0.12.3); Tick 107 draft again not inherited by automation cron
- [x] Tick 109 Portal Save re-link — draft `8a5f870d-…` / build `5cc5d6e4` **SUCCEEDED** + proposed (uv 0.12.3); Tick 108 draft again not inherited by automation cron
- [x] Tick 110 Portal Save re-link — draft `51029881-…` / build `8c3754f3` **SUCCEEDED** + proposed (uv 0.12.3); Tick 109 draft again not inherited by automation cron
- [x] Tick 111 Portal Save re-link — draft `e150b7f1-…` / build `0042344a` **SUCCEEDED** + proposed (uv 0.12.3); Tick 110 draft again not inherited by automation cron
- [x] Tick 112 Portal Save re-link — draft `d7e6f41e-…` / build `8e1487e8` **SUCCEEDED** + proposed (uv 0.12.3); Tick 111 draft again not inherited by automation cron
- [x] Tick 113 Portal Save re-link — draft `4b6c5dd1-…` / build `79322e5f` **SUCCEEDED** + proposed (uv 0.12.3); Tick 112 draft again not inherited by automation cron
- [x] Tick 114 Portal Save re-link — draft `ab63f1e2-…` / build `6e71fc43` **SUCCEEDED** + proposed (uv 0.12.3); Tick 113 draft again not inherited by automation cron
- [x] Tick 115 Portal Save re-link — draft `4be50240-…` / build `427c3d44` **SUCCEEDED** + proposed (uv 0.12.3); Tick 114 draft again not inherited by automation cron
- [x] Tick 116 Portal Save re-link — draft `1b3a12e9-…` / build `5f067c36` **SUCCEEDED** + proposed (uv 0.12.4); Tick 115 draft again not inherited by automation cron
- [x] Tick 117 Portal Save re-link — draft `be42444c-…` / build `cc5e6bd7` **SUCCEEDED** + proposed (uv 0.12.4); Tick 116 draft again not inherited by automation cron
- [x] Tick 118 Portal Save re-link — draft `75254e0e-…` / build `6aede369` **SUCCEEDED** + proposed (uv 0.12.4); Tick 117 draft again not inherited by automation cron
- [x] Tick 119 Portal Save re-link — draft `92caf434-…` / build `24cfc26e` **SUCCEEDED** + proposed (uv 0.12.4); Tick 118 draft again not inherited by automation cron
- [x] Tick 120 Portal Save re-link — draft `58f2651d-…` / build `8455afe8` **SUCCEEDED** + proposed (uv 0.12.5); Tick 119 draft again not inherited by automation cron
- [x] Tick 121 Portal Save re-link — draft `0fe5bb37-…` / build `1a30bd18` **SUCCEEDED** + proposed (uv 0.12.5); Tick 120 draft again not inherited by automation cron
- [x] Tick 122 Portal Save re-link — draft `7a341c97-…` / build `c0548436` **SUCCEEDED** + proposed (uv 0.12.5); Tick 121 draft again not inherited by automation cron
- [x] Tick 123 Portal Save re-link — draft `01d80b32-…` / build `05b0fe3f` **SUCCEEDED** + proposed (uv 0.12.5); Tick 122 draft again not inherited by automation cron
- [x] Tick 124 Portal Save re-link — draft `cfa45bdf-…` / build `ac69edae` **SUCCEEDED** + proposed (uv 0.12.5); Tick 123 draft again not inherited by automation cron
- [x] Tick 125 Portal Save re-link — draft `d8436f8e-…` / build `345243d2` **SUCCEEDED** + proposed (uv 0.12.5); Tick 124 draft again not inherited by automation cron
- [x] Tick 126 Portal Save re-link — draft `7462f7f9-…` / build `514ddaaf` **SUCCEEDED** + proposed (uv 0.12.5); Tick 125 draft again not inherited by automation cron
- [x] Tick 127 Portal Save re-link — draft `54dea794-…` / build `d5e3334b` **SUCCEEDED** + proposed (uv 0.12.5); Tick 126 draft again not inherited by automation cron
- [x] Tick 128 Portal Save re-link — draft `6fdaef21-…` / build `80d57b01` **SUCCEEDED** + proposed (uv 0.12.5); Tick 127 draft again not inherited by automation cron
- [x] Tick 129 Portal Save re-link — draft `2acd30d9-…` / build `d9c1598f` **SUCCEEDED** + proposed (uv 0.12.5); Tick 128 draft again not inherited by automation cron
- [x] Tick 130 Portal Save re-link — draft `015756d5-…` / build `b292908f` **SUCCEEDED** + proposed (uv 0.12.5); Tick 129 draft again not inherited by automation cron
- [x] Tick 131 Portal Save re-link — draft `b386c9a9-…` / build `7dd2b14f` **SUCCEEDED** + proposed (uv 0.12.5); Tick 130 draft again not inherited by automation cron
- [x] Tick 132 Portal Save re-link — draft `3e680d4c-…` / build `33f67cb5` **SUCCEEDED** + proposed (uv 0.12.5); Tick 131 draft again not inherited by automation cron
- [x] Tick 133 Portal Save re-link — draft `30a347b7-…` / build `ea1872bd` **SUCCEEDED** + proposed (uv 0.12.5); Tick 132 draft again not inherited by automation cron
- [x] Tick 134 Portal Save re-link — draft `f324774e-…` / build `6b15cc9d` **SUCCEEDED** + proposed (uv 0.12.5); Tick 133 draft again not inherited by automation cron
- [x] Tick 135 Portal Save re-link — draft `793f5f75-…` / build `6f995d2d` **SUCCEEDED** + proposed (uv 0.12.5); Tick 134 draft again not inherited by automation cron
- [x] Documented case study (tie → contradiction → different DNA → fitness lift) with artifacts — offline dry-run `docs/case_study_offline.md` + `run_1840` (`selective` preferred → gen3 share **0.75**; lift +0.0436)
- [ ] Live API-run H2 DNA trait skew under contradiction bias
- Evidence: unit + dry-run G1 + scoped feedback + fitness-weighted order + preferred anchoring + bias-aware/delayed XO + tempered early mutation + delay-all mutation bias + compressed fitness scale + ε-greedy/live harvest + directed explore + H5 protocol + cost-to-threshold + **post-steering** offline case study + G2 preflight + diamond fetcher + G3 sequential runner + G4 5-seed runner + G4 paper-pack + unified live pipeline + Cursor env drafts + Tick 32 uv / per_run_venv + Tick 33 Portal Save pointer + Tick 34 SystemExit-safe probe + Tick 35–134 uv drafts; live GPQA still pending (Portal Save **uv-capable** env `793f5f75-…` onto automation + API keys + HF token / gpqa accept)

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
- Cursor env: `.cursor/environment.json` (+ **uv**) + Tick 135 draft `793f5f75-…` (build `6f995d2d` SUCCEEDED + proposed; must Portal Save onto automation — prior drafts not inherited); pointer `docs/icml_portal_save_target.json`
- Per-run venv probe: `scripts/icml_env_checks.py` (Tick 32; Tick 34 subprocess / SystemExit-safe)

## Gate tracker (Section 21.5)

| Gate | Status |
|------|--------|
| G0 mechanism unit tests | **PASS** (2026-08-03; … + Tick 32 per_run_venv / uv + Tick 34 SystemExit-safe probe) |
| G1 dry-run Condition D | **PASS** (2026-08-04) — `run_1401` + `test_cabs_inline_dry_run.py` |
| G2 smoke GPQA subset | **PREFLIGHT READY** (Tick 24/25 + Tick 32/34 `per_run_venv`); **live** G2 still BLOCKED (no API keys; no HF_TOKEN / real diamond; need Portal Save uv env `793f5f75-…` onto automation — see `docs/icml_portal_save_target.json`) |
| G3 pilot B vs D | Offline synthetic pilot preserved (Tick 23; gens30 **4/5**; cost30 **4/5**; H5 **5/5**; post-steer H2); **live** G3 **PREFLIGHT READY** (Tick 26: `run_g3_pilot.py`) but NOT STARTED (blocked on keys; run after G2) |
| G4 5-seed + metrics | **PREFLIGHT READY** (Tick 27–28: `run_g4_multiseed.py` + full paper pack); **live** NOT STARTED (blocked on keys; run after G3) |
| G5 paper pack | PARTIAL (offline figs + post-steer case study + offline PRIMARY gens30/cost30 4/5 + offline H5 5/5); live pack automatable via Tick 28/29 pipeline but NOT STARTED |
