"""45-minute finish sprint: verify tests, demos, merge proof, print judge commands."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIA_ROOT = ROOT.parent / "SIA"
sys.path.insert(0, str(ROOT))

from cabs.belief_engine import BeliefEngine
from cabs.prompt_injection import agenda_snapshot


def _run(cmd: list[str], cwd: Path | None = None) -> int:
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd or ROOT, check=False).returncode


def _banner(title: str) -> None:
    print(f"\n{'=' * 72}\n  {title}\n{'=' * 72}\n")


def main() -> int:
    _banner("SIA-CABS FINISH SPRINT")
    failures = 0

    _banner("1/5 Tests")
    if _run([sys.executable, "-m", "pytest", "-q", "--tb=no"]) != 0:
        failures += 1
        print("  WARN: SIA2 tests failed")

    _banner("2/5 Offline showcase (CABS + Tavily + committee artifacts)")
    if _run([sys.executable, str(ROOT / "scripts" / "present_hackathon.py")]) != 0:
        failures += 1

    _banner("3/5 Darwinian merge proof (run_311)")
    run_311 = SIA_ROOT / "runs" / "run_311"
    if run_311.is_dir():
        rc = _run(
            [sys.executable, "-m", "sia_cabs.cli", "analyze", "--run-dir", str(run_311)],
        )
        if rc != 0:
            failures += 1
        bs = run_311 / "belief_store"
        if bs.exists():
            contradictions = json.loads((bs / "contradictions.json").read_text(encoding="utf-8"))
            cross = [
                c for c in contradictions.get("contradictions", [])
                if (c.get("metadata") or {}).get("cross_agent")
            ]
            print(f"  Cross-agent contradictions: {len(cross)}")
            if cross:
                c0 = cross[0]
                print(f"  Example: {c0.get('topic')} agents={c0.get('metadata', {}).get('agents')}")
            agenda = agenda_snapshot(str(run_311))
            print(f"  Open research questions: {len(agenda.get('research_questions', []))}")
        civ = run_311 / "civilization.json"
        if civ.exists():
            data = json.loads(civ.read_text(encoding="utf-8"))
            best = max((g.get("best_fitness", 0) for g in data.get("generations", [])), default=0)
            print(f"  Darwinian best fitness: {best:.1%}")
    else:
        print(f"  SKIP: {run_311} not found")

    _banner("4/5 Live runs on this machine")
    for label, path in [
        ("Baseline", ROOT / "runs" / "run_901"),
        ("CABS", ROOT / "runs" / "run_902"),
        ("Showcase", ROOT / "runs" / "run_showcase"),
    ]:
        if not path.is_dir():
            continue
        beliefs = 0
        bp = path / "belief_store" / "beliefs.json"
        if bp.exists():
            beliefs = len(json.loads(bp.read_text(encoding="utf-8")).get("beliefs", []))
        print(f"  {label}: {path.name} beliefs={beliefs}")

    _banner("5/5 JUDGE COMMANDS (copy-paste)")
    print("""
  cd c:\\Users\\MSPSA\\Documents\\SIA2
  .\\.venv\\Scripts\\Activate.ps1
  python scripts\\finish_hackathon.py          # full verify (this script)
  python scripts\\present_hackathon.py         # 2-min demo
  pytest -q

  # CABS + Darwinian merge (no API):
  sia-cabs-tools analyze --run-dir ..\\SIA\\runs\\run_311

  # Layers 2-3 on showcase:
  sia-cabs-tools agenda --run-dir runs\\run_showcase
  type runs\\run_showcase\\belief_store\\approved_techniques.json

  Docs: docs\\SUBMISSION.md | docs\\PRESENTATION.md
""")

    _banner("PITCH (30 sec)")
    print("""
  Two metrics: FITNESS (Darwinian accuracy) + KNOWLEDGE GAIN (CABS beliefs/contradictions).
  CABS asks what to investigate when agents disagree. Darwinian evolves code via DNA.
  MERGED: analyze run_311 finds cross-agent memory/tool contradictions; --cabs steers
  mutation and mandates committee-approved code in feedback. Track 3: novel methodology.
""")

    if failures:
        print(f"\nFinished with {failures} step(s) reporting errors — review above.")
        return 1
    print("\nREADY FOR SUBMISSION.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
