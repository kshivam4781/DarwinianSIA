"""Read CABS belief_store JSON from disk (no SIA2 import — Section 19 contracts)."""

from __future__ import annotations

import json
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


def load_mutation_bias(run_dir: str, cabs_store: str | None = None) -> dict[str, list[str]]:
    """Open research questions → DNA field → candidate values for biased mutation."""
    store = resolve_belief_store(run_dir, cabs_store)
    questions = [
        q for q in _read_json(store / "research_questions.json").get("research_questions", [])
        if q.get("status", "open") == "open"
    ]

    from sia.evolution.dna import (
        MEMORY_MODES,
        PLANNING_STYLES,
        PROMPT_STRUCTURES,
        RETRY_POLICIES,
        TOOL_STRATEGIES,
    )

    field_choices: dict[str, tuple[str, ...]] = {
        "planning_style": PLANNING_STYLES,
        "tool_strategy": TOOL_STRATEGIES,
        "retry_policy": RETRY_POLICIES,
        "memory": MEMORY_MODES,
        "prompt_structure": PROMPT_STRUCTURES,
    }

    bias: dict[str, list[str]] = {}
    for q in questions:
        dna_field = q.get("dna_field")
        if not dna_field or dna_field == "confidence_threshold":
            continue
        choices = field_choices.get(dna_field)
        if choices:
            bias.setdefault(dna_field, [])
            for value in choices:
                if value not in bias[dna_field]:
                    bias[dna_field].append(value)

    return bias


def cabs_store_available(run_dir: str, cabs_store: str | None = None) -> bool:
    store = resolve_belief_store(run_dir, cabs_store)
    return (store / "research_questions.json").exists() or (store / "contradictions.json").exists()
