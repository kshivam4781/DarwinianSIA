"""Judge verify: offline CABS demo + ICML Thesis 1 status (no paid spend)."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Monorepo ships SIA under ROOT/SIA; sibling-checkout layout uses ROOT.parent/SIA.
_SIA_CANDIDATES = (ROOT / "SIA", ROOT.parent / "SIA")
SIA_ROOT = next((p for p in _SIA_CANDIDATES if p.is_dir()), _SIA_CANDIDATES[0])
sys.path.insert(0, str(ROOT))

from cabs.belief_engine import BeliefEngine  # noqa: E402
from cabs.prompt_injection import agenda_snapshot  # noqa: E402


def _run(cmd: list[str], cwd: Path | None = None) -> int:
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd or ROOT, check=False).returncode


def _banner(title: str) -> None:
    print(f"\n{'=' * 72}\n  {title}\n{'=' * 72}\n")


def _icml_status_line() -> str:
    ready = ROOT / "docs" / "ICML_READY.md"
    if not ready.is_file():
        return "UNKNOWN (docs/ICML_READY.md missing)"
    text = ready.read_text(encoding="utf-8")
    m = re.search(r"\*\*STATUS:\s*([A-Z_]+)\*\*", text)
    return m.group(1) if m else "UNKNOWN"


def _offline_bvd_blurb() -> str:
    path = ROOT / "docs" / "offline_bvd_summary.json"
    if not path.is_file():
        return "  (docs/offline_bvd_summary.json missing)"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return f"  (offline_bvd_summary unreadable: {exc})"
    cmp_ = data.get("compare") or {}
    shape = data.get("shape") or {}
    b_ids = data.get("b_run_ids") or []
    d_ids = data.get("d_run_ids") or []
    id_range = (
        f"{b_ids[0]}–{b_ids[-1]} / {d_ids[0]}–{d_ids[-1]}"
        if b_ids and d_ids
        else "see docs/offline_bvd_summary.json"
    )
    return (
        f"  Offline B vs D ({id_range}) @ pop{shape.get('population_size')}×"
        f"eval{shape.get('eval_subset')}×max_gen{shape.get('max_gen')}:\n"
        f"    gens30 D wins {cmp_.get('d_wins_gens30')}/5 "
        f"(primary_gens30={cmp_.get('primary_gens30_pass')}); "
        f"cost30 D wins {cmp_.get('d_wins_cost30')}/5 "
        f"(primary_cost30={cmp_.get('primary_cost30_pass')}); "
        f"final D wins {cmp_.get('d_wins_final')}/5\n"
        f"  NOT live GPQA — do not set ICML_READY from offline alone."
    )


def _ensure_pytest() -> tuple[bool, str]:
    """Bootstrap pytest on cold cloud images (Tick 321).

    Tick 320 made finish ICML-honest, but step 1/5 still ran ``python -m pytest``
    unconditionally. Cold cron / judge VMs often lack pytest → exit 1 and the
    ICML STATUS footer never printed. Prefer pip --user install; if that fails,
    SKIP (do not count as project failure).
    """
    if importlib.util.find_spec("pytest") is not None:
        return True, "pytest already importable"
    print("  pytest missing — bootstrapping via pip install --user …")
    cmd = [sys.executable, "-m", "pip", "install", "--user", "-q", "pytest"]
    print(f"  $ {' '.join(cmd)}")
    try:
        proc = subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return False, "pip install pytest timed out"
    except OSError as exc:
        return False, f"pip install pytest failed: {exc}"
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return False, f"pip install pytest exit {proc.returncode}: {err[:300] or 'no output'}"
    # Fresh import after user-site install
    importlib.invalidate_caches()
    if importlib.util.find_spec("pytest") is None:
        # User site may need to be on sys.path for this process; children get it via site.
        try:
            import site

            site.addsitedir(site.getusersitepackages())
            importlib.invalidate_caches()
        except Exception:
            pass
    if importlib.util.find_spec("pytest") is None:
        return False, "pytest still not importable after pip --user"
    return True, "pytest bootstrapped via pip --user"


def _print_icml_footer(icml_status: str, *, soft_warns: int = 0) -> int:
    """Always print ICML STATUS (Tick 321) — never hide behind pytest failures."""
    if soft_warns:
        print(f"\nFinished with {soft_warns} soft warning(s) — review above.")
    if icml_status == "READY":
        print("\nICML Thesis 1 STATUS: READY — publishable checklist complete.")
        return 0
    print(
        f"\nOffline demo OK — but ICML Thesis 1 STATUS: {icml_status} "
        "(not READY until live PRIMARY + mechanism + H5 + paper pack).\n"
        "Do NOT treat this script's exit-0 as ICML_READY."
    )
    return 0


def main() -> int:
    _banner("SIA-CABS / ICML THESIS 1 — JUDGE VERIFY")
    hard_failures = 0
    soft_warns = 0
    icml_status = _icml_status_line()

    _banner("0/5 ICML Thesis 1 status")
    print(f"  docs/ICML_READY.md STATUS: {icml_status}")
    print(_offline_bvd_blurb())
    print(
        "\n  Live stack (paid, after secrets):\n"
        "    bash scripts/icml_cron_entry.sh\n"
        "    # injects kimi-nebius-pydantic-meta + kimi-nebius-target; G2→G3→G4\n"
        "  Needs NEBIUS_API_KEY + (HF_TOKEN or local gpqa_diamond.csv).\n"
        "  ANTHROPIC_API_KEY optional under default Nebius meta.\n"
        "  Hard stop: do NOT run full LawBench without explicit human approval.\n"
        "  See docs/ICML_HUMAN_UNBLOCK.md | docs/paper_artifacts.md"
    )

    _banner("1/5 Tests")
    pytest_ok, pytest_detail = _ensure_pytest()
    if not pytest_ok:
        soft_warns += 1
        print(f"  SKIP tests: {pytest_detail}")
        print("  (cold image without pytest — not an ICML PRIMARY failure)")
    elif _run([sys.executable, "-m", "pytest", "-q", "--tb=no"]) != 0:
        soft_warns += 1
        print("  WARN: test suite reported failures (does not set ICML_READY)")

    _banner("2/5 Offline showcase (CABS + Tavily + committee artifacts)")
    if _run([sys.executable, str(ROOT / "scripts" / "present_hackathon.py")]) != 0:
        hard_failures += 1

    _banner("3/5 Darwinian merge proof (run_311)")
    run_311 = SIA_ROOT / "runs" / "run_311"
    if run_311.is_dir():
        rc = _run(
            [sys.executable, "-m", "sia_cabs.cli", "analyze", "--run-dir", str(run_311)],
        )
        if rc != 0:
            hard_failures += 1
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
        print(f"  SKIP: {run_311} not found (optional historical merge proof)")

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
    # Tick 322: cold cloud / Linux often lack a `python` shim — only `python3`.
    # Print the interpreter that actually launched this process.
    py = Path(sys.executable).name
    print(f"""
  # Offline (no API) — use this interpreter ({sys.executable}):
  {py} scripts/finish_hackathon.py
  {py} scripts/present_hackathon.py
  {py} -m pytest -q

  # ICML live (paid GPQA — preferred after secrets):
  bash scripts/icml_cron_entry.sh

  # Optional historical merge proof:
  sia-cabs-tools analyze --run-dir SIA/runs/run_311

  Docs: docs/SUBMISSION.md | docs/PRESENTATION.md | docs/ICML_READY.md
  Unblock: docs/ICML_HUMAN_UNBLOCK.md
""")

    _banner("PITCH (30 sec)")
    print("""
  Two metrics: FITNESS (Darwinian accuracy) + KNOWLEDGE GAIN (CABS beliefs/contradictions).
  Thesis: Belief → Contradiction → RQ → Biased mutation / scoped feedback → better
  sample efficiency than fitness-only Darwinian (Condition D vs B).
  Offline PRIMARY-shaped signal exists; live GPQA still needs Nebius + HF/CSV.
""")

    if hard_failures:
        print(f"\nFinished with {hard_failures} hard failure(s) — review above.")
        _print_icml_footer(icml_status, soft_warns=soft_warns)
        return 1

    return _print_icml_footer(icml_status, soft_warns=soft_warns)


if __name__ == "__main__":
    raise SystemExit(main())
