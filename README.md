# DarwinianSIA (SIA-CABS + Darwinian Evolution)

**Repository:** [github.com/kshivam4781/DarwinianSIA](https://github.com/kshivam4781/DarwinianSIA)

**Contradiction-Aware Belief System** — a hackathon extension for [SIA](https://github.com/hexo-ai/sia) that changes *what* the system learns next. Includes **Darwinian population evolution** (`SIA/`, `sia-upstream/sia/evolution/`) merged with CABS via JSON contracts.

## Present in 2 minutes (no API keys)

```powershell
cd c:\Users\MSPSA\Documents\SIA2
.\.venv\Scripts\Activate.ps1
python scripts\finish_hackathon.py    # full verify (recommended for judges)
python scripts\present_hackathon.py   # 2-min demo only
```

See [`docs/PRESENTATION.md`](docs/PRESENTATION.md) for the talking script and [`docs/SUBMISSION.md`](docs/SUBMISSION.md) for judges.

> **Agents & contributors:** Read [`docs/HACKATHON_MASTER_PLAN.md`](docs/HACKATHON_MASTER_PLAN.md) first — single source of truth for APIs, hardware, blockers, phases, and budgets. See also [`AGENTS.md`](AGENTS.md).

Instead of only optimizing benchmark scores, SIA-CABS maintains:

- **Beliefs** — hypotheses extracted each generation
- **Contradictions** — when beliefs conflict on the same topic
- **Research questions** — first-class objects that drive the next experiment

## Why this is different

Standard SIA loop:

```
Failure → Find cause → Apply fix → Improve score
```

SIA-CABS loop:

```
Belief → Contradiction → Investigation → New theory
```

The Meta/Feedback agents receive an active **research agenda**, not just execution logs.

## Architecture

```
Meta Agent
    ↓
Target Agent
    ↓
Feedback Agent
    ↓
Belief Engine (CABS)
    ├── Belief Extractor
    ├── Contradiction Detector
    └── Research Agent
    ↓
Meta Agent (next generation, with research agenda injected)
```

## Quick start

### 1. Install

Requires **Python 3.11+** (SIA upstream requirement). On Windows with multiple Pythons:

```bash
cd SIA2
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]" -e "./sia-upstream[dev]"
```

Set API keys (copy `.env.example` → `.env`). **ICML live** needs `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`); `ANTHROPIC_API_KEY` is optional under default Nebius pydantic-ai meta (Tick 289/310–318). See `docs/ICML_HUMAN_UNBLOCK.md`.

```bash
# Linux / macOS / cloud:
cp .env.example .env   # edit keys
source scripts/load_env.sh

# Or export directly:
export NEBIUS_API_KEY=your_key_here
# export HF_TOKEN=hf_...
# Optional under Nebius meta:
# export ANTHROPIC_API_KEY=sk-ant-...
```

Windows PowerShell: `. .\scripts\load_env.ps1`

### 2. ICML Thesis 1 live stack (preferred — Tick 288/289/317/318)

Paid G2→G3→G4 uses **Nebius Kimi for both meta and target**. Prefer the cron entry (injects profiles + serial gates under one budget):

```bash
bash scripts/icml_cron_entry.sh
# or: python scripts/run_icml_live_pipeline.py --live --fetch-diamond
```

Manual GPQA (pick unused integer `--run_id`; never overwrite):

```bash
sia run --task gpqa --max_gen 6 --run_id 1300 --no-web --cabs --cabs-inline \
  --meta-agent-profile kimi-nebius-pydantic-meta \
  --target-agent-profile kimi-nebius-target
```

Do **not** spend the ~$20 ICML ceiling on Nemotron/Qwen or Claude meta unless intentionally overriding `ICML_*_AGENT_PROFILE`.

### 3. Historical hackathon smoke (chess / optional Qwen target)

```bash
# Baseline (comparison only — not ICML live)
sia run --task longcot-chess --max_gen 1 --run_id 901 --no-web --target-agent-profile qwen-nebius-target

# SIA-CABS chess smoke
sia-cabs run --task longcot-chess --max_gen 3 --run_id 903 --no-web --target-agent-profile qwen-nebius-target
```

Feedback agent writes `beliefs.json`; CABS agenda is **prepended** to meta/feedback prompts.

### 4. Inspect beliefs and contradictions

```bash
sia-cabs-tools agenda --run-dir runs/run_showcase
python scripts/comparison_report.py --baseline runs/run_901 --cabs runs/run_903 --markdown
python scripts/cabs_dashboard.py --run-dir runs/run_showcase

# Tavily grounding (Layer 2) — needs TAVILY_API_KEY in .env
sia-cabs-tools ground --run-dir runs/run_showcase --max-calls 5 --task-hint longcot-chess
sia-cabs run --task longcot-chess --max_gen 3 --run_id 903 --no-web --tavily --target-agent-profile qwen-nebius-target

# Committee gating (Layer 3) — after Tavily evidence exists
sia-cabs-tools committee --run-dir runs/run_showcase --task-hint longcot-chess
sia-cabs run --task longcot-chess --max_gen 3 --run_id 903 --no-web --tavily --committee --target-agent-profile qwen-nebius-target
```

Or open the per-generation report:

```
runs/run_cabs/gen_2/cabs_report.json
runs/run_cabs/belief_store/beliefs.json
runs/run_cabs/belief_store/contradictions.json
runs/run_cabs/belief_store/research_questions.json
```

### 5. Retroactively analyze an existing SIA run

```bash
sia-cabs-tools analyze --run-dir runs/run_baseline
```

## Project layout

```
belief_store/                 # Template JSON schemas
cabs/
  belief_extractor.py         # Extract beliefs from generation artifacts
  contradiction_detector.py   # Find opposing beliefs on same topic
  research_question_generator.py
  experiment_planner.py
  research_agent.py           # Rank contradictions + design experiments
  belief_engine.py            # Orchestrates the CABS pipeline
  prompt_injection.py         # Injects research agenda into SIA prompts
sia_cabs/
  orchestrator.py             # SIA loop with CABS hooks
  cli.py                      # analyze / agenda utilities
```

## Example output

After a few generations you might see:

```json
{
  "belief": "Memory helps on hard legal reasoning examples",
  "topic": "memory",
  "polarity": "positive",
  "confidence": 0.82
}
```

Later:

```json
{
  "belief": "Memory hurts performance on easy examples",
  "topic": "memory",
  "polarity": "negative",
  "confidence": 0.81
}
```

CABS creates:

```json
{
  "research_question": "When does memory help versus hurt task performance?",
  "experiments": [
    {"name": "memory_on_hard_tasks", "variable": "memory", "setting": "enabled", "slice": "hard"},
    {"name": "memory_off_hard_tasks", "variable": "memory", "setting": "disabled", "slice": "hard"}
  ]
}
```

## Knowledge Gain Score

Each generation gets a `knowledge_gain_score` that rewards:

- new beliefs
- detected contradictions
- generated research questions

A generation that *explains why memory sometimes fails* is valuable even if accuracy does not jump immediately.

## Hackathon tracks

- **Primary**: Track 3 — Novel Self-Improvement Methodology (contradiction-driven learning)
- **Secondary**: Track 1 — if you modify/extend the SIA harness (this project does)

## Offline demo (no API key)

```bash
python scripts/demo_cabs.py
```

Shows belief extraction, contradiction detection, and research question generation from synthetic generations.

## Tests

```bash
pytest
```

## Submission / ICML evidence checklist

**Hard stop:** Do **not** run full LawBench without explicit human approval in the run notes (Section 0 / Section 21). Prefer GPQA diamond under the ~$20 Nebius ceiling.

1. Offline / dry-run evidence: `docs/paper_artifacts.md` + `docs/offline_bvd_summary.json` (IDs `1890–1904`)
2. Live PRIMARY (when secrets present): `bash scripts/icml_cron_entry.sh` → G2→G3→G4; fill Live Table 1
3. Compare Condition B vs D on gens-to-threshold / cost-to-threshold / final accuracy
4. Show at least one contradiction → DNA/code → fitness chain (`docs/case_study_offline.md`; live case study when available)
5. Keep H5 Spearman ρ > 0.3; set `docs/ICML_READY.md` STATUS: READY only when criteria 1–4 pass
