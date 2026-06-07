# Presentation cheat sheet (~2 hours to demo)

## Before you present (5 min)

```powershell
cd c:\Users\MSPSA\Documents\SIA2
.\.venv\Scripts\Activate.ps1
python scripts\finish_hackathon.py
```

Quick demo only: `python scripts\present_hackathon.py`

Confirm you see:
- **35 tests** passing
- A **contradiction** on topic `memory`
- A **research question** with suggested experiments
- Injected CABS prompt section (prepended to next gen)

Optional visual dashboard:
```powershell
python scripts\cabs_dashboard.py --run-dir runs\run_showcase
```

Optional Tavily grounding demo (Layer 2):
```powershell
. .\scripts\load_env.ps1
sia-cabs-tools ground --run-dir runs\run_showcase --max-calls 2 --task-hint longcot-chess
sia-cabs-tools agenda --run-dir runs\run_showcase
```
Look for `external_evidence` and `belief_store/evidence/*.json`.

Committee demo (Layer 3):
```powershell
sia-cabs-tools committee --run-dir runs\run_showcase --task-hint longcot-chess
type runs\run_showcase\belief_store\approved_techniques.json
sia-cabs-tools agenda --run-dir runs\run_showcase
```
Look for `Committee-Approved Techniques` in the injected prompt section.

## Slide-free talking script (~2 min)

**Opening (15 sec)**  
"Most self-improving AI only chases benchmark score. We built SIA-CABS so the system asks *what should I investigate next* when its own beliefs contradict."

**Problem (20 sec)**  
"Gen 1 says memory helps. Gen 2 agrees. Gen 3 says memory hurts on easy tasks. Normal SIA picks a fix. Science would ask: *when* does memory help vs hurt?"

**Demo (45 sec)**  
Run `python scripts/present_hackathon.py` and scroll to:
1. Generation story (beliefs added each gen)
2. CONTRADICTION block
3. RESEARCH QUESTION block
4. INJECTED PROMPT — show this goes into Meta/Feedback next gen

**Architecture (20 sec)**  
"Belief Engine after Feedback: extract beliefs, detect contradictions, generate research questions, inject agenda. Dual metric: accuracy plus knowledge gain."

**Evidence (20 sec)**  
"We ran real SIA on this laptop — baseline run 901, CABS run 902. Full loop works. For the contradiction story, use `runs/run_showcase` — full belief → contradiction → research question chain, no API cost."

**Close (10 sec)**  
"Track 3: new methodology. Future: web search, committee debate, Darwinian evolution in our sibling repo."

## If judges ask questions

| Question | Answer |
|----------|--------|
| How is this different from SIA? | SIA fixes failures. CABS tracks *beliefs* and *contradictions* and steers *what to investigate*. |
| Did accuracy improve? | Not required for Track 3. We show knowledge gain when beliefs conflict. Accuracy is secondary. |
| Can I reproduce? | `python scripts/present_hackathon.py` — no API keys. |
| What's next? | Tavily for evidence, committee to approve techniques, merge with Darwinian population. |

## Backup if terminal fails

Open these files in the IDE:
- `runs/run_showcase/belief_store/contradictions.json`
- `runs/run_showcase/belief_store/research_questions.json`
- `runs/run_showcase/gen_3/cabs_report.json`
- `docs/SUBMISSION.md`

## Optional live API demo (only if time + keys)

```powershell
. .\scripts\load_env.ps1
sia-cabs-tools agenda --run-dir runs\run_902
```
