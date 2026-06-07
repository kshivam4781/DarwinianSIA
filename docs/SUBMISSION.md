# SIA-CABS — Hackathon Submission

**Track 3: Novel Self-Improvement Methodology**  
**Title:** Contradiction-Aware Belief System + Darwinian Code Evolution  
**Repository:** https://github.com/kshivam4781/DarwinianSIA

---

## One-command demo (judges, ~2 min, no API)

```powershell
cd c:\Users\MSPSA\Documents\SIA2
.\.venv\Scripts\Activate.ps1
python scripts\finish_hackathon.py
```

Or presentation-only: `python scripts\present_hackathon.py`

---

## Problem

Score-only self-improvement never questions its assumptions. When two architectures disagree (memory helps vs hurts), the system should **investigate**, not blindly pick a fix.

## Solution: dual-metric stack

| Metric | System | Decides |
|--------|--------|---------|
| **Fitness** | Darwinian (SIA) | Which agent/DNA survives (GPQA accuracy) |
| **Knowledge gain** | CABS (SIA2) | What to investigate, contradict, ground, implement |

```
Belief → Contradiction → Research question → [Tavily] → [Committee] → Prompt/DNA steering
```

## Evidence (reproducible on this machine)

| Artifact | What it proves |
|----------|----------------|
| `runs/run_showcase` | Full 3-gen contradiction chain + committee `stratified_memory` |
| `runs/run_901` / `run_902` | Live SIA baseline vs CABS hooks |
| `SIA/runs/run_311` | Darwinian 2-gen, 20% elite; CABS cross-agent contradictions |
| `SIA/runs/run_311/belief_store/` | Merge output after `sia-cabs-tools analyze` |

### Merge (CABS + Darwinian) — implemented

```powershell
sia-cabs-tools analyze --run-dir c:\Users\MSPSA\Documents\SIA\runs\run_311
```

- Reads `gen_N/agent_K/` population layout
- Detects cross-agent contradictions (`metadata.agents: [0,1]`)
- Maps topics → DNA fields (`tool_use` → `tool_strategy`)
- SIA `--cabs` injects agenda + committee MUST-implement into feedback; biases mutation

```powershell
cd c:\Users\MSPSA\Documents\SIA
sia run --task gpqa --darwinian --resume --cabs --run_id 311 --max_gen 3 --no-web
```

## Layers

| Layer | Status | Demo |
|-------|--------|------|
| 1 CABS | Done | `present_hackathon.py` |
| 2 Tavily | Done | `sia-cabs-tools ground --run-dir runs/run_showcase` |
| 3 Committee | Done | `approved_techniques.json` on showcase |
| Merge Darwinian | Done | `analyze` on `run_311` |

## Tests

```powershell
pytest -q   # 35 tests SIA2
```

## Reproduce install

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]" -e "./sia-upstream[dev]"
. .\scripts\load_env.ps1
```

## Why Track 3

- **Novel loop:** Contradiction-driven investigation, not score-chasing alone.
- **Working + merged:** CABS + Darwinian wired via JSON contracts (`docs/HACKATHON_MASTER_PLAN.md` §19–20).
- **Dual metrics:** Fitness curve + knowledge gain curve.
- **Reproducible:** Offline demo + real runs + 35 tests.

## Repos

- **SIA2** (this submission): CABS, Tavily, committee
- **SIA** (sibling): Darwinian population, `civilization.json`, `--cabs` consumer
