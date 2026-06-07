"""Optional Haiku LLM fallback when heuristic belief extraction is weak."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from cabs.belief_nlp import detect_polarity, detect_topic
from cabs.belief_store import Belief

MIN_BELIEFS_FOR_FALLBACK = 2


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def llm_extract_beliefs(improvement_text: str, generation: int) -> list[Belief]:
    """
    Call Anthropic Haiku to extract beliefs from improvement.md.

    Returns empty list if API key missing or call fails.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or not improvement_text.strip():
        return []

    try:
        import anthropic
    except ImportError:
        return []

    client = anthropic.Anthropic(api_key=api_key)
    prompt = f"""Extract 2-5 beliefs from this agent improvement summary.

Return ONLY a JSON array:
[{{"belief": "...", "topic": "memory|planning|tool_use|reflection|prompting|error_handling", "polarity": "positive|negative", "confidence": 0.8}}]

Improvement text:
{improvement_text[:6000]}
"""

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = ""
        for block in message.content:
            if hasattr(block, "text"):
                raw += block.text
    except Exception:
        return []

    beliefs: list[Belief] = []
    for item in _extract_json_array(raw):
        if not isinstance(item, dict):
            continue
        text = str(item.get("belief", "")).strip()
        if len(text) < 10:
            continue
        topic = detect_topic(text) or str(item.get("topic", "prompting"))
        polarity = str(item.get("polarity", "")).lower()
        if polarity not in ("positive", "negative"):
            polarity = detect_polarity(text)
        if polarity == "neutral":
            continue
        try:
            confidence = float(item.get("confidence", 0.7))
        except (TypeError, ValueError):
            confidence = 0.7
        beliefs.append(
            Belief(
                belief=text,
                topic=topic,
                polarity=polarity,
                confidence=min(max(confidence, 0.0), 1.0),
                generation=generation,
                evidence=[f"gen_{generation}"],
                metadata={"source": "llm_fallback"},
            )
        )
    return beliefs


def maybe_supplement_beliefs(
    beliefs: list[Belief],
    improvement_text: str,
    generation: int,
) -> list[Belief]:
    """Add LLM beliefs when heuristics found fewer than MIN_BELIEFS_FOR_FALLBACK."""
    if len(beliefs) >= MIN_BELIEFS_FOR_FALLBACK:
        return beliefs
    extra = llm_extract_beliefs(improvement_text, generation)
    if not extra:
        return beliefs
    seen = {(b.topic, b.polarity) for b in beliefs}
    merged = list(beliefs)
    for belief in extra:
        key = (belief.topic, belief.polarity)
        if key in seen:
            continue
        seen.add(key)
        merged.append(belief)
    return merged
