# DarwinianSIA / SIA-CABS — Submission & ICML Thesis 1

**Repository:** https://github.com/kshivam4781/DarwinianSIA  
**Track framing:** Novel self-improvement methodology (belief → contradiction → biased evolution)  
**ICML Thesis 1 status:** see [`docs/ICML_READY.md`](ICML_READY.md) (**IN_PROGRESS** until live PRIMARY)

---

## One-command paths

### Offline demo (judges / no API, ~2 min)

```bash
python scripts/present_hackathon.py   # belief → contradiction → RQ story
# or: python scripts/finish_hackathon.py
```

Talking script: [`docs/PRESENTATION.md`](PRESENTATION.md).

### ICML live stack (paid GPQA — preferred)

```bash
bash scripts/icml_cron_entry.sh
# injects kimi-nebius-pydantic-meta + kimi-nebius-target; serial G2→G3→G4
```

Requires `NEBIUS_API_KEY` + (`HF_TOKEN` **or** local `gpqa_diamond.csv`).  
`ANTHROPIC_API_KEY` is **optional** under default Nebius pydantic-ai meta.  
Details: [`docs/ICML_HUMAN_UNBLOCK.md`](ICML_HUMAN_UNBLOCK.md).

**Hard stop:** Do **not** run full LawBench without explicit human approval in the run notes.

---

## Problem

Score-only self-improvement never questions its assumptions. When two architectures disagree (e.g. memory helps vs hurts), the system should **investigate**, not blindly pick a fix.

## Solution: dual-metric stack

| Metric | System | Decides |
|--------|--------|---------|
| **Fitness** | Darwinian (SIA) | Which agent/DNA survives (GPQA accuracy) |
| **Knowledge gain** | CABS | What to investigate, contradict, ground, implement |

```
Belief → Contradiction → Research question → Biased mutation / scoped feedback → Better sample efficiency
```

**ICML claim (Condition D vs B):** epistemic-full (`--cabs --cabs-inline`) beats darwinian-only on ≥3/5 seeds for gens-to-threshold, cost-to-threshold, or a non-trivial mean final accuracy gap — with H2 mechanism + H5 validity.

---

## Evidence (reproducible)

| Artifact | What it proves |
|----------|----------------|
| Offline B vs D `1890–1894` / `1900–1904` | PRIMARY-shaped at live Nebius shape (pop4×eval5×max_gen6): gens30 **4/5**, cost30 **4/5**, final **5/5**, mean gap ~**6.15pp**, H5 **5/5** — **not** live GPQA |
| `docs/case_study_offline.md` (`run_1900`) | H2: contradiction → preferred DNA share 0.25→0.5→0.75 → fitness lift |
| `docs/paper_artifacts.md` | Figs 1–2, Tables 1–2, abstract, limitations, run IDs |
| `docs/figures/fig1_learning_curves.png` | Offline learning curves B vs D |
| `docs/figures/fig2_mechanism.png` | Offline mechanism / H2 support |
| Live Table 1 / Table 2 | **Empty until** secrets + `bash scripts/icml_cron_entry.sh` |
| `runs/run_showcase` | Offline contradiction chain (hackathon demo) |
| `SIA/runs/run_311` | Darwinian + CABS merge proof (historical) |

Do **not** claim `ICML_READY` STATUS: READY from offline alone.

---

## Layers

| Layer | Status | Demo |
|-------|--------|------|
| 1 CABS | Done | `present_hackathon.py` |
| 2 Tavily | Done | `sia-cabs-tools ground` (optional) |
| 3 Committee | Done | `approved_techniques.json` on showcase |
| Merge Darwinian | Done | `--cabs` / `--cabs-inline` in `SIA/` |
| ICML G2→G4 live | Blocked | Needs NEBIUS + HF/CSV |

## Tests

```bash
pytest -q
# focused ICML lock (after tip recover):
python -m pytest tests/test_icml_env_checks.py::test_icml_anthropic_optional_human_surfaces -q
```

## Reproduce install

```bash
py -3.13 -m venv .venv   # or python3.13
source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]" -e "./sia-upstream[dev]"
source scripts/load_env.sh   # Windows: . .\scripts\load_env.ps1
```

## Why this methodology

- **Novel loop:** Contradiction-driven investigation steers DNA/mutation, not score-chasing alone.
- **Dual metrics:** Fitness curve + epistemic value (H5) + DNA trait skew (H2).
- **Reproducible:** Offline pilots + locked run IDs + gated live pipeline under ~$20.
- **Honest limitations:** Live GPQA still pending; prior G3 AUC fails / token-cost caveats in `paper_artifacts.md`.

## Docs map

| Doc | Use |
|-----|-----|
| `docs/HACKATHON_MASTER_PLAN.md` | Source of truth (esp. §12, §21) |
| `docs/ICML_PROGRESS.md` | Per-tick agent log |
| `docs/ICML_READY.md` | READY checklist |
| `docs/paper_artifacts.md` | Paper pack |
| `docs/ICML_HUMAN_UNBLOCK.md` | Secrets / cron unblock |
| `AGENTS.md` | Agent entry |
