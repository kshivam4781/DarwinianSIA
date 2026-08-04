"""Read CABS belief_store JSON from disk (no SIA2 import — Section 19 contracts)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def resolve_belief_store(run_dir: str, cabs_store: str | None = None) -> Path:
    if cabs_store:
        return Path(cabs_store)
    return Path(run_dir) / "belief_store"


def load_cabs_agenda(run_dir: str, cabs_store: str | None = None) -> str:
    """Build CABS agenda text for feedback/meta prompts (mirrors SIA2 format_cabs_context)."""
    store = resolve_belief_store(run_dir, cabs_store)

    contradictions = [
        c for c in _read_json(store / "contradictions.json").get("contradictions", [])
        if c.get("status", "open") == "open"
    ]
    questions = [
        q for q in _read_json(store / "research_questions.json").get("research_questions", [])
        if q.get("status", "open") == "open"
    ]
    approved = _read_json(store / "approved_techniques.json").get("techniques", [])
    if not approved:
        approved = _read_json(store / "approved_techniques.json").get("approved_techniques", [])

    if not contradictions and not questions and not approved:
        return ""

    lines = [
        "",
        "## CABS: Contradiction-Aware Research Agenda",
        "",
        "Do not only optimize benchmark score. Prioritize resolving contradictions and reducing uncertainty.",
        "",
    ]

    if contradictions:
        lines.append("### Active Contradictions")
        for idx, c in enumerate(sorted(contradictions, key=lambda x: -float(x.get("priority", 0)))[:5], 1):
            agents = (c.get("metadata") or {}).get("agents")
            agent_note = f" [agents {agents}]" if agents else ""
            lines.append(
                f"{idx}. **{c.get('topic', 'unknown')}**{agent_note}: "
                f"'{c.get('belief_a')}' vs '{c.get('belief_b')}' "
                f"(priority={float(c.get('priority', 0)):.2f})"
            )
        lines.append("")

    if questions:
        lines.append("### Research Questions To Investigate Next")
        for idx, q in enumerate(sorted(questions, key=lambda x: -float(x.get("priority", 0)))[:5], 1):
            lines.append(f"{idx}. {q.get('question')}")
            if q.get("dna_field"):
                lines.append(f"   DNA field to explore: `{q['dna_field']}`")
        lines.append("")

    if approved:
        lines.append("### Committee-Approved Techniques (MUST implement in target_agent.py)")
        for idx, tech in enumerate(approved[:5], 1):
            name = tech.get("technique", "technique")
            lines.append(f"{idx}. **{name}**")
            if tech.get("implementation_hint"):
                lines.append(f"   Implementation: {tech['implementation_hint']}")
        lines.append("")
        lines.append(
            "**REQUIRED:** You MUST implement every committee-approved technique above "
            "as concrete code changes in `target_agent.py`, not just prompt tweaks."
        )
        lines.append("")

    return "\n".join(lines)


def load_approved_techniques(run_dir: str, cabs_store: str | None = None) -> list[dict[str, Any]]:
    store = resolve_belief_store(run_dir, cabs_store)
    data = _read_json(store / "approved_techniques.json")
    techniques = data.get("techniques") or data.get("approved_techniques") or []
    return [t for t in techniques if isinstance(t, dict)]


def load_approved_technique_names(run_dir: str, cabs_store: str | None = None) -> list[str]:
    """Technique names for offspring DNA technique_seeds (Section 20.5)."""
    names: list[str] = []
    for tech in load_approved_techniques(run_dir, cabs_store):
        name = tech.get("technique")
        if name and name not in names:
            names.append(str(name))
    return names


def _field_choices() -> dict[str, tuple[str, ...]]:
    from sia.evolution.dna import (
        MEMORY_MODES,
        PLANNING_STYLES,
        PROMPT_STRUCTURES,
        RETRY_POLICIES,
        TOOL_STRATEGIES,
    )

    return {
        "planning_style": PLANNING_STYLES,
        "tool_strategy": TOOL_STRATEGIES,
        "retry_policy": RETRY_POLICIES,
        "memory": MEMORY_MODES,
        "prompt_structure": PROMPT_STRUCTURES,
    }


def _parse_trait_values_from_text(text: str, dna_field: str, allowed: tuple[str, ...]) -> list[str]:
    """Extract DNA trait values from belief / RQ text (e.g. memory=failure_based)."""
    if not text:
        return []
    found: list[str] = []
    # Explicit "memory=failure_based" or "memory: failure_based"
    pattern = re.compile(
        rf"\b{re.escape(dna_field)}\s*[=:]\s*([A-Za-z0-9_]+)",
        re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        value = match.group(1)
        if value in allowed and value not in found:
            found.append(value)
    # Bare allowed tokens mentioned in text (order-preserving, avoid over-matching short names)
    lowered = text.lower()
    for value in allowed:
        if value == "none":
            # Require explicit "memory=none" / "memory: none" style — handled above
            continue
        if re.search(rf"\b{re.escape(value)}\b", lowered) and value not in found:
            found.append(value)
    return found


def _values_from_beliefs(
    beliefs: list[dict[str, Any]],
    dna_field: str,
    allowed: tuple[str, ...],
    agent_ids: list[Any] | None = None,
) -> list[str]:
    """Pull trait values from belief metadata written by population DNA extractors."""
    found: list[str] = []
    agent_filter = {int(a) for a in agent_ids} if agent_ids else None
    for belief in beliefs:
        meta = belief.get("metadata") or {}
        if meta.get("trait") != dna_field:
            # Also parse free-text beliefs
            for value in _parse_trait_values_from_text(str(belief.get("belief", "")), dna_field, allowed):
                if value not in found:
                    found.append(value)
            continue
        if agent_filter is not None:
            aid = meta.get("agent_id")
            if aid is None or int(aid) not in agent_filter:
                continue
        value = meta.get("value")
        if isinstance(value, str) and value in allowed and value not in found:
            found.append(value)
    return found


def _values_from_agent_dna_files(
    run_dir: Path,
    dna_field: str,
    allowed: tuple[str, ...],
    agent_ids: list[Any],
    generation: int | None,
) -> list[str]:
    """Read contradicting agents' agent_dna.json for the disputed trait."""
    if generation is None or not agent_ids:
        return []
    found: list[str] = []
    for aid in agent_ids:
        dna_path = run_dir / f"gen_{int(generation)}" / f"agent_{int(aid)}" / "agent_dna.json"
        data = _read_json(dna_path)
        value = data.get(dna_field)
        if isinstance(value, str) and value in allowed and value not in found:
            found.append(value)
    return found


def _append_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def load_mutation_bias(run_dir: str, cabs_store: str | None = None) -> dict[str, list[str]]:
    """Open RQs → DNA field → *contradiction-scoped* candidate values for biased mutation.

    Section 20.4: bias must come from contradicting agent DNAs / belief metadata /
    parsed belief text — NOT the full trait enum (full enum ≡ uniform random ≡ no bias).
    """
    store = resolve_belief_store(run_dir, cabs_store)
    run_path = Path(run_dir)
    questions = [
        q for q in _read_json(store / "research_questions.json").get("research_questions", [])
        if q.get("status", "open") == "open"
    ]
    contradictions = {
        c.get("id"): c
        for c in _read_json(store / "contradictions.json").get("contradictions", [])
        if isinstance(c, dict) and c.get("id")
    }
    beliefs = [
        b for b in _read_json(store / "beliefs.json").get("beliefs", [])
        if isinstance(b, dict) and b.get("status", "active") == "active"
    ]

    field_choices = _field_choices()
    bias: dict[str, list[str]] = {}

    for q in sorted(questions, key=lambda x: -float(x.get("priority", 0))):
        dna_field = q.get("dna_field")
        if not dna_field or dna_field == "confidence_threshold":
            continue
        allowed = field_choices.get(str(dna_field))
        if not allowed:
            continue

        candidates: list[str] = []

        # Explicit candidate_values on the RQ (if a richer exporter wrote them)
        explicit = q.get("candidate_values") or q.get("suggested_values") or []
        if isinstance(explicit, list):
            _append_unique(
                candidates,
                [v for v in explicit if isinstance(v, str) and v in allowed],
            )

        contradiction = contradictions.get(q.get("contradiction_id"))
        agent_ids: list[Any] = []
        detected_gen: int | None = None
        if contradiction:
            meta = contradiction.get("metadata") or {}
            raw_agents = meta.get("agents") or []
            if isinstance(raw_agents, list):
                agent_ids = raw_agents
            detected_gen = contradiction.get("detected_at_gen")
            if detected_gen is not None:
                try:
                    detected_gen = int(detected_gen)
                except (TypeError, ValueError):
                    detected_gen = None

            for key in ("belief_a", "belief_b"):
                _append_unique(
                    candidates,
                    _parse_trait_values_from_text(str(contradiction.get(key, "")), str(dna_field), allowed),
                )

            _append_unique(
                candidates,
                _values_from_beliefs(beliefs, str(dna_field), allowed, agent_ids=agent_ids or None),
            )
            _append_unique(
                candidates,
                _values_from_agent_dna_files(
                    run_path, str(dna_field), allowed, agent_ids, detected_gen
                ),
            )

        # Parse the RQ text itself as a last structured clue
        _append_unique(
            candidates,
            _parse_trait_values_from_text(str(q.get("question", "")), str(dna_field), allowed),
        )

        # If we still have nothing concrete, skip this field — do NOT dump the full enum
        # (that previously made Condition D identical to uniform Darwinian mutation).
        if not candidates:
            continue

        # Keep contradiction pairs small (typically 2 values) for measurable H2 skew
        bias.setdefault(str(dna_field), [])
        _append_unique(bias[str(dna_field)], candidates[:4])

    return bias


def cabs_store_available(run_dir: str, cabs_store: str | None = None) -> bool:
    store = resolve_belief_store(run_dir, cabs_store)
    return (store / "research_questions.json").exists() or (store / "contradictions.json").exists()
