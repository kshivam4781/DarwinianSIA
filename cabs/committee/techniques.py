"""Extract implementable technique candidates from Tavily evidence."""

from __future__ import annotations

import re
from typing import Any

# Known technique slugs and detection patterns in evidence text
TECHNIQUE_CATALOG: dict[str, dict[str, Any]] = {
    "stratified_memory": {
        "name": "stratified_memory",
        "title": "Stratified memory (enable on hard, disable on easy)",
        "topic": "memory",
        "patterns": [r"stratif", r"easy.{0,20}hard", r"disable memory", r"slice", r"episodic"],
        "implementation_hint": "Gate memory by difficulty slice; disable on easy questions, enable on hard.",
    },
    "self_consistency": {
        "name": "self_consistency",
        "title": "Self-consistency (sample multiple answers, majority vote)",
        "topic": "prompting",
        "patterns": [r"self[- ]consisten", r"majority vote", r"multiple samples"],
        "implementation_hint": "Sample 3 completions per question; take majority answer.",
    },
    "planning_depth_cap": {
        "name": "planning_depth_cap",
        "title": "Cap planning depth to avoid timeouts",
        "topic": "planning",
        "patterns": [r"planning depth", r"timeout", r"chain of thought", r"\bcot\b", r"decompose"],
        "implementation_hint": "Limit planning steps to 5; abort CoT early with fallback answer format.",
    },
    "reflection_loop": {
        "name": "reflection_loop",
        "title": "Reflection / self-critique before final answer",
        "topic": "reflection",
        "patterns": [r"reflect", r"self[- ]critique", r"review answer"],
        "implementation_hint": "Add a critique pass that checks format before writing solution line.",
    },
    "working_memory_split": {
        "name": "working_memory_split",
        "title": "Split working memory from long-term recall",
        "topic": "memory",
        "patterns": [r"working memory", r"proactive interference", r"episodic"],
        "implementation_hint": "Keep short buffer for current question only; do not carry full history.",
    },
}


def _evidence_text(evidence: dict[str, Any]) -> str:
    parts = [evidence.get("answer") or ""]
    for item in evidence.get("results") or []:
        parts.append(item.get("title") or "")
        parts.append(item.get("content") or "")
    return " ".join(parts).lower()


def extract_technique_candidates(
    evidence: dict[str, Any],
    *,
    research_question: dict[str, Any] | None = None,
    task_hint: str = "",
) -> list[dict[str, Any]]:
    """Return technique candidates suggested by external evidence."""
    text = _evidence_text(evidence)
    topic = (research_question or {}).get("topic") or ""
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    for slug, meta in TECHNIQUE_CATALOG.items():
        if topic and meta["topic"] != topic and topic not in ("architecture", "benchmark_score"):
            # Prefer topic-aligned techniques unless text strongly matches
            topic_match = meta["topic"] == topic
        else:
            topic_match = True

        hits = sum(1 for pat in meta["patterns"] if re.search(pat, text, re.I))
        if hits == 0:
            continue
        if not topic_match and hits < 2:
            continue
        if slug in seen:
            continue
        seen.add(slug)

        confidence = min(0.55 + hits * 0.12, 0.92)
        candidates.append(
            {
                "technique": slug,
                "title": meta["title"],
                "topic": meta["topic"],
                "task": task_hint or "general",
                "research_question_id": evidence.get("research_question_id"),
                "confidence": round(confidence, 2),
                "implementation_hint": meta["implementation_hint"],
                "evidence_summary": (evidence.get("answer") or "")[:300],
                "source_query": evidence.get("query", ""),
            }
        )

    # Topic fallback if nothing matched
    if not candidates and research_question:
        rq_topic = research_question.get("topic") or "architecture"
        candidates.append(
            {
                "technique": f"investigate_{rq_topic}",
                "title": f"Run controlled experiment on {rq_topic}",
                "topic": rq_topic,
                "task": task_hint or "general",
                "research_question_id": evidence.get("research_question_id"),
                "confidence": 0.5,
                "implementation_hint": f"A/B test {rq_topic} enabled vs disabled on easy and hard slices.",
                "evidence_summary": (evidence.get("answer") or "")[:300],
                "source_query": evidence.get("query", ""),
            }
        )

    return candidates[:3]
