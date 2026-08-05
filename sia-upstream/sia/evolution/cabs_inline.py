"""In-loop CABS analyze for Condition D (--cabs-inline).

After each darwinian generation evaluation (before breeding), refresh
``belief_store/`` so mutation bias and feedback agenda see new contradictions.

Prefers in-process ``cabs.belief_engine.BeliefEngine`` (monorepo / SIA_CABS_ROOT).
Falls back to ``sia-cabs-tools analyze --generation N`` subprocess when needed.
"""

from __future__ import annotations

import json
import os
import re
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


# Age decay for unresolved open items (per generation since detection).
# Fresh contradictions/RQs dominate; stale open stock fades so multi-gen
# series is non-constant even when the store composition is unchanged.
_EPI_AGE_DECAY = 0.85
# Flow terms: new knowledge / resolutions this generation.
_EPI_KG_WEIGHT = 1.0
_EPI_RES_WEIGHT = 0.5
# Steering opportunity: fitness_gap × under-adoption of preferred DNA.
# Makes H5 (epi_t vs Δfitness_t+1) track actionable contradiction pressure
# rather than pure age decay of open-stock priorities.
_EPI_STEER_WEIGHT = 2.0
# Discovery headroom: aged open-stock × (1 − best_fitness). Keeps epi elevated
# when a local preferred allele has dominated (steering→0) but population
# fitness still has room — the regime where stuck-preferred ε-explore can
# unlock a better allele and raise next-gen fitness (H5 under Tick 17/18).
_EPI_DISCOVERY_WEIGHT = 1.25
# Soften raw open-stock so age-decay alone does not dominate H5 ranks.
_EPI_STOCK_WEIGHT = 0.35
_TRAIT_EQ_RE = re.compile(r"\b([a-z_][a-z0-9_]*)\s*=\s*([a-z0-9_]+)", re.IGNORECASE)
_FITNESS_RE = re.compile(r"fitness\s*[:=]?\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
_KNOWN_DNA_FIELDS = frozenset(
    {
        "planning_style",
        "tool_strategy",
        "retry_policy",
        "memory",
        "prompt_structure",
        "reflection",
        "confidence_threshold",
    }
)


def _item_age(item: dict[str, Any], generation: int) -> int:
    for key in ("detected_at_gen", "created_at_gen", "generation", "resolved_at_gen"):
        raw = item.get(key)
        if raw is None:
            continue
        try:
            return max(0, int(generation) - int(raw))
        except (TypeError, ValueError):
            continue
    return 0


def _effective_priority(item: dict[str, Any], generation: int) -> float:
    base = float(item.get("priority", 0) or 0)
    age = _item_age(item, generation)
    return base * (_EPI_AGE_DECAY**age)


def _load_store_items(store_root: Path, name: str, key: str) -> list[dict[str, Any]]:
    path = store_root / name
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    items = data.get(key, []) if isinstance(data, dict) else []
    return [x for x in items if isinstance(x, dict)]


def _knowledge_gain_from_report(run_dir: str, generation: int) -> float:
    report = Path(run_dir) / f"gen_{generation}" / "cabs_report.json"
    if not report.is_file():
        return 0.0
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0.0
    try:
        return float(data.get("knowledge_gain_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _resolved_priority_sum(store_root: Path, generation: int) -> float:
    """Sum raw priorities of contradictions/RQs resolved at this generation."""
    total = 0.0
    for name, key in (
        ("contradictions.json", "contradictions"),
        ("research_questions.json", "research_questions"),
    ):
        for item in _load_store_items(store_root, name, key):
            if item.get("status") != "resolved":
                continue
            try:
                resolved_gen = int(item.get("resolved_at_gen"))
            except (TypeError, ValueError):
                continue
            if resolved_gen == int(generation):
                total += float(item.get("priority", 0) or 0)
    return total


def _parse_belief_side(text: str) -> tuple[str | None, str | None, float | None]:
    """Parse ``tool_strategy=selective ... fitness 0.52`` style belief sides."""
    if not text:
        return None, None, None
    field: str | None = None
    value: str | None = None
    for match in _TRAIT_EQ_RE.finditer(text):
        cand_field = match.group(1).lower()
        if cand_field in _KNOWN_DNA_FIELDS:
            field = cand_field
            value = match.group(2).lower()
            break
    fitness: float | None = None
    fit_match = _FITNESS_RE.search(text)
    if fit_match:
        try:
            fitness = float(fit_match.group(1))
        except ValueError:
            fitness = None
    return field, value, fitness


def _trait_share_in_generation(
    run_dir: str | Path,
    generation: int,
    field: str,
    value: str,
) -> float | None:
    """Fraction of agents in ``gen_N`` whose DNA ``field`` equals ``value``."""
    gen_dir = Path(run_dir) / f"gen_{int(generation)}"
    if not gen_dir.is_dir():
        return None
    total = 0
    hits = 0
    for dna_path in sorted(gen_dir.glob("agent_*/agent_dna.json")):
        try:
            data = json.loads(dna_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict) or field not in data:
            continue
        total += 1
        raw = data.get(field)
        if isinstance(raw, bool):
            cur = "true" if raw else "false"
        else:
            cur = str(raw).lower()
        if cur == str(value).lower():
            hits += 1
    if total == 0:
        return None
    return hits / total


def _generation_best_fitness(run_dir: str | Path, generation: int) -> float | None:
    """Best agent fitness/accuracy for ``gen_N`` (civilization.json or results)."""
    root = Path(run_dir)
    civ_path = root / "civilization.json"
    if civ_path.is_file():
        try:
            civ = json.loads(civ_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            civ = None
        if isinstance(civ, dict):
            for gen in civ.get("generations", []):
                if not isinstance(gen, dict):
                    continue
                try:
                    g = int(gen.get("gen") or gen.get("generation"))
                except (TypeError, ValueError):
                    continue
                if g == int(generation):
                    try:
                        return float(gen.get("best_fitness", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        break
    fits: list[float] = []
    for results_path in (root / f"gen_{int(generation)}").glob("agent_*/results.json"):
        try:
            data = json.loads(results_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        acc = data.get("accuracy") if isinstance(data, dict) else None
        if isinstance(acc, (int, float)):
            fits.append(float(acc))
    if not fits:
        return None
    return max(fits)


def _discovery_opportunity(
    contradictions: list[dict[str, Any]],
    generation: int,
    run_dir: str | None,
) -> float:
    """Open-contradiction pressure × fitness headroom (live-safe).

    When preferred DNA already dominates, steering_opportunity collapses even
    if the local winner is suboptimal. Discovery keeps epistemic_value high
    until best fitness rises — aligning epi_t with later ε-explore gains.
    """
    if not run_dir or not contradictions:
        return 0.0
    best = _generation_best_fitness(run_dir, generation)
    if best is None:
        return 0.0
    headroom = max(0.0, 1.0 - float(best))
    if headroom <= 0.0:
        return 0.0
    aged = sum(_effective_priority(c, generation) for c in contradictions)
    return aged * headroom


def _steering_opportunity(
    contradictions: list[dict[str, Any]],
    generation: int,
    run_dir: str | None,
) -> float:
    """Actionable contradiction pressure for H5.

    For each open contradiction with parsable fitness on both sides:
    ``aged_priority * fitness_gap * (1 - preferred_trait_share)``.

    High when the higher-fitness DNA side is still under-adopted (room for
    fitness-weighted bias to lift next-gen fitness); low when preferred DNA
    already dominates or the fitness gap is tiny.
    """
    if not run_dir:
        return 0.0
    total = 0.0
    for contradiction in contradictions:
        sides: list[tuple[str, str, float]] = []
        for key in ("belief_a", "belief_b"):
            field, value, fitness = _parse_belief_side(str(contradiction.get(key) or ""))
            if field and value and fitness is not None:
                sides.append((field, value, fitness))
        meta = contradiction.get("metadata") or {}
        if isinstance(meta, dict):
            meta_field = meta.get("dna_field") or meta.get("field") or meta.get("trait")
            meta_values = meta.get("values") or meta.get("candidates")
            meta_scores = meta.get("fitness_by_value") or meta.get("scores")
            if (
                isinstance(meta_field, str)
                and isinstance(meta_values, (list, tuple))
                and isinstance(meta_scores, dict)
            ):
                for raw_val in meta_values:
                    try:
                        score = float(meta_scores[str(raw_val)])
                    except (KeyError, TypeError, ValueError):
                        continue
                    sides.append((meta_field.lower(), str(raw_val).lower(), score))
        # Need two scored sides on the same DNA field.
        by_field: dict[str, list[tuple[str, float]]] = {}
        for field, value, fitness in sides:
            by_field.setdefault(field, []).append((value, fitness))
        best_term = 0.0
        for field, scored in by_field.items():
            if len(scored) < 2:
                continue
            scored_sorted = sorted(scored, key=lambda x: x[1], reverse=True)
            preferred_value, best_fit = scored_sorted[0]
            loser_fit = scored_sorted[-1][1]
            gap = max(0.0, float(best_fit) - float(loser_fit))
            if gap <= 0.0:
                continue
            share = _trait_share_in_generation(run_dir, generation, field, preferred_value)
            if share is None:
                under = 1.0  # unknown adoption → treat as full opportunity
            else:
                under = max(0.0, 1.0 - float(share))
            term = _effective_priority(contradiction, generation) * gap * under
            if term > best_term:
                best_term = term
        total += best_term
    return total


def _epistemic_value(
    store_root: Path,
    generation: int,
    *,
    knowledge_gain: float | None = None,
    run_dir: str | None = None,
) -> dict[str, float]:
    """H5 epistemic_value_t: soft stock + flow + steering + discovery.

    Stock: open contradiction + RQ priorities, decayed by gens since detection
    (down-weighted so age decay alone does not dominate H5 ranks).
    Flow: knowledge_gain_score (from cabs_report) + resolved priorities this gen.
    Steering: aged_priority × fitness_gap × (1 − preferred DNA share).
    Discovery: aged open-stock × (1 − best_fitness) so epi stays predictive when
    a local preferred allele dominates but fitness headroom remains.
    """
    all_contradictions = _load_store_items(store_root, "contradictions.json", "contradictions")
    contradictions = [c for c in all_contradictions if c.get("status", "open") == "open"]
    questions = [
        q
        for q in _load_store_items(store_root, "research_questions.json", "research_questions")
        if q.get("status", "open") == "open"
    ]
    # RQs often lack detected_at_gen; inherit age from linked contradiction when needed.
    c_by_id = {c.get("id"): c for c in all_contradictions if c.get("id")}

    def _rq_effective(q: dict[str, Any]) -> float:
        base = float(q.get("priority", 0) or 0)
        has_age = any(q.get(k) is not None for k in ("detected_at_gen", "created_at_gen", "generation"))
        if has_age:
            return _effective_priority(q, generation)
        parent = c_by_id.get(q.get("contradiction_id"))
        if parent is not None:
            return base * (_EPI_AGE_DECAY ** _item_age(parent, generation))
        return base

    c_raw = sum(float(c.get("priority", 0) or 0) for c in contradictions)
    q_raw = sum(float(q.get("priority", 0) or 0) for q in questions)
    c_sum = sum(_effective_priority(c, generation) for c in contradictions)
    q_sum = sum(_rq_effective(q) for q in questions)

    if knowledge_gain is None:
        knowledge_gain = _knowledge_gain_from_report(run_dir, generation) if run_dir else 0.0
    resolved_sum = _resolved_priority_sum(store_root, generation)
    flow = _EPI_KG_WEIGHT * float(knowledge_gain) + _EPI_RES_WEIGHT * resolved_sum
    steering = _steering_opportunity(contradictions, generation, run_dir)
    discovery = _discovery_opportunity(contradictions, generation, run_dir)
    epistemic_value = (
        _EPI_STOCK_WEIGHT * (c_sum + q_sum)
        + flow
        + _EPI_STEER_WEIGHT * steering
        + _EPI_DISCOVERY_WEIGHT * discovery
    )

    return {
        "open_contradictions": float(len(contradictions)),
        "open_research_questions": float(len(questions)),
        "contradiction_priority_sum": c_sum,
        "rq_priority_sum": q_sum,
        "contradiction_priority_sum_raw": c_raw,
        "rq_priority_sum_raw": q_raw,
        "knowledge_gain_score": float(knowledge_gain),
        "resolved_priority_sum": resolved_sum,
        "epistemic_flow": flow,
        "steering_opportunity": steering,
        "discovery_opportunity": discovery,
        "epistemic_value": epistemic_value,
    }


def _append_epistemic_snapshot(
    run_dir: str,
    generation: int,
    cabs_store: str | None,
    *,
    knowledge_gain: float | None = None,
) -> dict[str, float]:
    store = resolve_belief_store(run_dir, cabs_store)
    store.mkdir(parents=True, exist_ok=True)
    metrics = _epistemic_value(
        store,
        generation,
        knowledge_gain=knowledge_gain,
        run_dir=run_dir,
    )
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

    kg = summary.get("knowledge_gain_score")
    if kg is None and isinstance(summary.get("payload"), dict):
        kg = summary["payload"].get("knowledge_gain_score")
    try:
        kg_f: float | None = float(kg) if kg is not None else None
    except (TypeError, ValueError):
        kg_f = None

    metrics = _append_epistemic_snapshot(
        run_dir,
        generation,
        cabs_store,
        knowledge_gain=kg_f,
    )
    summary["epistemic_value"] = metrics.get("epistemic_value", 0.0)
    summary["epistemic_metrics"] = metrics
    return summary
