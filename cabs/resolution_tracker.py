"""Detect when research questions are addressed and mark them resolved."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _topic_keywords(topic: str) -> list[str]:
    mapping = {
        "memory": ["memory", "context", "history", "retain"],
        "reflection": ["reflect", "critique", "review", "self-critique"],
        "planning": ["plan", "planning", "decompose", "chain of thought", "cot"],
        "tool_use": ["tool", "search", "retriev", "function call"],
        "prompting": ["prompt", "instruction", "system message"],
        "error_handling": ["retry", "fallback", "error", "robust"],
        "model_choice": ["model", "temperature", "sampling"],
        "data_quality": ["preprocess", "clean", "data quality"],
    }
    return mapping.get(topic, [topic.replace("_", " ")])


def _improvement_addresses_question(improvement_text: str, question: dict[str, Any]) -> bool:
    text = improvement_text.lower()
    if not text.strip():
        return False

    topic = question.get("topic") or _topic_from_question_text(question.get("question", ""))
    keywords = _topic_keywords(topic)

    topic_hits = sum(1 for kw in keywords if kw in text)
    if topic_hits < 1:
        return False

    investigation_markers = [
        "investigate",
        "test",
        "experiment",
        "compare",
        "disable",
        "enable",
        "slice",
        "when",
        "versus",
        "vs",
        "resolve",
        "contradiction",
        "hypothesis",
    ]
    if any(marker in text for marker in investigation_markers):
        return True

    # Explicit mention of contradiction beliefs
    belief_a = (question.get("belief_a") or "").lower()
    belief_b = (question.get("belief_b") or "").lower()
    for fragment in (belief_a, belief_b):
        if len(fragment) > 20 and fragment[:30] in text:
            return True

    return topic_hits >= 2


def _topic_from_question_text(question: str) -> str:
    lowered = question.lower()
    for topic in (
        "memory",
        "reflection",
        "planning",
        "tool_use",
        "prompting",
        "error_handling",
        "model_choice",
        "data_quality",
    ):
        if topic.replace("_", " ") in lowered or topic in lowered:
            return topic
    return "architecture"


def check_resolutions(
    improvement_text: str,
    open_questions: list[dict[str, Any]],
    contradictions: list[dict[str, Any]],
    generation: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Return updated (questions, contradictions) with resolved items marked.

    Matches open research questions against improvement.md from the generation
    that should investigate them.
    """
    if not improvement_text.strip():
        return open_questions, contradictions

    contradiction_by_id = {c["id"]: c for c in contradictions}
    resolved_contradiction_ids: set[str] = set()
    updated_questions: list[dict[str, Any]] = []

    for question in open_questions:
        q = dict(question)
        if q.get("status") != "open":
            updated_questions.append(q)
            continue
        if _improvement_addresses_question(improvement_text, q):
            q["status"] = "resolved"
            q["resolved_at"] = _utc_now()
            q["resolution"] = f"Addressed in gen_{generation} improvement.md"
            q["resolved_at_gen"] = generation
            cid = q.get("contradiction_id")
            if cid:
                resolved_contradiction_ids.add(cid)
        updated_questions.append(q)

    updated_contradictions: list[dict[str, Any]] = []
    for contradiction in contradictions:
        c = dict(contradiction)
        if c.get("id") in resolved_contradiction_ids and c.get("status") == "open":
            c["status"] = "resolved"
            c["resolved_at"] = _utc_now()
            c["resolved_at_gen"] = generation
        updated_contradictions.append(c)

    return updated_questions, updated_contradictions
