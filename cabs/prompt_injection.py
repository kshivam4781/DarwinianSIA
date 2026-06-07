"""Inject CABS research agenda into SIA meta/feedback prompts."""

from __future__ import annotations

import json
from typing import Any

from cabs.belief_store import BeliefStore
from cabs.research_agent import build_research_agenda


def format_cabs_context(agenda: dict[str, Any]) -> str:
    contradictions = agenda.get("active_contradictions", [])
    questions = agenda.get("research_questions", [])
    approved = agenda.get("approved_techniques", [])
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
        for idx, contradiction in enumerate(contradictions, start=1):
            lines.append(
                f"{idx}. **{contradiction.get('topic', 'unknown')}**: "
                f"'{contradiction.get('belief_a')}' vs '{contradiction.get('belief_b')}' "
                f"(priority={contradiction.get('priority', 0):.2f})"
            )
        lines.append("")

    if questions:
        lines.append("### Research Questions To Investigate Next")
        for idx, question in enumerate(questions, start=1):
            lines.append(f"{idx}. {question.get('question')}")
            experiments = question.get("experiments") or []
            if experiments:
                lines.append("   Suggested experiments:")
                for experiment in experiments[:4]:
                    lines.append(
                        f"   - {experiment.get('name')}: {experiment.get('variable')}="
                        f"{experiment.get('setting')} on {experiment.get('slice')}"
                    )
            ext = question.get("external_evidence") or {}
            if ext.get("answer") or ext.get("snippets"):
                lines.append("   External evidence (Tavily):")
                if ext.get("answer"):
                    lines.append(f"   - Summary: {ext['answer'][:220]}")
                for snippet in (ext.get("snippets") or [])[:2]:
                    title = snippet.get("title") or snippet.get("url") or "source"
                    content = (snippet.get("content") or "")[:160]
                    lines.append(f"   - {title}: {content}")
        lines.append("")

    evidence_count = agenda.get("external_evidence_count", 0)
    if evidence_count:
        lines.append(f"### External Evidence (Tavily): {evidence_count} research question(s) grounded")
        lines.append("")

    if approved:
        lines.append("### Committee-Approved Techniques (implement in target_agent.py)")
        for idx, tech in enumerate(approved, start=1):
            lines.append(f"{idx}. **{tech.get('technique', 'technique')}** for task `{tech.get('task', 'general')}`")
            if tech.get("belief"):
                lines.append(f"   Belief: {tech['belief']}")
            if tech.get("implementation_hint"):
                lines.append(f"   Implementation: {tech['implementation_hint']}")
            votes = tech.get("committee_vote") or {}
            if votes:
                lines.append(
                    f"   Committee: proponent={votes.get('proponent')}, "
                    f"skeptic={votes.get('skeptic')}, replicator={votes.get('replicator')}"
                )
        lines.append("")

    lines.append(f"Guidance: {agenda.get('guidance', '')}")
    lines.append("")
    return "\n".join(lines)


def load_cabs_prompt_section(belief_store_root: str) -> str:
    store = BeliefStore(belief_store_root)
    agenda = build_research_agenda(
        store.load_contradictions(),
        store.load_research_questions(),
        belief_store_root=belief_store_root,
    )
    return format_cabs_context(agenda)


def inject_into_prompt(prompt: str, belief_store_root: str, *, prepend: bool = True) -> str:
    """Inject CABS agenda. Default: prepend so agents see it first."""
    section = load_cabs_prompt_section(belief_store_root)
    if not section:
        return prompt
    if prepend:
        return f"{section}\n{prompt}"
    return f"{prompt}\n{section}"


def agenda_snapshot(belief_store_root: str) -> dict[str, Any]:
    store = BeliefStore(belief_store_root)
    return build_research_agenda(
        store.load_contradictions(),
        store.load_research_questions(),
        belief_store_root=belief_store_root,
    )
