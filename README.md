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

Set API keys (copy `.env.example` → `.env`). **ICML live** needs `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`); `ANTHROPIC_API_KEY` is optional under default Nebius pydantic-ai meta (Tick 289/310). See `docs/ICML_HUMAN_UNBLOCK.md`.

```bash
# Required for ICML live (Nebius target + meta/feedback)
set NEBIUS_API_KEY=your_key_here
# Optional under Nebius meta:
# set ANTHROPIC_API_KEY=sk-ant-...
```

### 2. Baseline SIA run (for comparison)

```bash
sia run --task longcot-chess --max_gen 1 --run_id 901 --no-web --target-agent-profile qwen-nebius-target
```

### 3. SIA-CABS run

```bash
sia-cabs run --task longcot-chess --max_gen 3 --run_id 903 --no-web --target-agent-profile qwen-nebius-target
```

Feedback agent now writes `beliefs.json`; CABS agenda is **prepended** to meta/feedback prompts.

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

## Submission evidence checklist

1. Baseline run: `sia run --task lawbench --max_gen 5 --run_id baseline`
2. CABS run: `sia-cabs run --task lawbench --max_gen 5 --run_id cabs`
3. Compare `results.json` scores across generations in both runs
4. Show at least one contradiction → research question chain from `belief_store/`
5. Explain how the research agenda changed agent behavior in later generations
