# Presentation cheat sheet (ICML Thesis 1 + offline demo)

## Before you present (5 min)

```bash
# Offline story (no API)
python scripts/present_hackathon.py
# or full verify: python scripts/finish_hackathon.py
```

Confirm you see:
- Tests passing (or note focused ICML lock green)
- A **contradiction** on a DNA-relevant topic
- A **research question** with suggested experiments
- Injected CABS prompt section (agenda for next gen)

Optional visual dashboard:
```bash
python scripts/cabs_dashboard.py --run-dir runs/run_showcase
```

### ICML live path (only with secrets + budget)

```bash
bash scripts/icml_cron_entry.sh
```

Needs `NEBIUS_API_KEY` + (`HF_TOKEN` or local `gpqa_diamond.csv`). Anthropic optional under Nebius meta.  
**Do not** run full LawBench without explicit human approval.

Paper pack after live: `docs/paper_artifacts.md`, `docs/ICML_READY.md`.

---

## Slide-free talking script (~2 min)

**Opening (15 sec)**  
"Most self-improving AI only chases benchmark score. We built SIA-CABS so the system asks *what should I investigate next* when its own beliefs contradict — then steers Darwinian DNA mutation from that agenda."

**Problem (20 sec)**  
"Fitness-only Darwinian evolution (Condition B) mutates blindly. When agents disagree — selective vs aggressive tools — science would ask *which allele to prefer*, not sample uniformly."

**Demo (45 sec)**  
Run `python scripts/present_hackathon.py` and scroll to:
1. Generation story (beliefs added each gen)
2. CONTRADICTION block
3. RESEARCH QUESTION block
4. INJECTED PROMPT — show this goes into Meta/Feedback next gen

**ICML claim (20 sec)**  
"Condition D is epistemic-full: `--cabs --cabs-inline`. Offline at the live Nebius shape, D beats B on gens-to-30% **4/5**, cost-to-30% **4/5**, final accuracy **5/5** (~6pp gap), with H5 ρ>0.3 on **5/5**. Live GPQA is the publishable bar — gated behind secrets and a $20 cron pipeline."

**Close (10 sec)**  
"Mechanism: contradiction → preferred DNA → population skew → fitness lift. Evidence pack: `docs/paper_artifacts.md`. Status: `docs/ICML_READY.md`."

---

## If judges ask questions

| Question | Answer |
|----------|--------|
| How is this different from SIA? | SIA fixes failures. CABS tracks *beliefs* and *contradictions* and steers *what to mutate/investigate*. |
| Did accuracy improve? | Offline PRIMARY-shaped yes (D vs B). Publishable claim needs live multi-seed GPQA (G4). |
| Can I reproduce offline? | `python scripts/present_hackathon.py` — no API. Offline Bvd: `docs/offline_bvd_summary.json` IDs `1890–1904`. |
| What's the live command? | `bash scripts/icml_cron_entry.sh` with Nebius + HF/CSV. |
| LawBench? | Hard-stop — not without explicit human approval. |
| What's next? | Unblock secrets → live G2→G3→G4 → fill Live Tables → STATUS READY. |

## Backup if terminal fails

Open these files in the IDE:
- `docs/paper_artifacts.md` (Figs 1–2, Tables, abstract)
- `docs/case_study_offline.md`
- `docs/figures/fig1_learning_curves.png`
- `docs/figures/fig2_mechanism.png`
- `runs/run_showcase/belief_store/contradictions.json`
- `docs/SUBMISSION.md`
- `docs/ICML_READY.md`

## Optional live API demo (only if time + keys)

```bash
source scripts/load_env.sh   # Windows: . .\scripts\load_env.ps1
bash scripts/icml_cron_entry.sh
# or inspect a completed run agenda:
# sia-cabs-tools agenda --run-dir SIA/runs/run_<id>
```
