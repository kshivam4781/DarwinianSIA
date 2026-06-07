# Agent instructions — Darwinian AI Civilization (SIA hackathon)

**Before doing anything:** read [`docs/HACKATHON_FINISH_LINE.md`](docs/HACKATHON_FINISH_LINE.md) and execute it (submission sprint).

For full system design and history, also read [`docs/HACKATHON_MASTER_PLAN.md`](docs/HACKATHON_MASTER_PLAN.md). Do **not** re-enter a planning phase unless those files are stale or the user explicitly asks to revise strategy.

## Quick context

| Item | Value |
|------|-------|
| Project | Population-based evolutionary self-improvement for [SIA](https://github.com/hexo-ai/sia) |
| Workspace | `c:\Users\MSPSA\Documents\SIA` |
| OS | **Windows 11** — not Linux |
| Python | **`py -3.13` only** (3.10 is too old) |
| Primary API | **Nebius Token Factory** → `$env:NEBIUS_API_KEY` |
| Promo | `CLAW-NEBIUS-2026-04-B` |
| GPU | RTX 5070 — **unused** (inference via Nebius API) |
| Docker | **Not installed** |
| Submission task | `lawbench` |
| Dev task | `gpqa` (cheaper) |

## Critical blockers (check every session)

1. **Windows venv paths** — `sia/layout.py` must use `Scripts/python.exe` on win32 (see master plan §9 B1).
2. **Never full LawBench darwinian first** — use `--dry-run` and `--eval_subset` (implement if missing).
3. **API money** — subset-first; pop=4 not 8; redeem Nebius promo before big runs.
4. **Submission sprint** — follow [`docs/HACKATHON_FINISH_LINE.md`](docs/HACKATHON_FINISH_LINE.md) (SUBMISSION.md, compare script, showcase run).

## Implementation order

```
✅ Phase 0–1 done → Phase 2: real API subset run → baseline vs darwinian → submission
```

## Key paths

| Path | Purpose |
|------|---------|
| `sia/evolution/` | Darwinian module |
| `sia/orchestrator.py` | Branches to darwinian loop |
| `sia/cli.py` | `--darwinian` flags |
| `docs/HACKATHON_FINISH_LINE.md` | **Execute this for submission** |
| `docs/HACKATHON_MASTER_PLAN.md` | Full plan — architecture & history |

## Commands (after env setup)

```powershell
cd c:\Users\MSPSA\Documents\SIA
.\.venv\Scripts\Activate.ps1
$env:NEBIUS_API_KEY = "your-key"

sia run --task gpqa --darwinian --population_size 2 --elite_count 1 `
  --max_gen 2 --run_id 100 --dry-run --eval_subset 5 --no-web --seed 42
```

## Do not

- Re-plan from scratch without reading the master plan
- Run expensive LawBench population jobs before gates pass
- Use OpenClaw instead of SIA
- Commit API keys
- Break `tests/test_prompts_snapshot.py`
