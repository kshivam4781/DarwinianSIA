"""In-loop CABS analyze for Condition D (--cabs-inline).

After each darwinian generation evaluation (before breeding), refresh
``belief_store/`` so mutation bias and feedback agenda see new contradictions.

Prefers in-process ``cabs.belief_engine.BeliefEngine`` (monorepo / SIA_CABS_ROOT).
Falls back to ``sia-cabs-tools analyze --generation N`` subprocess when needed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from sia.evolution.cabs_bridge import resolve_belief_store
from sia.logging_setup import get_logger

logger = get_logger(__name__)


def _repo_root_candidates() -> list[Path]:
    here = Path(__file__).resolve()
    candidates: list[Path] = []
    env = os.environ.get("SIA_CABS_ROOT")
    if env:
        candidates.append(Path(env))
    # Monorepo layout: <root>/{cabs,SIA/sia/evolution/cabs_inline.py}
    candidates.append(here.parents[3])
    # Sibling layout: .../SIA2/cabs next to .../SIA
    candidates.append(here.parents[2].parent / "SIA2")
    candidates.append(here.parents[2].parent)
    return candidates


def ensure_cabs_importable() -> bool:
    """Make ``cabs`` importable; return True on success."""
    try:
        import cabs.belief_engine  # noqa: F401

        return True
    except ImportError:
        pass

    for root in _repo_root_candidates():
        marker = root / "cabs" / "belief_engine.py"
        if not marker.exists():
            continue
        root_str = str(root)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
        try:
            import cabs.belief_engine  # noqa: F401

            return True
        except ImportError:
            continue
    return False


def _epistemic_value(store_root: Path) -> dict[str, float]:
    """H5 working definition: sum of open contradiction + RQ priorities."""

    def _load(name: str, key: str) -> list[dict[str, Any]]:
        path = store_root / name
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        items = data.get(key, []) if isinstance(data, dict) else []
        return [x for x in items if isinstance(x, dict)]

    contradictions = [
        c for c in _load("contradictions.json", "contradictions") if c.get("status", "open") == "open"
    ]
    questions = [
        q for q in _load("research_questions.json", "research_questions") if q.get("status", "open") == "open"
    ]
    c_sum = sum(float(c.get("priority", 0) or 0) for c in contradictions)
    q_sum = sum(float(q.get("priority", 0) or 0) for q in questions)
    return {
        "open_contradictions": float(len(contradictions)),
        "open_research_questions": float(len(questions)),
        "contradiction_priority_sum": c_sum,
        "rq_priority_sum": q_sum,
        "epistemic_value": c_sum + q_sum,
    }


def _append_epistemic_snapshot(run_dir: str, generation: int, cabs_store: str | None) -> dict[str, float]:
    store = resolve_belief_store(run_dir, cabs_store)
    store.mkdir(parents=True, exist_ok=True)
    metrics = _epistemic_value(store)
    row = {"generation": generation, **metrics}
    out = store / "epistemic_value.jsonl"
    with out.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return metrics


def _run_inprocess(
    run_dir: str,
    generation: int,
    *,
    cabs_store: str | None,
    task_hint: str,
    enable_committee: bool,
) -> dict[str, Any]:
    from cabs.belief_engine import BeliefEngine, CabsEngineConfig

    store_root = resolve_belief_store(run_dir, cabs_store)
    engine = BeliefEngine(
        store_root,
        CabsEngineConfig(
            enable_tavily=False,
            enable_committee=enable_committee,
            committee_use_llm=False,
            task_hint=task_hint,
        ),
    )
    result = engine.process_generation(run_dir, generation)
    return {
        "mode": "inprocess",
        "generation": result.generation,
        "beliefs_added": result.beliefs_added,
        "contradictions_added": result.contradictions_added,
        "research_questions_added": result.research_questions_added,
        "knowledge_gain_score": result.knowledge_gain_score,
        "committee": result.committee,
    }


def _run_subprocess(run_dir: str, generation: int) -> dict[str, Any]:
    cmd = [
        "sia-cabs-tools",
        "analyze",
        "--run-dir",
        run_dir,
        "--generation",
        str(generation),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"sia-cabs-tools analyze failed (exit {completed.returncode}): "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {"raw_stdout": completed.stdout[-2000:]}
    return {"mode": "subprocess", "generation": generation, "payload": payload}


def run_cabs_inline(
    run_dir: str,
    generation: int,
    *,
    cabs_store: str | None = None,
    task_hint: str = "",
    enable_committee: bool = False,
) -> dict[str, Any]:
    """Refresh belief_store for one generation; return a JSON-serializable summary."""
    summary: dict[str, Any]
    if ensure_cabs_importable():
        summary = _run_inprocess(
            run_dir,
            generation,
            cabs_store=cabs_store,
            task_hint=task_hint,
            enable_committee=enable_committee,
        )
    else:
        logger.warning(
            "cabs package not importable; falling back to sia-cabs-tools subprocess "
            "(set SIA_CABS_ROOT if needed)"
        )
        summary = _run_subprocess(run_dir, generation)

    metrics = _append_epistemic_snapshot(run_dir, generation, cabs_store)
    summary["epistemic_value"] = metrics.get("epistemic_value", 0.0)
    summary["epistemic_metrics"] = metrics
    return summary
