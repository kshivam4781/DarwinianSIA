"""One-command hackathon presentation demo (no API keys required)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIA_ROOT = ROOT.parent / "SIA"
sys.path.insert(0, str(ROOT))

from cabs.belief_engine import BeliefEngine
from cabs.prompt_injection import format_cabs_context

def _seed_showcase() -> Path:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "seed_showcase_run.py")], check=True, cwd=ROOT)
    return ROOT / "runs" / "run_showcase"


def _banner(title: str) -> None:
    width = 72
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)
    print()


def _section(title: str) -> None:
    print(f"\n--- {title} ---\n")


def _run_pytest() -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    line = (result.stdout or "").strip().split("\n")[-1] if result.stdout else "pytest failed"
    print(f"  {line}")
    return result.returncode == 0


def _process_showcase(run_dir: Path) -> list:
    store_dir = run_dir / "belief_store"
    if store_dir.exists():
        import shutil

        shutil.rmtree(store_dir)
    engine = BeliefEngine.for_run(run_dir)
    results = []
    for gen in (1, 2, 3):
        results.append(engine.process_generation(run_dir, gen))
    return results


def _print_story(results: list) -> None:
    for r in results:
        print(
            f"  Gen {r.generation}: +{r.beliefs_added} beliefs, "
            f"+{r.contradictions_added} contradictions, "
            f"+{r.research_questions_added} research questions "
            f"(knowledge gain={r.knowledge_gain_score:.2f})"
        )


def _print_contradiction_chain(engine: BeliefEngine) -> None:
    store = engine.store.snapshot()
    contradictions = store.get("contradictions", [])
    questions = store.get("research_questions", [])

    if contradictions:
        _section("CONTRADICTION (the core insight)")
        c = contradictions[0]
        print(f"  Topic: {c.get('topic')}")
        print(f"  A: {c.get('belief_a')}")
        print(f"  B: {c.get('belief_b')}")
        print(f"  Priority: {c.get('priority', 0):.2f}")

    if questions:
        _section("RESEARCH QUESTION (what to investigate next)")
        q = questions[0]
        print(f"  {q.get('question')}")
        for exp in (q.get("experiments") or [])[:3]:
            print(
                f"    - {exp.get('name')}: {exp.get('variable')}={exp.get('setting')} "
                f"on {exp.get('slice')}"
            )

    from cabs.research_agent import build_research_agenda

    agenda = build_research_agenda(
        engine.store.load_contradictions(),
        engine.store.load_research_questions(),
    )
    injected = format_cabs_context(agenda)
    if injected:
        _section("INJECTED INTO NEXT META/FEEDBACK PROMPT")
        print(injected)


def _darwinian_merge_summary() -> None:
    run_311 = SIA_ROOT / "runs" / "run_311"
    if not run_311.is_dir():
        return
    _section("DARWINIAN + CABS MERGE (run_311)")
    engine = BeliefEngine.for_run(run_311)
    try:
        engine.process_generation(run_311, 2)
    except Exception as exc:
        print(f"  analyze skipped: {exc}")
        return
    store = engine.store.snapshot()
    cross = [
        c for c in store.get("contradictions", [])
        if (c.get("metadata") or {}).get("cross_agent")
    ]
    print(f"  Population layout: gen_2/agent_0 vs agent_1")
    print(f"  Cross-agent contradictions: {len(cross)}")
    if cross:
        c = cross[0]
        print(f"  Top: {c.get('topic')} — agents {c.get('metadata', {}).get('agents')}")
    civ = run_311 / "civilization.json"
    if civ.exists():
        data = json.loads(civ.read_text(encoding="utf-8"))
        gens = data.get("generations", [])
        if gens:
            best = max(g.get("best_fitness", 0) for g in gens)
            print(f"  Darwinian elite fitness: {best:.1%} (GPQA subset)")
    print("  SIA resumes with: sia run --darwinian --resume --cabs --run_id 311 ...")


def _real_runs_summary() -> None:
    run_901 = ROOT / "runs" / "run_901"
    run_902 = ROOT / "runs" / "run_902"
    if not run_901.exists() and not run_902.exists():
        print("  (No live API runs found — showcase demo is sufficient for presentation.)")
        return

    _section("LIVE SIA RUNS ON THIS MACHINE")
    for label, run_dir in [("Baseline SIA", run_901), ("SIA-CABS", run_902)]:
        if not run_dir.exists():
            continue
        results_path = run_dir / "gen_1" / "results.json"
        acc = "?"
        if results_path.exists():
            try:
                data = json.loads(results_path.read_text(encoding="utf-8"))
                acc = data.get("summary", {}).get("accuracy", data.get("accuracy", "?"))
            except (json.JSONDecodeError, OSError):
                pass
        beliefs = 0
        bs = run_dir / "belief_store" / "beliefs.json"
        if bs.exists():
            try:
                beliefs = len(json.loads(bs.read_text(encoding="utf-8")).get("beliefs", []))
            except (json.JSONDecodeError, OSError):
                pass
        print(f"  {label}: {run_dir.name} - gen_1 accuracy={acc}, beliefs={beliefs}")
    print("\n  Full comparison: python scripts/comparison_report.py --baseline runs/run_901 --cabs runs/run_902 --markdown")


def _talking_points() -> None:
    _banner("2-MINUTE PITCH (read aloud)")
    print("""
  1. PROBLEM: Self-improving AI fixes failures but never questions its assumptions.

  2. INSIGHT: Science advances via belief -> contradiction -> investigation.

  3. SOLUTION: SIA-CABS Belief Engine sits between Feedback and Meta agents.
     It extracts beliefs, detects contradictions, and generates research questions.

  4. DEMO: Gen 1-2 say memory helps. Gen 3 says memory hurts on easy cases.
     CABS does NOT just pick a fix - it asks WHEN does memory help vs hurt?

  5. EVIDENCE: Dual metrics - benchmark accuracy AND knowledge gain score.
     We ran real SIA on this laptop (run_901 baseline, run_902 with CABS hooks).

  6. MERGED: Darwinian run_311 + CABS analyze = cross-agent contradictions.
     Fitness picks elites; CABS picks what to question and implement next.
     Tavily + committee on showcase (stratified_memory approved).
""")


def main() -> None:
    _banner("SIA-CABS HACKATHON PRESENTATION")
    print("  Contradiction-Aware Belief System | Track 3: Novel Self-Improvement")
    print("  No API keys needed for this demo.\n")

    _section("1. Tests")
    ok = _run_pytest()
    if not ok:
        print("  Warning: some tests failed — demo still runs.")

    _section("2. Showcase run (3 generations, synthetic)")
    run_dir = _seed_showcase()
    results = _process_showcase(run_dir)
    _print_story(results)

    engine = BeliefEngine.for_run(run_dir)
    _print_contradiction_chain(engine)

    _section("3. Belief store snapshot")
    print(json.dumps(engine.store.snapshot(), indent=2)[:2500])
    if len(json.dumps(engine.store.snapshot())) > 2500:
        print("  ... (truncated)")

    _darwinian_merge_summary()
    _real_runs_summary()
    _talking_points()

    _banner("COMMANDS FOR JUDGES")
    print("""
  python scripts/present_hackathon.py          # this demo
  python scripts/demo_cabs.py                  # minimal offline demo
  python scripts/comparison_report.py --baseline runs/run_901 --cabs runs/run_902 --markdown
  sia-cabs-tools agenda --run-dir runs/run_showcase
  pytest -q

  Docs: docs/SUBMISSION.md | docs/PRESENTATION.md
""")


if __name__ == "__main__":
    main()
